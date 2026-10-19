# Security and threat model — pre-alpha

## What is actually enforced today

1. The browser UI binds only to `127.0.0.1` and uses a fresh process-local bearer token, host checks and same-origin POST validation. The token is passed to the opened browser through a URL fragment, not an HTTP query.
2. MCP tools expose no approval granting, file browsing outside the managed project via arbitrary paths, arbitrary shell command, plugin installer, publisher or credential operation.
3. Projects are created under a managed workspace root; new source generation refuses nonempty existing directories and rejects symlink paths outside the workspace.
4. The controller stores explicit, SHA-256 argument-bound approval requests and enforces one-use execution authorization for the Gradle build operation.
5. The system does not read/store cloud API keys, install third-party plugins, modify normal `.minecraft` saves or publish output.
6. Static integrity validation checks generated SHA-256 manifests and parses JSON.

## What is **NOT** enforced yet (important)

- **There is no OS-level sandbox.** Gradle plugins and build scripts are executable, can contact the network, run arbitrary commands and access files according to the user's OS account. Build approvals disclose this.
- Claude Code can have separate tool/shell permissions that bypass our controller. The `.mcp.json` and `.claude/agents` restrictions do **not** constrain other tools the user grants to Claude Code.
- The app does not yet implement hardened signed installers, remote supply-chain integrity, provider redaction, per-worker OS isolation, independent process custody, enforced CPU/memory budgets, full atomic workspace staging, or signed approval audit logs.
- One local user owning the profile can edit the SQLite database / source or act through the CLI; this is a **single-user desktop prototype** and does not claim resistance to local administrator compromise.
- The HTTP app is not intended for remote access, reverse proxies or shared hosts. Disallow port forwarding/tunneling. Other local processes can inspect data belonging to the same OS account. The token controls HTTP clients, not OS-local adversaries.

## Future must-have security milestones

- Trusted component downloader with manufacturer source pinning, checksums, signature validation where available, version pinning, rollback and approved installer capabilities.
- Gradle/JDK/Minecraft game worker isolated using OS sandbox/VM/container with writable allowlist, egress policy, clean ephemeral worlds, resource limits, filesystem overlay and secret removal.
- Enforced scoped file access and per-agent repo worktrees; prompt injection from README, Reddit, user projects and retrieved MCP metadata must not elevate authority.
- Authenticated controller IPC with origin protections and no network listener required (named pipes/Unix sockets preferred for production).
- Patch review UI, license scanners, software bill of materials (SBOM), reproducible build checks and secret/file classification for any cloud upload.
- Negative security tests for symlink escapes, path traversal, forged tools, approval replay, approval mismatch, malicious Gradle modifications, world deletion and unsafe dependency installs.

## Security reporting

Please do not paste credentials or private project source in public issues. Report issues through a private GitHub advisory/disclosure channel when the GitHub repository is published.
