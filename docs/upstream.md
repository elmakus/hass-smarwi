# Upstream and downstream ledger

## Repository policy

- Fork: <https://github.com/elmakus/hass-smarwi>; independently maintained releases.
- Upstream: <https://github.com/jirutka/hass-smarwi>; tracked at `upstream/master`.
- Protected release branch: `main`. PRs require passing Package checks, Tilt contract, Linter, Typechecker, HACS Validation, and Hassfest Validation against the current base, including for administrators. Force pushes and deletion are disabled. The sole-maintainer policy does not require another human approval. The local `upstream-tracking` branch tracks `upstream/master`. Preserve upstream history; do not merge fork branding into upstream topics.
- Base inspected on 2026-11-06: v0.3.5, `6a528f35a695bfb5b70e5fe22eb113a163ef7999`. No newer default-branch commit or open upstream PR was found.
- Preserve MIT license notices, domain `smarwi`, serial-derived identities, and MQTT-only communication. Do not copy code from other forks to implement packaging.
- Keep parent workspace instructions, handoffs, credentials, and personal device traces out of this repository.

For an upstream-suitable fix, fetch upstream and branch from the fresh upstream base, not accumulated downstream `main`. Record its base, tests, downstream integration commit, and upstream PR status. Keep independent fixes separate; stack only real dependencies. Check for an equivalent upstream patch before applying it downstream. Our releases do not depend on upstream acceptance.

## Topics

| Topic | Base | Tests / evidence | Fork integration | Upstream status |
| --- | --- | --- | --- | --- |
| P1a: independent metadata and offline packaging | `6a528f35a695bfb5b70e5fe22eb113a163ef7999` | 10 offline unittest cases pass; 18 downloaded CI ZIP members match source bytes; production Python unchanged; read-only review found no blockers; all five CI gates pass on PR and merged `main` | `d157f56b11950dad1d05d43b105f7d82e15033ec`, [fork PR #1](https://github.com/elmakus/hass-smarwi/pull/1); topic commits `88beab5` and `96f7fa1` | Fork-only; no upstream PR |
| P2a/P8: direct tilt-only entity contract | `0c2bd0825eeea45e86cf9701aed8ea78738ea21a` | 8 entity tests with mocked commands plus 10 packaging tests pass locally on Python 3.14.10 / HA 2026.11.0 / paho-mqtt 2.1.0; all six CI gates pass on the code commit; public HA services and setup were outside this initial slice | Code commit `641f6b4a272cc5c5f833b786bde78904e2699815`, [fork PR #3](https://github.com/elmakus/hass-smarwi/pull/3) records integration history | Downstream harness baseline; no upstream PR |
| P2b/P8: public HA setup and native tilt services | `110b60961a78636dfd4089a99bd843cb3f0cd9a3` | 18 new public-interface cases pass; full suite has 36 passes and one strict expected failure for the known 1% wire defect; HA and official pytest-homeassistant fixtures both pinned to 2026.11.0; real SMARWI platforms and HA MQTT callbacks, mocked Paho transport; production Python unchanged; independent review accepted the narrowed xfail boundary | Code commits `cf08f31` and `ae831e4`; [fork PR #5](https://github.com/elmakus/hass-smarwi/pull/5) records integration history and CI gates | Downstream harness expansion; no upstream PR |

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
- Production Python is unchanged. `WINDOW` and exactly the four tilt features remain; there are no standard-action aliases or UI-driven feature conversions.

P1a does not complete P1's HACS install/update acceptance. P2a protects the direct entity contract; P2b adds public config-entry setup, native tilt services, state-machine assertions and unload with simulated MQTT. Neither completes P2/P8 lifecycle/race acceptance. The new fixture sends a separate online update after discovery, so it does not validate initial cached hydration. Stop's HA state refresh still waits for telemetry; its two mocked payloads are characterization, not a physical safety pass. Telemetry freshness, 1% command encoding, stop/holding policy, settings safety, broker recovery, hardware soak, and releases remain open. See [development and release gates](development.md).
