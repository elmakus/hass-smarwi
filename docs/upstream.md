# Upstream and downstream ledger

## Repository policy

- Fork: <https://github.com/elmakus/hass-smarwi>; independently maintained releases.
- Upstream: <https://github.com/jirutka/hass-smarwi>; tracked at `upstream/master`.
- Protected release branch: `main`. PRs require passing Package checks, Tilt contract, Linter, Typechecker, HACS Validation, and Hassfest Validation against the current base, including for administrators. Force pushes and deletion are disabled. The sole-maintainer policy does not require another human approval. The local `upstream-tracking` branch tracks `upstream/master`. Preserve upstream history; do not merge fork branding into upstream topics.
- Base last refreshed before the offline P3a topic on 2026-11-06: v0.3.5, `6a528f35a695bfb5b70e5fe22eb113a163ef7999`. That check found no newer default-branch commit or open upstream PR. Neither P3a nor P3b repeated remote checks.
- Preserve MIT license notices, domain `smarwi`, serial-derived identities, and MQTT-only communication. Do not copy code from other forks to implement packaging.
- Keep parent workspace instructions, handoffs, credentials, and personal device traces out of this repository.

For an upstream-suitable fix, fetch upstream and branch from the fresh upstream base, not accumulated downstream `main`. Record its base, tests, downstream integration commit, and upstream PR status. Keep independent fixes separate; stack only real dependencies. Check for an equivalent upstream patch before applying it downstream. Our releases do not depend on upstream acceptance.

## Topics

| Topic | Base | Tests / evidence | Fork integration | Upstream status |
| --- | --- | --- | --- | --- |
| P1a: independent metadata and offline packaging | `6a528f35a695bfb5b70e5fe22eb113a163ef7999` | 10 offline unittest cases pass; 18 downloaded CI ZIP members match source bytes; production Python unchanged; read-only review found no blockers; all five CI gates pass on PR and merged `main` | `d157f56b11950dad1d05d43b105f7d82e15033ec`, [fork PR #1](https://github.com/elmakus/hass-smarwi/pull/1); topic commits `88beab5` and `96f7fa1` | Fork-only; no upstream PR |
| P2a/P8: direct tilt-only entity contract | `0c2bd0825eeea45e86cf9701aed8ea78738ea21a` | 8 entity tests with mocked commands plus 10 packaging tests pass locally on Python 3.14.10 / HA 2026.11.0 / paho-mqtt 2.1.0; all six CI gates pass on the code commit; public HA services and setup were outside this initial slice | Code commit `641f6b4a272cc5c5f833b786bde78904e2699815`, [fork PR #3](https://github.com/elmakus/hass-smarwi/pull/3) records integration history | Downstream harness baseline; no upstream PR |
| P2b/P8: public HA setup and native tilt services | `110b60961a78636dfd4089a99bd843cb3f0cd9a3` | 18 new public-interface cases pass; full suite has 36 passes and one strict expected failure for the known 1% wire defect; HA and official pytest-homeassistant fixtures both pinned to 2026.11.0; real SMARWI platforms and HA MQTT callbacks, mocked Paho transport; production Python unchanged; independent review accepted the narrowed xfail boundary | Code commits `cf08f31` and `ae831e4`; [fork PR #5](https://github.com/elmakus/hass-smarwi/pull/5) records integration history and CI gates | Downstream harness expansion; no upstream PR |

### P3a local offline topic

- Downstream working branch: `fix/keyval-message-validation`, based on `3001ce5b30018a30ef81c6f3536794b1c0b07d94`. Not integrated into `main` or published. Independent read-only review found no blockers in this bounded local change; the reviewer did not independently run tests.
- Production scope: tolerate empty lines in the shared key/value decoder; reject malformed records atomically at both MQTT callbacks; catch advanced-configuration integer parse failures; ignore empty/unknown-only status and configuration with no writable records. Preserve values, first-colon splitting, unknown integer configuration keys and existing nonempty snapshot replacement. No command, Stop, settings-write or availability changes.
- An inherited diagnostic also required importing the same `DeviceInfo` class directly from its defining HA module. This is an import-only compatibility correction, not a new device model.
- Regressions failed before the fix. Twelve decoder cases and eighteen additional public MQTT cases now pass; local full suite: 66 passes, one strict expected failure for the separate 1% defect, plus 25 unittest subtests. Ruff lint/scoped formatting and installed dependency checks pass. Active diagnostics have no primary errors; three inherited unchecked status-number warnings remain.
- This is a syntax/rejection-policy slice, not P3 acceptance. At that checkpoint, status numeric validation remained open; P3b below addresses conversion/packing only. Full-versus-partial semantics remain unresolved. No current upstream, contributor-documentation, remote-CI or hardware check occurred. Before any upstream submission, fetch upstream, inspect equivalent patches, and prepare a fresh isolated production topic rather than submitting this downstream branch. No upstream PR, tag, release or deployment exists for P3a.

### P3b local offline topic

- Downstream working branch: `fix/status-numeric-validation`, based on local P3a commit `5a1016ce5dbf0df36612f025c34a6ea337427a02`. Local topic only, not integrated into `main`, published or accepted upstream. Two independent read-only reviews found no blockers; neither reviewer executed checks. The main agent independently validated the final change.
- Production scope: atomically reject failed `s`/`rssi`/`ip` integer conversions and unrepresentable unsigned packed IPv4 before snapshot/discovery/registry/update side effects. Preserve existing `int()` syntax, empty/missing `s` fallback, unknown numeric UNKNOWN mapping, optional fields, raw strings and full replacement. No invented numeric bounds, field completeness, position/boolean policy or command/settings/availability changes.
- Twenty new synthetic MQTT cases: fourteen initial/registered rejection-and-recovery cases, five accepted-conversion cases and one missing-field replacement case. Corrected red run against unchanged production source: 14 failed, 6 passed, 10 conversion-exception teardown errors. Final full suite: 86 passed, one unchanged strict 1% xfail, 25 passing unittest subtests and five third-party deprecation warnings; selected new cases: 20 passed. Ten package unittests, scoped Ruff formatting/lint and offline dependency check (122 packages) pass. Two-file active diagnostics have no primary findings; three inherited getter conversion warnings and 111 informational spelling findings remain auxiliary.
- Only existing network-blocked fixtures and mocked Paho transport were used. No upstream refresh, external-documentation/remote-CI check, live HA/MCP, real broker/device, installation or physical test. See [development](development.md#atomic-status-numbers-p3b-local-topic) for exact policy, commands and limits. The legacy CLI basedpyright job was not run locally. This is not complete P3 or release acceptance.

### Formatting follow-up

The `chore/stable-formatting` topic normalizes the existing packaging script and test formatting, pins Ruff to `0.14.3`, adds `ruff format --check scripts/build_release.py tests` to the required Linter job, and corrects Python-script indentation in `.editorconfig`. AST comparisons confirm that the three formatted Python files keep their behavior. The old top-level Ruff `pyupgrade` settings move to the supported `lint.pyupgrade` table without changing their value. Production integration files remain unchanged.

### P1a CI evidence (2026-11-06)

- PR: [Package](https://github.com/elmakus/hass-smarwi/actions/runs/42233695833), [Lint/type checking](https://github.com/elmakus/hass-smarwi/actions/runs/42233695876), [HACS/hassfest](https://github.com/elmakus/hass-smarwi/actions/runs/42233695668).
- Integrated `main`: [Package](https://github.com/elmakus/hass-smarwi/actions/runs/42234010585), [Lint/type checking](https://github.com/elmakus/hass-smarwi/actions/runs/42234010824), [HACS/hassfest](https://github.com/elmakus/hass-smarwi/actions/runs/42234010744).
- The initial PR's new builder failed Ruff's `TRY004`; topic commit `96f7fa1` corrected the metadata type exception. Fresh local tests and all CI gates passed before merge. No checks were bypassed.
- No fork release or new tag was created. Only a development Actions artifact was built and inspected. Artifact/log retention is finite; reproduce the archive from the recorded commit with the documented builder.

### P2a CI evidence (2026-11-06)

Code commit `641f6b4` passed [Tilt contract](https://github.com/elmakus/hass-smarwi/actions/runs/42243544912), [Package](https://github.com/elmakus/hass-smarwi/actions/runs/42243544681), [Lint/type checking](https://github.com/elmakus/hass-smarwi/actions/runs/42243544699), and [HACS/hassfest](https://github.com/elmakus/hass-smarwi/actions/runs/42243544909). The new tilt contract is also a required protected-branch check. These are direct entity tests with mocks, not a live installation or physical test result.

## Intentional P1a divergence

- Fork owner, support, documentation, HACS custom-repository links, and default branch point to elmakus rather than upstream. Existing copyright notices remain intact.
- Source version `0.4.0.dev0` identifies an unreleased fork baseline. It is not upstream v0.3.5 or a tested compatibility promise.
- The inherited, untested HACS minimum was removed. A tested minimum is a release gate, not inferred from the old dependency pins.
- ZIPs contain flat integration files and the unchanged root license. The builder checks exact version/asset agreement instead of rewriting a manifest from a tag.
- The package workflow produces inspection-only Actions artifacts. Automatic upload on a published GitHub release is removed until release gates pass. Workflow action references are pinned to inspected commit SHAs, repository permissions are read-only, and checkout credentials are not persisted.
- P1a left production Python unchanged. The later local P3a syntax and P3b numeric topics are described separately above. `WINDOW` and exactly the four tilt features remain; there are no standard-action aliases or UI-driven feature conversions.

P1a does not complete P1's HACS install/update acceptance. P2a protects the direct entity contract; P2b adds public config-entry setup, native tilt services, state-machine assertions and unload with simulated MQTT. Neither completes P2/P8 lifecycle/race acceptance. The new fixture sends a separate online update after discovery, so it does not validate initial cached hydration. Stop's HA state refresh still waits for telemetry; its two mocked payloads are characterization, not a physical safety pass. P3a adds local syntax regressions; P3b adds atomic numeric conversion/packing validation only. Broader status-domain semantics remain open. Telemetry freshness, 1% command encoding, stop/holding policy, settings safety, broker recovery, hardware soak, and releases remain open. See [development and release gates](development.md).
