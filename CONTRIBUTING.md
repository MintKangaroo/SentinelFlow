# Contributing

Use Python 3.12+ and Node.js 20+. Keep changes focused, typed, tested, and documented.
Install both workspaces, then run the complete gate before committing:

```bash
python3 -m pip install -e ".[dev]"
npm --prefix web ci
make check
```

Use Conventional Commits. Never commit `.env`, credentials, tokens, production data, or
details of unauthorized targets. Security-sensitive features require deny-by-default
tests, abuse cases, redacted errors, and an auditable authorization decision.
