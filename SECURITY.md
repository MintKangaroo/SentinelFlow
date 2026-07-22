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
