# Pilot testing log

Findings from exploratory testing of the orchestrator (Python layer only; no Gradle/Minecraft
available in the test environment). Severity: **High** = generated output cannot compile or a
safety gate fails; **Med** = wrong/unclear behavior a user will hit; **Low** = polish.

Status legend: OPEN · FIXED(branch) · WONTFIX

## Round 1 — 2026-10-19 · CLI + UI API · base `dev` @ 5b2fae8

### Bugs

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| B1 | High | generator | Item/block id `mod_id` → `public static final Item MOD_ID` collides with the `MOD_ID` string constant. Duplicate field, javac fails. Uniqueness check only compares raw identifiers, not derived Java names. | FIXED (`claude-feature/round1-fixes`) |
| B2 | High | generator | Item `ruby_item` + block `ruby` → `RUBY_ITEM` emitted twice (item + BlockItem). Duplicate field; block also lands in the wrong creative tab. Same root cause as B1. | FIXED (`claude-feature/round1-fixes`) |
| B3 | Med | generator | Datapack folder `loot_tables/` is ignored by 1.21+ (singular `loot_table/`); blocks dropped nothing. Test asserted the wrong path. | FIXED (`claude-feature/mojmap-1.21.1-generator`) |

### UX / correctness

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| U1 | Med | build | One-use build approval is **consumed even when no Gradle is found** (`BUILD_BLOCKED`). User must request + grant again for a tooling problem. Pre-check wrapper/Gradle before `consume_approval`. | FIXED (`claude-feature/round1-fixes`) |
| U2 | Med | build | `request-build` succeeds on a tampered workspace; failure only surfaces at `build` after the approval is spent. Run `validate_generated` inside `request_build` and refuse early. | FIXED (`claude-feature/round1-fixes`) |
| U3 | Low | validation | Single-char identifiers rejected (regex `{1,39}` → min 2) but the message says "starting with a letter". Fix message (or allow 1 char). | FIXED (`claude-feature/round1-fixes`) |
| U4 | Low | validation | Invalid-identifier error echoes the full offending string (tested 300 chars). Truncate to ~40. | FIXED (`claude-feature/round1-fixes`) |
| U5 | Low | diagnose | `diagnose` with no build log returns `lines_reviewed: 1, classifications: []` instead of saying there is no log. | FIXED (`claude-feature/round1-fixes`) |
| U6 | Low | planner | `:BUILD` task is assigned role `debugger`. Arguably `coder`/`release`; debugger should own the failure path. Design question. | OPEN |
| U7 | Med | UI clarity | UI exposes plan/approve/generate/request-build/grant/deny/build but **no validate, logs or diagnose views**. After a failed build the user cannot see why from the UI. | OPEN |
| U8 | Low | UI/CLI clarity | Blocking-question message says "Update the idea in a new project" — there is no edit path, so the user must pick a new mod id. Either allow re-interpreting the idea on an unapproved project or explain the constraint. | OPEN |

### Verified OK

- Input validation: invalid mod id, shell chars in package, empty idea, duplicate identifiers, unicode/punctuation, numeric-leading ids, nonexistent project.
- Unsupported keywords (`boss`, `biome`) produce blocking questions; `approve-spec` refuses while they remain.
- `generate` is one-shot; second call refused. Never overwrites an existing workspace.
- Approvals: bogus id refused; granted approval is one-use (second `build` refused).
- Manifest tamper detection (`validate` → `CHANGED: build.gradle`).
- UI: 403 without token, with wrong token, with non-localhost `Host`; POST requires matching `Origin`; bound to 127.0.0.1 only; path traversal and unknown endpoints rejected; malformed JSON returns 400.
- UI and CLI share the same core: identical results for create → plan → approve → generate → request-build.

## Not yet tested

- `craftctl build` against a real Gradle (needs host machine).
- MCP server protocol and tool restrictions.
- `diagnose` against real failing Gradle logs.
- Skills/agents as prompts for a cold Claude Code session.
- UI rendered in a browser (only the API was exercised).
