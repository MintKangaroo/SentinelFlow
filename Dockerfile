FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system sentinelflow && adduser --system --ingroup sentinelflow sentinelflow

COPY pyproject.toml README.md LICENSE alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY deploy/api-entrypoint.sh ./deploy/api-entrypoint.sh
RUN python -m pip install --no-cache-dir .

USER sentinelflow

EXPOSE 8000
CMD ["./deploy/api-entrypoint.sh"]
