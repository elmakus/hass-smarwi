# Upstream and downstream ledger

## Repository policy

- Fork: <https://github.com/elmakus/hass-smarwi>; independently maintained releases.
- Upstream: <https://github.com/jirutka/hass-smarwi>; tracked at `upstream/master`.
- Protected release branch: `main`. PRs require passing Package checks, Tilt contract, Linter, Typechecker, HACS Validation, and Hassfest Validation against the current base, including for administrators. Force pushes and deletion are disabled. The sole-maintainer policy does not require another human approval. The local `upstream-tracking` branch tracks `upstream/master`. Preserve upstream history; do not merge fork branding into upstream topics.
- Upstream refreshed again during the authorized publication phase on 2026-11-06: v0.3.5, `6a528f35a695bfb5b70e5fe22eb113a163ef7999`, with no newer default-branch commit or open upstream PR found. P3a/P3b initially developed offline; their later fork publication and CI are recorded separately below.
- Preserve MIT license notices, domain `smarwi`, serial-derived identities, and MQTT-only communication. Do not copy code from other forks to implement packaging.
- Keep parent workspace instructions, handoffs, credentials, and personal device traces out of this repository.

For an upstream-suitable fix, fetch upstream and branch from the fresh upstream base, not accumulated downstream `main`. Record its base, tests, downstream integration commit, and upstream PR status. Keep independent fixes separate; stack only real dependencies. Check for an equivalent upstream patch before applying it downstream. Our releases do not depend on upstream acceptance.

## Current prerelease acceptance (2026-11-07)

- Published experimental [`0.4.0.dev1`](https://github.com/elmakus/hass-smarwi/releases/tag/0.4.0.dev1), exact source `c4fe71f7e04c1c4842b088b77d1c18372efc1e04`, after protected version-candidate [PR #34](https://github.com/elmakus/hass-smarwi/pull/34). All six source-main checks across four workflows passed. Manifest/tag match; all 18 ZIP members match source/license. Only `cover.py` (local-intent [PR #33](https://github.com/elmakus/hass-smarwi/pull/33)) and `manifest.json` differ from immutable dev0 `c6017d43e37e5e00eef1e01bb0fff293ab9d942d`. Asset size/hash and candidate checks are in the [current development record](development.md#published-dev1-and-native-version-cycle-2026-11-07).
- Actual public native Marketplace `update.install` calls with explicit versions completed dev0 → dev1 → dev0 → dev1. All 18 installed hashes matched before each of three normal Core `2026.11.0` restarts; all 41 baseline entries, configured entry/device/cover identity and nine enabled settings values were preserved. Final dev1 is installed, update entity off/not in progress, closed/zero and IDLE with fixation on/tamper off; disabled diagnostics/calibrated distance remain disabled, upstream uninstalled. Final post-restart hashes match dev1; scoped structured SMARWI logs have zero entries and scoped raw logs only standard loader warnings. The baseline integration-tree backup remains preserved; this was not a full HA backup restore. See the linked record for the corrected A2 `pending-upgrade` verifier assumption.
- Initial dev0 installation accepted the normal public warning under operator authorization and reused an existing GitHub connection. Earlier authorized firmware `3.4.1-15-g3d0f` tests exercised all four native tilt actions **only on dev0**, not dev1; see the [bounded physical record](development.md#bounded-real-device-telemetry-acceptance-2026-11-07). The physical entry intentionally remains configured on dev1. No motion/Stop/Fix commands, broker outage, firmware, calibration or mechanical-setting changes occurred in the version cycle.
- This closes versioned file replacement, normal restart, configuration identity and current-configuration compatibility, not schema-migration backward compatibility, interrupted-install/restart-failure automatic rollback, full HA backup restore, legacy HACS, hardware Stop/holding/freshness or mechanical safety. No production change accompanies this documentation record. Historical sections retain their original scope; their “unreleased/no release/device” statements describe those checkpoints, not current publication. Further release and safety gates remain open.

## Topics

| Topic | Base | Tests / evidence | Fork integration | Upstream status |
| --- | --- | --- | --- | --- |
| P1a: independent metadata and offline packaging | `6a528f35a695bfb5b70e5fe22eb113a163ef7999` | 10 offline unittest cases pass; 18 downloaded CI ZIP members match source bytes; production Python unchanged; read-only review found no blockers; all five CI gates pass on PR and merged `main` | `d157f56b11950dad1d05d43b105f7d82e15033ec`, [fork PR #1](https://github.com/elmakus/hass-smarwi/pull/1); topic commits `88beab5` and `96f7fa1` | Fork-only; no upstream PR |
| P2a/P8: direct tilt-only entity contract | `0c2bd0825eeea45e86cf9701aed8ea78738ea21a` | 8 entity tests with mocked commands plus 10 packaging tests pass locally on Python 3.14.10 / HA 2026.11.0 / paho-mqtt 2.1.0; all six CI gates pass on the code commit; public HA services and setup were outside this initial slice | Code commit `641f6b4a272cc5c5f833b786bde78904e2699815`, [fork PR #3](https://github.com/elmakus/hass-smarwi/pull/3) records integration history | Downstream harness baseline; no upstream PR |
| P2b/P8: public HA setup and native tilt services | `110b60961a78636dfd4089a99bd843cb3f0cd9a3` | 18 new public-interface cases pass; full suite has 36 passes and one strict expected failure for the known 1% wire defect; HA and official pytest-homeassistant fixtures both pinned to 2026.11.0; real SMARWI platforms and HA MQTT callbacks, mocked Paho transport; production Python unchanged; independent review accepted the narrowed xfail boundary | Code commits `cf08f31` and `ae831e4`; [fork PR #5](https://github.com/elmakus/hass-smarwi/pull/5) records integration history and CI gates | Downstream harness expansion; no upstream PR |

### P3a initial offline evidence

- Downstream branch: `fix/keyval-message-validation`, based on `3001ce5b30018a30ef81c6f3536794b1c0b07d94`, code `5a1016c`. Subsequently merged through [fork PR #6](https://github.com/elmakus/hass-smarwi/pull/6), merge `24f181ef26090c215be371423a8b9b1e4e4694d4`, after all six protected checks passed. Independent read-only review found no blockers in this bounded local change; the reviewer did not independently run tests.
- Production scope: tolerate empty lines in the shared key/value decoder; reject malformed records atomically at both MQTT callbacks; catch advanced-configuration integer parse failures; ignore empty/unknown-only status and configuration with no writable records. Preserve values, first-colon splitting, unknown integer configuration keys and existing nonempty snapshot replacement. No command, Stop, settings-write or availability changes.
- An inherited diagnostic also required importing the same `DeviceInfo` class directly from its defining HA module. This is an import-only compatibility correction, not a new device model.
- Regressions failed before the fix. Twelve decoder cases and eighteen additional public MQTT cases now pass; local full suite: 66 passes, one strict expected failure for the separate 1% defect, plus 25 unittest subtests. Ruff lint/scoped formatting and installed dependency checks pass. Active diagnostics have no primary errors; three inherited unchecked status-number warnings remain.
- This is a syntax/rejection-policy slice, not P3 acceptance. At that checkpoint, status numeric validation remained open; P3b below addresses conversion/packing only. Full-versus-partial semantics remain unresolved. At that initial offline checkpoint, no current upstream, contributor-documentation, remote-CI or hardware check occurred. Later fork publication refreshed upstream and passed every protected check; no hardware test followed. Before any upstream submission, fetch upstream, inspect equivalent patches, and prepare a fresh isolated production topic rather than submitting this downstream branch. No upstream PR, tag, release or deployment exists for P3a.

### P3b initial offline evidence

- Downstream branch: `fix/status-numeric-validation`, based on P3a commit `5a1016ce5dbf0df36612f025c34a6ea337427a02`, code `d3f228b`. Subsequently merged through [fork PR #7](https://github.com/elmakus/hass-smarwi/pull/7), merge `025b2b0a169067a8532125e75a80a9c94ad186b5`. Required CI exposed three intentionally unused call results; `b9abc71` assigns them to `_` without changing behavior or suppressing a rule. All six protected checks then passed. No upstream acceptance is claimed. Two independent read-only reviews found no blockers; neither reviewer executed checks. The main agent independently validated the final change.
- Production scope: atomically reject failed `s`/`rssi`/`ip` integer conversions and unrepresentable unsigned packed IPv4 before snapshot/discovery/registry/update side effects. Preserve existing `int()` syntax, empty/missing `s` fallback, unknown numeric UNKNOWN mapping, optional fields, raw strings and full replacement. No invented numeric bounds, field completeness, position/boolean policy or command/settings/availability changes.
- Twenty new synthetic MQTT cases: fourteen initial/registered rejection-and-recovery cases, five accepted-conversion cases and one missing-field replacement case. Corrected red run against unchanged production source: 14 failed, 6 passed, 10 conversion-exception teardown errors. Initial P3b full suite: 86 passed, one strict 1% xfail, 25 passing unittest subtests and five third-party deprecation warnings; selected new cases: 20 passed. Ten package unittests, scoped Ruff formatting/lint and offline dependency check (122 packages) pass. Two-file active diagnostics have no primary findings; three inherited getter conversion warnings and 111 informational spelling findings remain auxiliary.
- Only network-blocked fixtures and mocked Paho transport were used for runtime tests. The initial development was offline; subsequent repository/documentation refresh and required CI were authorized separately. No live HA/MCP, real broker/device, installation or physical test occurred. See [development](development.md#atomic-status-numbers-p3b-initial-offline-checkpoint) for exact policy and historical counts. Current-HA strict typing is now reproducible locally. This is not complete P3 or release acceptance.

### Subsequent independent topics (2026-11-06)

Each production topic had a tests-first local regression, independent read-only review and main-agent validation. Reviewer source inspection is not reviewer-executed testing. Merged PRs passed all six protected checks on the current base; no administrator bypass or protection change was used.

| Topic / original local base | Scope and decisive evidence | Fork integration / code | Upstream status |
| --- | --- | --- | --- |
| P3c / `025b2b0` | Literal `c/o` observed closure; other values remain unknown. Seven MQTT cases, four red before fix. | [#8](https://github.com/elmakus/hass-smarwi/pull/8), merge `cb511b2`, code `bbf34a2` | No upstream PR |
| P4a / `bbf34a2` | One-line cache hydration after listener attachment; three deterministic setup/update/unload/reload cases failed before fix. No post-attachment online refresh masks initialization. | [#9](https://github.com/elmakus/hass-smarwi/pull/9), merge `f7bd433`, code `017985b` | No upstream PR |
| P3d / `d3f228b` | Matched discovery segment needs `%` and a nonempty serial before constructing/subscribing. Three red/green MQTT cases; valid recovery and duplicate discovery checked. | [#10](https://github.com/elmakus/hass-smarwi/pull/10), merge `2cc1193`, code `6277ce2` | No upstream PR |
| Current-HA tooling / `025b2b0` | Python 3.14.10/HA 2026.11.0, native Probatio and no obsolete stubs/CONNECTION_CLASS. Keep basedpyright 1.10.4/mode all; 18 current-HA baseline errors become zero. Eight non-config modules AST-identical. One documented selector-registry annotation exception, no global disabling. | [#11](https://github.com/elmakus/hass-smarwi/pull/11), merge `ad97141`, code `a88f658` | Fork tooling; no upstream PR |
| P5a / `712701d` | Literal Remote ID validation and native/legacy/in-progress duplicate prevention; 41 public flow cases, 34 red before fix. Existing entries unchanged. | [#12](https://github.com/elmakus/hass-smarwi/pull/12), merge `af34dd8`, code `fbd931e` | No upstream PR |
| P6a / `ad97141` | `1% -> open;1`, zero closes, default/100 unchanged. Ordinary exact regression replaces strict xfail; no remaining expected failure for this defect. | [#13](https://github.com/elmakus/hass-smarwi/pull/13), merge `98d1cc1`, code `640a519` | No upstream PR |
| P4b / `017985b` | Native broker/session/status availability gate; seven Paho callback cases, two-device/non-cover cleanup and explicit retained replay limits. Retained online is not freshness. | [#14](https://github.com/elmakus/hass-smarwi/pull/14), merge `8d9bc6c`, code `c4d6982` | No upstream PR |
| P6b / `c4d6982` | Always forward explicit native requests; six inferred-equality cases and three delayed-ACK/Stop interleavings. Preserve original before-await intent. Rejected after-await candidate was never published; it could resurrect cleared intent. | [#15](https://github.com/elmakus/hass-smarwi/pull/15), merge `46f1034`, code `fc68be7` | No upstream PR |
| P6c / `6c07e79` | Reporting-only: accepted binary closed => zero, otherwise unknown. Direct matrix and near-frame/target/Stop regressions; movement-direction heuristics remain unresolved. Combined test preconditions preserve private inference checks rather than requiring public estimates. | [#16](https://github.com/elmakus/hass-smarwi/pull/16), merge `cbcb80a`, code `7d5264b`; test guard cleanup `cf30a8f` | No upstream PR |
| P4c / `a588a63` | Typed entry-owned device dictionary, native runtime cleanup, independent entries/reload/rejected unload/setup retry tests. No coordinator/model/new runtime module. | [#17](https://github.com/elmakus/hass-smarwi/pull/17), merge `f993fe5`, code `04a9872` | No upstream PR |
| P6d / `7cbe99a` | Identity-owned local failure/cancellation cleanup, same-target supersession and actual Stop/terminal invalidation interleavings. No rollback, success-ACK mutation, retry or transport policy. | [#18](https://github.com/elmakus/hass-smarwi/pull/18), merge `017732e`, code `9cee5f2` | No upstream PR |
| P4d / `b2dd8e0` | Transactional device subscription acquisition and identity-owned reservation rollback. Ten initial red cases; 17 final guarded public MQTT cases cover retry, duplicates, retained-marked status, cancellation, successful/rejected unload and entry isolation. Native subscribe is currently synchronous; injected suspension is robustness evidence only. | [#20](https://github.com/elmakus/hass-smarwi/pull/20), merge `fce3894`, code `144b1b9` | No upstream PR |
| P4e / `41a974b` | Tests-only pending tilt-service completion across unload/reload and immediate rejected unload. Six paired service/outcome cases; replacement ownership/state, one effective active update and no extra publishes. No reproduced production defect or policy change. | [#22](https://github.com/elmakus/hass-smarwi/pull/22), code `cb7766c` | Downstream characterization; no upstream PR |
| P4f / `43c22f5` | Native setup retry for false MQTT-client readiness, before resource allocation. Three independently reproduced red cases become green: scheduled recovery, unload/removal cancellation and active-entry preservation. No broker reconnect or command-retry policy. | [#23](https://github.com/elmakus/hass-smarwi/pull/23), code `9d03b9c` | No upstream PR |

### Idle-Stop local-intent cleanup: original unreleased checkpoint (2026-11-07)

Based on `806c19b272ec19b189dc3b5a42a63f83fd121249`, this changes only
local requested-target/owner cleanup before the cached-IDLE Stop guard. Three
native service sequences reproduce a stale direction override after a completed
request and idle Stop; three added delayed-publication cases reproduce retained
targets. The prior three moving cases pass. All six regressions now pass, plus
three completed-request boundary characterizations and three direct late-outcome
subtests. Full suite: **256 tests and 101 subtests**, five inherited warnings;
eleven package tests, Ruff and strict production typing pass.

The earlier direct idle-Stop-preserves-owner characterization is intentionally
updated; unchanged-status/release/availability policy remains tested. No physical
command decision, observed movement, raw telemetry or public percentage changes.
Early physical Stop, retraction, freshness and general direction inference remain
unproven. At this original checkpoint no live system, release, deployment or upstream
PR accompanied the topic. It subsequently merged as [fork PR #33](https://github.com/elmakus/hass-smarwi/pull/33)
and is included in published dev1; no upstream PR is claimed.
The [local-intent record](development.md#local-intent-after-stop-with-cached-idle-2026-11-07)
separates it from the immutable published `0.4.0.dev0` source `c6017d4`.

### Native Marketplace package contract (2026-11-07)

[Fork PR #30](https://github.com/elmakus/hass-smarwi/pull/30), code `34b1852`,
is based on `ddae9473e2e8596b6df48e780433abdfbae06708`.
Five offline cases reuse the existing candidate ZIP builder, official HA fixture
and real native Marketplace prepare/write/backup code. They cover exact first and
replacement writes with stale-file removal, old-tree restoration after invalid
written domain/version, and failed first-write cleanup after invalid nested layout.
Only download response bytes are replaced; an exact three-URL sequence and socket
and DNS guards bound the test. No production, metadata, dependency, workflow or
builder change is included. No upstream PR, release or deployment follows.

Main independently verified **246 tests and 98 subtests, no xfails**, five inherited
third-party warnings; eleven package unittests, Ruff lint/scoped format, pinned
strict basedpyright 1.10.4 with zero errors/warnings/notes in production scope,
122-package compatibility and diff checks pass. These are characterization tests,
not red-before-fix regressions. The [development boundary](development.md#offline-native-marketplace-package-contract)
excludes public installation, persisted version/cache/import, real downloads,
accounts/releases, legacy HACS, interrupted recovery and physical acceptance.
Native distribution remains an incomplete release gate.

### Actual manual installation acceptance (2026-11-07)

On an operator-authorized HAOS/Core `2026.11.0` instance, exact candidate
`d77460b` files were installed, replaced with reference `ce8d31a`, then replaced
with the current candidate again. Each of the three steps verified all 18 members
against exact Git blobs, restarted HA and opened/cancelled the public SMARWI user
flow without entering a Remote ID. Final config validation passed and current
files remained installed, without a SMARWI config entry or physical controller.
Previous trees were preserved. The standard custom-integration startup warning is
not an integration exception; final structured SMARWI error search was empty.

Both snapshots use `0.4.0.dev0`; this proves manual file replacement/import/form
behavior, not versioned release updates, migrated-state compatibility or native
Marketplace/HACS. No tag, release asset or account-warning bypass was used. See
[actual manual installation](development.md#actual-manual-installation-acceptance-2026-11-07)
for the exact boundary. No production source or test-suite change accompanies this
acceptance record.

### Actual synthetic MQTT lifecycle (2026-11-07)

Installed `d77460b` passed a separate real HA/EMQX test with one random synthetic
Remote ID/serial, a real user config entry and native MQTT publish/dump services.
Exactly one WINDOW/four-tilt-feature cover reported closed/zero and open/unknown.
Native actions produced ordered `open;1`, `open;100`, `close`, `stop`, `stop`
callbacks plus four expected `lcfa` reads. Offline/cache recovery, a bounded
malformed-status preservation/recovery case and native same-entity reload passed.
Cleanup removed the test entry and 12 states, preserved all 40 original entry IDs
and left no retained test telemetry at a fresh scoped subscription.

Observations use the same HA client's broker callbacks, not an independent MQTT
client or physical acknowledgement. The deliberate malformed status warned as
expected; native HA also warned about the deprecated unscoped registry lookup,
which requires a separate compatibility fix. No broker failure/settings,
physical controller, release or native installer was tested. See the
[actual synthetic MQTT boundary](development.md#actual-synthetic-mqtt-lifecycle-2026-11-07).

### Entry-scoped registry lookup (2026-11-07)

Based on `d77460b`, the production change replaces only the deprecated unscoped
metadata lookup with native `async_get_device_by_identifier` and the owning config
entry ID. A public HA/MQTT regression with duplicate native identifiers under two
entries failed before the change because another entry's metadata was modified.
Parent independently reproduced that failure and verified **247 tests and 98
subtests passing**, no xfails; package11, Ruff/scoped format, production-only strict
basedpyright1.10.4 zero findings, 122 compatible dependencies and diff checks.
Both changed Python paths have clean primary-server probes. Independent source
review found no issues, without executing tests. Identities and controls are
unchanged; no upstream PR or release is included.

### Raw error-code diagnostic (2026-11-07)

[Fork PR #28](https://github.com/elmakus/hass-smarwi/pull/28), based on `ce8d31a`,
code `f8f9459` adds only the documented `e` field, raw getter,
optional diagnostic sensor and English name. Ten new guarded HA/MQTT cases were red
before implementation (missing entity) and pass after it. No fault-code meanings,
problem boolean, movement, Stop/Fix, settings or availability change is inferred.
The [roadmap assessment](development.md#roadmap-assessment-2026-11-07) separates this
supported diagnostic from unverified firmware features and remaining release gates.
No upstream PR, release or deployment accompanies this downstream feature.

Combined local checkpoint after P6d integration: **188 passed, 57 passing subtests, no xfails**, five third-party deprecation warnings. Ten package unittests, Ruff lint/scoped formatting, offline installed-dependency check (122 compatible packages) and strict current-HA basedpyright (zero errors/warnings) pass. All 18 development ZIP members match source bytes with the unchanged MIT license. Two independent P6d reviewers found no blockers; main reran the combined suite. The final all-server LSP sweep was inconclusive, not universally clean; explicit-interpreter CLI evidence is confirmed. Counts describe the combined production tree at `017732edb81ca082a6de6eaa06de24464cf583df`, not every historical topic in isolation. An independent local evidence/privacy audit found no actionable issues in the protocol, development notes or ledger; it did not independently execute tests or query GitHub. No live HA/device, HACS install/update, supported minimum or hardware acceptance is implied.

### P4d combined verification and limits

After initialization recovery, main independently reran the full suite: **205 passed, 57 passing subtests, no xfails**, with five existing third-party deprecation warnings. Ten package unittests, Ruff lint/scoped formatting, strict basedpyright1.10.4 (zero errors/warnings/notes), installed dependency check (122 compatible packages) and `git diff --check` pass. Three changed Python files pass active primary-server diagnostics; this does not replace the earlier inconclusive all-server result with a universal claim. All 18 development ZIP members match committed source bytes, including the unchanged MIT license. Two fresh independent reviewers found no blocking issues; neither executed tests.

All six protected PR checks passed on `144b1b9` against current base `b2dd8e0`: [Package](https://github.com/elmakus/hass-smarwi/actions/runs/42294280485), [Tilt contract](https://github.com/elmakus/hass-smarwi/actions/runs/42294280515), [Linter/Typechecker](https://github.com/elmakus/hass-smarwi/actions/runs/42294280531), [HACS/Hassfest](https://github.com/elmakus/hass-smarwi/actions/runs/42294280747). Merge `fce3894494ea7b0c6f3b292e357a6d23c3172013` used no administrator bypass or protection change. No upstream PR, tag, release or deployment followed.

The Event gate retains original HA MQTT jobs rather than a replay scheduler. It suppresses provisional/closed-attempt handlers but does not cancel original handlers already executing after commit, establish arbitrary queued discovery/unload safety, or recover an acquisition handle that native code never returned. Native once-owned cleanup callbacks are assumed to complete normally; injected removal failures remain untested. Failed attempts retain an inert drained unload closure until entry teardown. No command, Stop/Fix, direction, settings, identity or transport policy changed. Real broker replay, hardware, supported minimum and disposable install/update/rollback remain gates. See [development](development.md#discovery-initialization-recovery-p4d) for the bounded regression scope.

### P4e pending-service characterization

Main independently reran the exact tests-only patch: **211 passed, 57 passing subtests, no xfails**, with five existing third-party deprecation warnings. Ten package unittests, Ruff lint/scoped formatting, strict basedpyright1.10.4 (zero errors/warnings/notes), 122-package compatibility and `git diff --check` pass. The changed Python test has a clean active primary-server probe; the strict CLI project covers production modules, not tests. Two fresh independent reviewers found no blockers in source and supplied evidence; neither executed tests.

All production, packaging, workflow and dependency files are unchanged from base `41a974b`. Success, failure and cancellation are paired with native open, close and set-tilt respectively in both lifecycle paths, not a full service/outcome matrix. The caller-owned service survives unload in pinned HA; mocked publication supplies cancellation. Rejected unload is immediate, before removal. Partial unload, other HA versions, real broker delivery/replay and physical safety remain gates. The README warning and cover description now match the already accepted software fixes and observed-only public tilt reporting; no release, deployment or quality-tier claim follows.

### P4f MQTT-client setup retry

The false result from the existing readiness helper previously produced native `SETUP_ERROR`, without automatic recovery. The minimal branch now raises `ConfigEntryNotReady`; HA owns logging, backoff, retry and cancellation. Successful setup and helper exception propagation are unchanged. Parent independently reproduced three red cases against unchanged source, then reran the exact reviewed fix: **214 passed, 57 passing subtests, no xfails**. Ten package unittests, Ruff lint/scoped format, strict basedpyright1.10.4 (zero errors/warnings/notes in its production-module scope), 122-package compatibility and `git diff --check` pass. Both changed Python files have clean active primary-server probes. Two independent reviewers found no blockers in source/evidence; neither executed tests.

Readiness false/true is injected at the documented helper boundary. No actual helper timeout, ordinary startup race or broker outage was reproduced. A loaded MQTT client passes without broker connectivity; missing/disabled/fatally broken MQTT still needs correction. The inspected official core sample has mixed retry/fatal policy, not a prevalence claim or installed-wheel/commit equivalence. No custom timer, loop, queue, command/control/settings change, dependency, supported-version claim, deployment or release is added.

### Synthetic hosted package and checkpoint acceptance

- [PR #24](https://github.com/elmakus/hass-smarwi/pull/24), code `742499d`, adds a separate manual-only hosted harness, native HA/MQTT client, helper tests and documentation. [PR #25](https://github.com/elmakus/hass-smarwi/pull/25), code `91ee698`, folds the identical type-check command to remove an inherited line-length finding. [PR #26](https://github.com/elmakus/hass-smarwi/pull/26), code `afb1c88`, corrects probe framing/empty-IPv6 EOF handling and verified stock-image metadata compatibility, with red/green regressions and source-location-only failure diagnostics. No containment rule is suppressed.
- First authorized [run 42310285561](https://github.com/elmakus/hass-smarwi/actions/runs/42310285561) was blocked before application stages, with successful cleanup. It did not identify the earliest guard. Later deterministic source regressions and SHA256-verified public image configuration established the corrections; do not claim an observed unique first-run cause.
- [Run 42312152414](https://github.com/elmakus/hass-smarwi/actions/runs/42312152414), harness `16ac338`, passed the original exact A → B → matching-A byte-restoration sequence. [PR #27](https://github.com/elmakus/hass-smarwi/pull/27), code `e6fa58c`, adds the narrow differentiating retained-state assertion. Its reviewed-branch [run 42315158582](https://github.com/elmakus/hass-smarwi/actions/runs/42315158582) passed: A ended closed, B ended open, and restored A received retain-flagged closed status plus HA closed/zero before fresh fixture telemetry. Main independently verified artifact digests, installed-tree hashes against exact Git blobs, stable identity, checkpoint bytes, containment and exact-resource cleanup.
- Both successful runs used A `43c22f5a3c427aa46040f175f770d3dfd0f016b8` and B `635017321dab8c29bbeff5f5223bfe9461cdffd1`, both `0.4.0.dev0`; actual HA2026.11.0/Python3.14.10/Mosquitto2.0.22/Paho2.1.0/aiohttp3.14.5/aiohasupervisor0.8.1/Docker28.0.4. A and B are fixed historical snapshots, not automatic current-main/future-release acceptance. Production integration, metadata and dependencies remain unchanged by these harness topics.
- Final local scope: **230 tests,98passing subtests,no xfails**, five inherited third-party warnings; package10/helper16;Ruff/scopedformat9files;strictbasedpyright1.10.4zeroerrors/warnings/notes in production-module scope;122compatiblepackages;diff checks. Three changed Python primary probes are clean; auxiliary findings and earlier editor-resolution limits are not universal clean-LSP evidence. Two independent retained source reviews accepted the retained-state patch without executing checks. The workflow remains manual, not a required broker test on every push/PR.
- Independent proportionality assessment favors retaining the bounded dependency-free gate, not a generic testing platform. Frameworks can replace some lifecycle/client plumbing but leave most provenance/state/native-interface/containment/evidence responsibilities. Existing builder and official fixtures are reused; avoid framework migration, generic ref inputs, expanding smoke duplication or a layout abstraction until it pays for itself.
- The new proof is one paired synthetic broker/HA-state observation, not an independent trace of HA's causal update path, general replay/freshness, backward migrated-state compatibility, native HACS/Marketplace install/update/downgrade, HA backup restore, firmware or physical acceptance. No live HA/device, production network, account connection, tag or release was involved. See [development](development.md#manual-synthetic-hosted-acceptance) for the exact boundary and finite artifact retention.

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
- Source version `0.4.0.dev0` originally identified an unreleased fork baseline and now identifies the immutable earlier experimental prerelease; current `0.4.0.dev1` includes the local-intent fix. It is not upstream v0.3.5 or a tested compatibility promise.
- P1a removed the inherited, untested HACS minimum. The current-stable policy now declares tested development floor `2026.11.0`, aligned with the runtime, strict checker and official fixtures. Older HA compatibility is outside scope; the floor does not establish native installer or physical acceptance.
- ZIPs contain flat integration files and the unchanged root license. The builder checks exact version/asset agreement instead of rewriting a manifest from a tag.
- The package workflow produces inspection-only Actions artifacts. Automatic upload on a published GitHub release is removed until release gates pass. Workflow action references are pinned to inspected commit SHAs, repository permissions are read-only, and checkout credentials are not persisted.
- P1a left production Python unchanged. Later parser, lifecycle, configuration and command/reporting topics are tracked separately above. `WINDOW` and exactly the four tilt features remain; there are no standard-action aliases or UI-driven feature conversions.

P1a does not complete HACS install/update acceptance. The original P2b fixture does not itself prove cached hydration; separate deterministic P4 tests now cover it and bounded native broker/lifecycle transitions. Broader lifecycle races and general real retained/session replay remain unproven; the bounded synthetic retained-checkpoint result above does not close those gates. Stop's state refresh still waits for telemetry and two mocked payloads are not a physical safety pass. The 1% encoding defect is fixed; unsupported public percentages are removed, and local publish-failure intent cleanup is covered by P6d, but private direction inference, command execution ordering, Stop-before-motion, release/disconnect invalidation, settings safety, firmware semantics, freshness, hardware soak and further release acceptance remain separate gates; older HA compatibility is outside scope. See [development and release gates](development.md) and the [protocol evidence boundary](protocol.md).
