"""Use cases for workspace-scoped, immutable response playbooks."""

from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sentinelflow.application.incidents import utc_now
from sentinelflow.application.ports import PlaybookUnitOfWork
from sentinelflow.domain import (
    Playbook,
    PlaybookEvent,
    PlaybookEventType,
    PlaybookIdempotencyConflict,
    PlaybookNotFound,
    PlaybookStatus,
    PlaybookStep,
    PlaybookVersion,
    PlaybookVersionNotFound,
)
from sentinelflow.domain.playbook import JsonObject

type PlaybookUnitOfWorkFactory = Callable[[], PlaybookUnitOfWork]
type Clock = Callable[[], datetime]
type IdFactory = Callable[[], UUID]


class PlaybookService:
    """Coordinate playbook aggregates, immutable revisions, and audit events."""

    def __init__(
        self,
        unit_of_work_factory: PlaybookUnitOfWorkFactory,
        *,
        clock: Clock = utc_now,
        id_factory: IdFactory = uuid4,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock
        self._id_factory = id_factory

    async def create(
        self,
        *,
        workspace_id: UUID,
        name: str,
        description: str,
        steps: tuple[PlaybookStep, ...],
        actor_id: str,
        idempotency_key: str,
    ) -> tuple[Playbook, PlaybookVersion]:
        """Create a playbook and immutable revision one atomically."""
        now = self._clock()
        playbook_id = self._id_factory()
        candidate = PlaybookVersion.build(
            id=self._id_factory(),
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            number=1,
            steps=steps,
            created_by=actor_id,
            created_at=now,
        )
        event_data: JsonObject = {
            "name": name,
            "description": description,
            "revision": 1,
            "definition_hash": candidate.definition_hash,
        }
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.playbooks.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_replay(
                    existing,
                    event_type=PlaybookEventType.CREATED,
                    actor_id=actor_id,
                    data=event_data,
                )
                playbook = await unit_of_work.playbooks.get(workspace_id, existing.playbook_id)
                version = await unit_of_work.playbooks.get_version(
                    workspace_id, existing.playbook_id, 1
                )
                if playbook is None or version is None:
                    raise PlaybookNotFound
                return playbook, version

            playbook = Playbook(
                id=playbook_id,
                workspace_id=workspace_id,
                name=name,
                description=description,
                status=PlaybookStatus.DRAFT,
                latest_version=1,
                active_version=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
            event = PlaybookEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                playbook_id=playbook.id,
                sequence=1,
                event_type=PlaybookEventType.CREATED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=event_data,
                occurred_at=now,
            )
            await unit_of_work.playbooks.add(playbook, candidate, event)
            await unit_of_work.commit()
            return playbook, candidate

    async def get(self, *, workspace_id: UUID, playbook_id: UUID) -> Playbook:
        """Return a playbook without crossing its workspace."""
        async with self._unit_of_work_factory() as unit_of_work:
            playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id)
            if playbook is None:
                raise PlaybookNotFound
            return playbook

    async def list(
        self,
        *,
        workspace_id: UUID,
        status: PlaybookStatus | None,
        limit: int,
        offset: int,
    ) -> Sequence[Playbook]:
        """List playbooks within one workspace."""
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.playbooks.list(
                workspace_id, status=status, limit=limit, offset=offset
            )

    async def get_version(
        self, *, workspace_id: UUID, playbook_id: UUID, number: int
    ) -> PlaybookVersion:
        """Get one immutable playbook revision."""
        async with self._unit_of_work_factory() as unit_of_work:
            version = await unit_of_work.playbooks.get_version(workspace_id, playbook_id, number)
            if version is None:
                raise PlaybookVersionNotFound
            return version

    async def list_versions(
        self, *, workspace_id: UUID, playbook_id: UUID
    ) -> Sequence[PlaybookVersion]:
        """List all immutable revisions after verifying the aggregate exists."""
        async with self._unit_of_work_factory() as unit_of_work:
            playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id)
            if playbook is None:
                raise PlaybookNotFound
            return await unit_of_work.playbooks.list_versions(workspace_id, playbook_id)

    async def create_version(
        self,
        *,
        workspace_id: UUID,
        playbook_id: UUID,
        steps: tuple[PlaybookStep, ...],
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> tuple[Playbook, PlaybookVersion]:
        """Append an immutable revision with optimistic concurrency."""
        async with self._unit_of_work_factory() as unit_of_work:
            playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id, for_update=True)
            if playbook is None:
                raise PlaybookNotFound

            existing = await unit_of_work.playbooks.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                raw_revision = existing.data.get("revision")
                revision = raw_revision if isinstance(raw_revision, int) else 0
                candidate = PlaybookVersion.build(
                    id=self._id_factory(),
                    workspace_id=workspace_id,
                    playbook_id=playbook_id,
                    number=revision,
                    steps=steps,
                    created_by=actor_id,
                    created_at=existing.occurred_at,
                )
                expected_data: JsonObject = {
                    "revision": revision,
                    "definition_hash": candidate.definition_hash,
                    "expected_version": expected_version,
                }
                self._assert_replay(
                    existing,
                    event_type=PlaybookEventType.VERSION_CREATED,
                    actor_id=actor_id,
                    data=expected_data,
                    playbook_id=playbook_id,
                    expected_version=expected_version,
                )
                version = await unit_of_work.playbooks.get_version(
                    workspace_id, playbook_id, revision
                )
                if version is None:
                    raise PlaybookVersionNotFound
                return playbook, version

            now = self._clock()
            previous_version, revision = playbook.create_revision(now, expected_version)
            version = PlaybookVersion.build(
                id=self._id_factory(),
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                number=revision,
                steps=steps,
                created_by=actor_id,
                created_at=now,
            )
            event_data: JsonObject = {
                "revision": revision,
                "definition_hash": version.definition_hash,
                "expected_version": expected_version,
            }
            event = PlaybookEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                sequence=playbook.version,
                event_type=PlaybookEventType.VERSION_CREATED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=event_data,
                occurred_at=now,
            )
            await unit_of_work.playbooks.save(playbook, previous_version=previous_version)
            await unit_of_work.playbooks.add_version(version)
            await unit_of_work.playbooks.add_event(event)
            await unit_of_work.commit()
            return playbook, version

    async def publish(
        self,
        *,
        workspace_id: UUID,
        playbook_id: UUID,
        revision: int,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> Playbook:
        """Activate one immutable revision."""
        data: JsonObject = {
            "revision": revision,
            "expected_version": expected_version,
        }
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.playbooks.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_replay(
                    existing,
                    event_type=PlaybookEventType.PUBLISHED,
                    actor_id=actor_id,
                    data=data,
                    playbook_id=playbook_id,
                    expected_version=expected_version,
                )
                playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id)
                if playbook is None:
                    raise PlaybookNotFound
                return playbook

            playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id, for_update=True)
            if playbook is None:
                raise PlaybookNotFound
            version = await unit_of_work.playbooks.get_version(workspace_id, playbook_id, revision)
            if version is None:
                raise PlaybookVersionNotFound
            now = self._clock()
            previous_version = playbook.publish(revision, now, expected_version)
            event = PlaybookEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                sequence=playbook.version,
                event_type=PlaybookEventType.PUBLISHED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=data,
                occurred_at=now,
            )
            await unit_of_work.playbooks.save(playbook, previous_version=previous_version)
            await unit_of_work.playbooks.add_event(event)
            await unit_of_work.commit()
            return playbook

    async def archive(
        self,
        *,
        workspace_id: UUID,
        playbook_id: UUID,
        expected_version: int,
        actor_id: str,
        idempotency_key: str,
    ) -> Playbook:
        """Make a playbook permanently read-only."""
        data: JsonObject = {"expected_version": expected_version}
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.playbooks.get_event_by_idempotency(
                workspace_id, idempotency_key
            )
            if existing is not None:
                self._assert_replay(
                    existing,
                    event_type=PlaybookEventType.ARCHIVED,
                    actor_id=actor_id,
                    data=data,
                    playbook_id=playbook_id,
                    expected_version=expected_version,
                )
                playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id)
                if playbook is None:
                    raise PlaybookNotFound
                return playbook

            playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id, for_update=True)
            if playbook is None:
                raise PlaybookNotFound
            now = self._clock()
            previous_version = playbook.archive(now, expected_version)
            event = PlaybookEvent(
                id=self._id_factory(),
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                sequence=playbook.version,
                event_type=PlaybookEventType.ARCHIVED,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                data=data,
                occurred_at=now,
            )
            await unit_of_work.playbooks.save(playbook, previous_version=previous_version)
            await unit_of_work.playbooks.add_event(event)
            await unit_of_work.commit()
            return playbook

    async def events(
        self, *, workspace_id: UUID, playbook_id: UUID, limit: int
    ) -> Sequence[PlaybookEvent]:
        """Return ordered immutable audit events."""
        async with self._unit_of_work_factory() as unit_of_work:
            playbook = await unit_of_work.playbooks.get(workspace_id, playbook_id)
            if playbook is None:
                raise PlaybookNotFound
            return await unit_of_work.playbooks.list_events(workspace_id, playbook_id, limit=limit)

    @staticmethod
    def _assert_replay(
        event: PlaybookEvent,
        *,
        event_type: PlaybookEventType,
        actor_id: str,
        data: JsonObject,
        playbook_id: UUID | None = None,
        expected_version: int | None = None,
    ) -> None:
        if (
            event.event_type is not event_type
            or event.actor_id != actor_id
            or event.data != data
            or (playbook_id is not None and event.playbook_id != playbook_id)
            or (expected_version is not None and event.sequence != expected_version + 1)
        ):
            raise PlaybookIdempotencyConflict
