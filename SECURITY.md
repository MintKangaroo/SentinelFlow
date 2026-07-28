# Security Policy

## Supported versions

The project is pre-alpha. Security fixes are applied to the latest `main` branch.

## Reporting a vulnerability

Do not open a public issue containing exploit details, secrets, personal data, or live
target information. Use the repository host's private security-advisory feature. If that
is unavailable, contact the maintainers privately through a verified project profile.
Expect acknowledgement within five business days.

## Authorized-use boundary

This software is designed only for operator-owned systems, local or Docker labs, CTFs,
educational cyber ranges, and explicitly authorized environments. Unauthorized scanning,
public-range discovery, credential theft, persistence, evasion, malware deployment,
data destruction, and data exfiltration are prohibited.

Future target-facing code must deny public or unregistered targets by default, permit
localhost, RFC1918, Docker networks, or explicit allowlist entries only, and record
redacted audit events for rejected requests.

Never submit real credentials, tokens, cookies, private keys, personal information, or
raw authentication material in issues, logs, fixtures, or commits.

## Deployment boundary

Incident endpoints require workspace and actor headers, but this milestone does not authenticate
them. Do not expose the API directly to an untrusted network. A trusted identity gateway must
authenticate callers, remove caller-supplied identity headers, and inject only authorized
workspace and actor context.

## Integration Adapter boundary

The Adapter SDK accepts opaque UUID credential references only. Secret-manager implementations
must authorize every lookup using both `workspace_id` and the reference; storing resolved values
in PostgreSQL, integration JSON, logs, traces, task payloads, or exception messages is prohibited.

Outbound clients require a fixed HTTPS origin by default, reject credentials and paths in the
configured base URL, reject absolute per-request URLs, do not follow redirects, and reserve
authentication, workspace, correlation, and idempotency headers. Unsafe HTTP is available only
through an explicit development opt-in.

Retries are bounded. Non-idempotent requests are never retried without an idempotency key.
These transport controls do not authorize an action: high-risk writes remain prohibited until
workflow, human-approval, dry-run, and compensation controls are implemented.
