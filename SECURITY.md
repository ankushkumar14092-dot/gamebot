# Security Policy

## 🔒 Supported Versions

| Version / Branch | Supported |
|---|---|
| `main` | :white_check_mark: |

---

## 🛡️ Reporting a Vulnerability

If you discover a security vulnerability or sensitive information exposure within this repository, please do **NOT** open a public issue.

Instead, please report the vulnerability directly:
- Through GitHub Private Vulnerability Reporting on this repository.
- Or by contacting the maintainer directly.

Please include:
1. Description of the issue and affected components.
2. Steps to reproduce or proof-of-concept.
3. Potential impact.

---

## 🔐 Secret Hygiene & Safety Guidelines

- **Zero-Secret Policy in Git:** Never commit `.env`, API keys (`GEMINI_API_KEY`, `FIREWORKS_API_KEY`), or team credentials.
- **Git Pre-Push Scanning:** The automated workflow checks staged diffs for accidental API key patterns before staging commits.
- **Emergency Stop Protocol:** In the event of an unexpected loop or rate runaway, place an `EMERGENCY_STOP` file in the workspace root to immediately freeze all autonomous processes.
