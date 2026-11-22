# Security reporting

Do not post passwords, private keys, precise private locations or sensitive message contents in public issues or relay rooms.

Report security vulnerabilities through [GitHub private vulnerability reporting](https://github.com/HK1200/Meshchat-neXt/security/advisories/new), which is enabled for this repository. A public relay room or ordinary GitHub issue is not a private reporting channel. Do not include live passwords or private identity keys in a report; use a minimal reproduction with disposable data.

For general, non-sensitive bugs and support, see [README.md](README.md). Include the affected version, platform, reproduction steps and a description of the impact. Review and redact diagnostic files before sharing them.

The reporting destination belongs to this project. No inherited upstream contact should be assumed to accept neXt security reports.

## CI scanner availability

The supplemental Argus supply-chain indicator action became unavailable upstream in November 2026. Its pinned repository returns HTTP 404, so the workflow reports the missing scan explicitly instead of preventing the dependency-audit job from starting. The pip-audit, Trivy dependency/configuration, gitleaks, CodeQL and Scorecard checks remain enabled. This does not represent an Argus scan passing.
