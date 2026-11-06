# Development and release gates

See the [development MQTT protocol and safety boundaries](protocol.md) for evidence-backed topics, payloads and verification limits.

## Current status

This is an independently maintained, MQTT-only fork of `jirutka/hass-smarwi`, based on upstream v0.3.5 (`6a528f35a695bfb5b70e5fe22eb113a163ef7999`). Parser, state-reporting, lifecycle and configuration fixes are independent topics. The [upstream ledger](upstream.md) records their fork PRs, exact scope and publication status. Historical baseline counts below are not current totals.

The source version is `0.4.0.dev0`, not a published or hardware-tested release. There is no validated Home Assistant support range or firmware matrix. The inherited `homeassistant: 2024.1.0` HACS declaration was removed because it was not backed by tests. Omitting that filter does not mean every Home Assistant version works. A tested minimum must be declared before publishing a release.

The integration domain remains `smarwi`. One `WINDOW` cover retains exactly `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION`, and `STOP_TILT`. Standard cover controls, standard-action aliases, HTTP control/polling/fallback, dashboard dependencies, and additional actuator entities are outside scope.

## Current behavior and evidence boundary

- Validate status numbers before snapshot replacement, entity discovery, registry work or update dispatch. Reject malformed messages atomically; do not invent mandatory complete snapshots, merging, firmware ranges or a state-code allowlist.
- Interpret only literal `pos:c`/`pos:o` as observed closed/open. Public tilt is zero only for accepted closed telemetry, including cache; otherwise it is unknown. Requested targets and near-frame estimates are not measured percentage feedback.
- Hydrate newly attached entities from cache after listener registration. Broker loss clears the session online observation without discarding telemetry. Reconnect alone cannot restore availability; retained online replay is an observation, not fresh liveness proof.
- Validate Remote ID as a literal MQTT segment without silent normalization. Native identity/in-progress checks and stored-data matching prevent duplicate new and legacy entries without modifying existing entries.
- Route 1% to `open;1`, zero to `close`, and every explicit tilt request to the existing command path even at an inferred equal position. Install requested intent before awaited publication; a late acknowledgement must not restore intent cleared by an actual Stop invalidation.
- On publication failure/cancellation, discard only the request that still owns the current local intent. Identity ownership distinguishes successive requests even at the same target. Do not restore an older target, retry automatically, change observed motion or interpret failure as proof of non-delivery. Existing Stop/terminal invalidation conditions remain unchanged.
- Keep runtime device maps owned by typed config entries, with native unload/reload cleanup and tests for independent entries and bounded setup/unload failures.
- Roll back failed/cancelled device subscription initialization without poisoning discovery. Preserve the provisional duplicate guard; run MQTT handlers only after all acquisitions succeed, and suppress handlers from abandoned attempts. Drain each returned native cleanup handle once.

All public-interface tests use official HA fixtures and mocked Paho transport with explicit network guards. No HA server starts or live controller is installed. Passing them does not prove device execution, target accuracy, broker replay boundaries or safe physical Stop/holding. Retained telemetry remains last known.

Private motion/direction estimates remain inherited and unverified. The `OPENING` phase cannot simply be equated to physical opening toward every target. Stop-before-motion, unchanged idle telemetry, release/disconnect intent invalidation, settings transactions and physical recovery remain separate gates. Native HA tilt-toggle opens at reported zero and closes when tilt is unknown; removing stale zero can change that default branch. Use explicit native actions when intent matters. No dashboard or standard-action alias compensates for these limits.

## Latest combined local verification (2026-11-06)

The combined source checkpoint passes **211 tests and 57 subtests, with no xfails** on Python `3.14.10`, HA/official `pytest-homeassistant` `2026.11.0` and Paho `2.1.0`. Five third-party aiohttp/backoff deprecation warnings remain visible. This is one tested development baseline, not a declared HA minimum or firmware matrix.

```sh
.venv/bin/python -m pytest -q --tb=short --show-capture=no
python3 -m unittest discover -s tests -p test_package.py -v
.venv-tests/bin/ruff check .
.venv-tests/bin/ruff format --check scripts/build_release.py tests
.venv/bin/uv tool run --offline --from basedpyright==1.10.4 basedpyright --pythonpath .venv/bin/python --project pyproject.toml
.venv/bin/uv pip check --offline --python .venv/bin/python
git diff --check
```

The ten package unittests, pinned strict checker (zero errors/warnings), Ruff, scoped formatting and installed-dependency check (122 compatible packages) pass. The offline tool command assumes its pinned tool is already cached; initial dependency/tool installation can need network access. Reuse existing environments and do not start `scripts/develop`.

Main independently reran the combined checks for the tests-only pending-service characterization. Two fresh independent reviewers found no blockers; they inspected source and evidence but did not execute tests. Active primary-server diagnostics checked the changed Python test file with zero findings and no inconclusive outcome. The earlier 14-file all-server recheck was push-only/inconclusive, not a universal clean-LSP result. Earlier interpreter-resolution findings and actual test-assertion issues are recorded in the ledger; no diagnostic rule was globally disabled. The explicit-interpreter strict CLI result remains independently confirmed for its production-module scope, not test-file coverage.

A development ZIP was also built without overwriting an existing output: all 18 members matched current source bytes, including the unchanged MIT license. This checks packaging, not HACS installation or deployment. Fork CI and merge status are recorded per PR in the ledger; local green results alone do not authorize a release.

## Discovery initialization recovery (P4d)

A failed per-device subscription acquisition previously left its provisional device in the entry cache, preventing rediscovery. Earlier acquired listeners remained effective until entry unload and could announce entities for that incomplete device. Initialization now rolls back returned handles on exception/cancellation and removes only its owned reservation. A local `asyncio.Event` gates the original HA MQTT jobs until acquisition succeeds; failure/unload wakes them to exit. A handle returned after teardown is removed immediately and initialization propagates cancellation. No custom replay scheduler or command queue is added.

Main independently reproduced ten initial red cases against unchanged production source. Seventeen final public HA/MQTT cases cover all three acquisition boundaries, error/cancellation, direct unload or retry, duplicate discovery, retained-marked status, successful/rejected unload, late-returned handles and another active entry. The seven additional cases were not separately claimed as red before production. The exact cover identity and four tilt features remain asserted.

Native HA 2026.11 public subscribe currently registers without yielding. Deliberately suspended acquisitions characterize defensive robustness, not demonstrated broker timing. The gate does not cancel original handlers already executing after commit or solve every queued discovery/unload race. Native registration failures before returning a handle and removal-callback failures remain unproven. Failed attempts keep an inert drained unload closure until entry teardown. These are software ownership guarantees, not firmware, freshness or physical-safety evidence.

## Pending native tilt-service lifecycle (P4e)

Six guarded public-HA cases hold a mocked tilt-command publish across successful native unload/reload or immediate rejected unload. Each lifecycle path resolves success, failure and publish-originated cancellation separately, paired with native open, close and set-tilt actions respectively. Adjacent tests cover shared request failure/cancellation across all three actions; this slice is not a full cross-product. In pinned HA 2026.11.0, the caller-created service task remains pending through unload.

Late completion stays with the old caller and object. The tests preserve replacement cache/device/entity ownership, telemetry, local intent and public state, with no late detached-entity write or extra publish. A changed synthetic status then produces exactly one effective active-cover update and state write. Rejected unload retains the active object and listeners. It is rejection before platform removal, not a partial-teardown test.

No production defect was reproduced and no production policy changed. Cancellation is injected by mocked publication, not caused by native unload. These are characterization tests, not red-before-fix regressions. They do not prove delivery, retraction, physical stopping, holding, real broker replay or behavior on other HA versions.

## Consistent formatting

Use Ruff `0.14.3`, pinned in `requirements.txt`, for the fork-maintained packaging script and tests. Both development requirement files now target HA `2026.11.0`; do not replace a working environment or install the historical HA 2024 pins/stubs from older revisions into it. Run these commands before committing:

```sh
ruff format scripts/build_release.py tests
ruff format --check scripts/build_release.py tests
ruff check .
```

The required **Linter** CI job runs both lint and the same format check. Formatting is therefore checked, not silently rewritten during CI. The committed files already use this format; editor reformatting with the project settings should leave no diff. `.editorconfig` explicitly keeps Python scripts space-indented while preserving the existing shell-script tab rule. Do not hide recurring formatter changes with stash or assume-unchanged flags: format and commit them with the relevant topic.

The formatting check deliberately covers only `scripts/build_release.py` and `tests/`; it does not reformat inherited production integration files or change actuator behavior.

## Offline package checks

Run these commands from the repository root. Python 3.13 and Git are sufficient; no third-party packages, HA instance, MQTT broker, or device are needed.

```sh
python3 -m unittest discover -s tests -p test_package.py -v
python3 scripts/build_release.py --tag 0.4.0.dev0
```

The builder creates `dist/smarwi.zip`, with a flat integration root and the original root `LICENSE`. It uses tracked integration source, translations, and PNG brand assets. It rejects unexpected tracked files, symlinks, missing required assets, mismatched tags, and mismatched HACS filenames. It ignores untracked local files and never packages repository metadata, parent workspace files, or the whole checkout. New integration files must be tracked before packaging; adding a new runtime file type requires updating the allowlist and tests.

The builder does not edit the manifest or overwrite an existing ZIP. Use `--output /path/to/a/new/directory/smarwi.zip` for another build. The output basename must match `hacs.json`. A matching tag is only a metadata check, not permission to publish.

The **Package** workflow runs the same checks on pull requests to `main`, pushes to `main`, and manual dispatch. Its optional `tag` input must match the source manifest exactly. It saves a development ZIP as an Actions artifact; it has no release event or release-upload step and cannot publish a release. Do not install its untested artifact on a live window.

Hassfest and HACS validation check metadata. The required Ruff/basedpyright workflow now uses Python `3.14.10` and HA `2026.11.0`, matching the runtime test baseline instead of historical HA 2024 stubs. It retains basedpyright `1.10.4` and `typeCheckingMode = "all"`; the checker receives the actual Python interpreter explicitly. Native HA Probatio replaces the previous form schema, obsolete `CONNECTION_CLASS` metadata and unnecessary ignores are removed, and one narrow `TextSelector` import exception documents generic-type erasure in HA's registry decorator. A lasting test protects native schema acceptance/rejection. No global rule is disabled.

With the existing pinned environment, run `uv tool run --from basedpyright==1.10.4 basedpyright --pythonpath .venv/bin/python --project pyproject.toml` from the repository root. This alignment provides type evidence for the selected HA version, not a supported-version range or hardware acceptance. Package tests remain dependency-free. Do not run `scripts/develop` as an offline check: it starts Home Assistant.

## Direct tilt-contract baseline (P2a)

Use Python 3.14.2 or newer in a dedicated development environment. These tests import the real pinned HA entity classes but do not construct or start a Home Assistant instance. They use only a fake device, mock its commands, and block socket connections, DNS and HA MQTT publish/subscribe calls during each test. Do not run them inside an operating HA installation.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-tests.txt
.venv/bin/python -m unittest discover -s tests -p test_cover_contract.py -v
```

For an existing environment, install the test requirements into that environment; do not replace it. A uv-created environment may have no pip; use an installed `uv pip install --python .venv/bin/python -r requirements-tests.txt` in that case. The **Tests / Tilt contract** job uses Python 3.14 and the same pins. Package checks select only `test_package.py`, so they remain usable without HA installed. Importing the entity can create Python bytecode caches; packaging fixtures exclude those caches instead of treating them as runtime source.

Eight direct entity tests protect `WINDOW`, exactly four tilt features, absence of standard-action aliases, the tilt-position property, `is_closed`, and delegation of the four native tilt methods. The Stop case supplies an actual moving state and checks that inferred position is invalidated. The original 0/1/10/30/100 entity-payload cases stopped at a mocked device boundary. The later public 1% regression and P6a fix validate `open;1`; those original direct tests did not establish its wire encoding.

These direct tests remain useful unit tests, not integration acceptance. The next slice exercises setup and services through HA instead of replacing those interfaces.

## Public setup and tilt-service baseline (P2b)

`requirements-tests.txt` pairs HA `2026.11.0` with the official `pytest-homeassistant==2026.11.0` fixtures and `paho-mqtt==2.1.0`. It also pins `aiohasupervisor==0.8.1`, matching HA's Supervisor manifest: MQTT's config flow imports it even without a Supervisor installation. The [official fixture README](https://github.com/home-assistant/core/blob/74cf5a49c63ed8d4d87717844bf14f79c28c9cea/packages/pytest-homeassistant/README.md) explains the version pairing and pytest settings. Do not install the overlapping legacy `pytest-homeassistant-custom-component`; its `0.13.375` release requires HA `2026.10.4`, not our pinned version.

```sh
.venv/bin/python -m pytest tests/test_cover_services.py -q
.venv/bin/python -m pytest -q
```

The P2b baseline introduced 36 passing tests and one strict expected failure. The required **Tilt contract** job runs the full pytest suite, including the original direct entity and packaging tests. The dependency-free package-only unittest command above is unchanged. See the topic ledger for later results; P3a/P3b counts below describe their initial historical checkpoints.

The new tests set up a real SMARWI config entry through `hass.config_entries.async_setup`, load its real platforms, and discover a synthetic serial through HA's MQTT message callbacks. They resolve the registered cover by its existing serial-derived unique ID. Calls through `hass.services.async_call` verify native tilt payloads, QoS 2 and non-retained publishing at the mocked HA client boundary. HA rejects invalid tilt payloads and explicitly targeted standard actions without publishing. State-machine assertions verify WINDOW, exactly the four tilt features, unknown tilt and observed closed/zero tilt without standard position attributes. A moving Stop case characterizes the inherited two mocked `stop` publishes and position invalidation after subsequent idle telemetry. Public unload removes the active cover and prevents later synthetic discovery from recreating it.

At the P2b checkpoint, 1% was a **strict xfail**, not a pass: desired `open;1` became `close`. Only that exact single wrong-close result raised its dedicated expected-failure exception; missing/duplicate publishes, other payloads and setup failures were not masked. P6a subsequently corrected the boundary and replaced that exception/marker with an ordinary exact `open;1` assertion. No expected failure remains for this defect. Dependency and setup checks were not bypassed.

The official `hass` and `mqtt_mock` fixtures create disposable in-process HA objects with a mocked Paho client. No HA server is started, no live HA installation is accessed, and no real broker or device is connected. Additional guards block socket connections, UDP sends, server binds/listens and DNS, including loopback. A small fixture completes the upstream Paho mock's missing socket-close callback on disconnect, so HA cancels its actual MQTT timer; cleanup checks remain enabled. Storage, translations, registries, platform forwarding and HA service dispatch use the official fixtures, not a hand-built HA replacement.

P2b was a bounded baseline, not full P2/P8 acceptance. Its historical fixture deliberately sends a separate online update after discovery and does not itself prove cached hydration. Separate deterministic tests now cover cache-before-attachment, broker session transitions, Remote-ID flows and typed runtime ownership; consult the ledger for each bounded result. Actual broker replay/freshness, arbitrary lifecycle races, settings, supported-version range and HACS install/update remain open. Stop does not immediately refresh the HA state machine before telemetry, and two mocked payloads do not validate physical halt or holding. No hardware safety or full Bronze compliance is claimed.

## Key/value message syntax (P3a initial offline checkpoint)

```sh
.venv/bin/python -m pytest tests/test_keyval.py tests/test_cover_services.py -q
.venv/bin/python -m pytest -q
```

The shared decoder ignores empty lines, including leading/internal/trailing empty LF or CRLF lines. It still splits only at the first colon. Values, unknown keys and the inherited duplicate-key behavior are unchanged; whitespace is not normalized. A nonempty line without a colon rejects the entire message. Both MQTT callbacks catch that parse failure before changing a snapshot or dispatching an update. The advanced-configuration callback also catches failed integer conversions before assignment. New rejection warnings do not include raw payloads.

An empty or unknown-only status is ignored without entity registration, snapshot replacement or an update signal. An advanced-configuration message with no writable records, including a response containing only the inherited read-only `cvdist` field, also leaves the previous snapshot unchanged. Unknown integer configuration keys remain preserved. Accepted nonempty snapshots still replace the previous dictionary; this topic does not introduce merging or require a complete set of fields. The [manufacturer MQTT documentation](https://vektiva.gitlab.io/vektivadocs/en/api/mqtt.html) describes newline-separated `key:value` status but does not settle complete-versus-partial updates. The rejection policy is a conservative implementation choice, not a verified firmware contract.

Twelve decoder cases and eighteen additional public MQTT cases cover blank lines, malformed records, ignored empty/unknown-only status, noninteger configuration values, snapshot preservation, no discovery/update signal or command publish on rejection, and recovery on the next valid message. The first regression run failed before the production change. At the P3a checkpoint, the local full suite had **66 passes and one strict expected failure**, plus 25 unittest subtests, on the existing pinned HA 2026.11.0 environment. The expected failure still represents the separate 1% command-encoding defect. All transport remains mocked and network guards remain enabled.

Active diagnostics also identified the inherited indirect `DeviceInfo` import as private in pinned HA. Importing the same class directly from `homeassistant.helpers.device_registry` resolves that finding without changing runtime behavior. At the P3a checkpoint, three inherited numeric-conversion warnings for status `ip`, `rssi` and `s` remained. Numeric validation is addressed separately in P3b below; broader status domain validation, unknown position handling, topic validation, initial cached hydration, availability and settings transactions remain separate work. Keeping the previous snapshot does not establish freshness or safe writes.

P3a was initially developed offline, without refreshing upstream, contributor documentation or remote CI. The later publication phase refreshed upstream and merged fork PR #6 only after all six protected checks passed. That does not create an upstream-ready submission, complete P3, establish Bronze compliance or validate physical safety. Prepare suitable upstream fixes separately from a freshly checked upstream base; no deployment or release followed.

## Atomic status numbers (P3b initial offline checkpoint)

```sh
.venv/bin/python -m pytest tests/test_cover_services.py -k 'numeric_status or partial_status' -q --tb=short --show-capture=no
.venv/bin/python -m pytest -q --tb=short --show-capture=no
python3 -m unittest discover -s tests -p test_package.py -v
.venv-tests/bin/ruff format --check scripts/build_release.py tests
.venv-tests/bin/ruff check .
.venv/bin/uv pip check --offline --python .venv/bin/python
```

After decoding/filtering a nonempty status, validate numeric conversions before assigning the snapshot, announcing entities, updating the device registry or dispatching updates. Present `rssi` uses the existing Python `int()` semantics; present `ip` additionally passes the existing unsigned 32-bit little-endian IPv4 conversion. Thus IP endpoints `0` and `4294967295` remain representable; this is not an IP usability policy. `s` retains `int(value or 0)`: missing/empty state remains UNKNOWN, as do unknown integer codes. No RSSI bounds, state-code allowlist or stricter numeric grammar is introduced. Accepted snapshots retain raw strings and replace, rather than merge with, the previous snapshot. Missing fields remain optional.

A failed integer conversion or unsigned IP packing rejects the entire message with a payload-free warning, before even the integration's status debug log. It preserves the previous snapshot and emits no status discovery/update signal, registry update, state write or publish. Initial online discovery still creates the device object/subscriptions; validation does not undo that earlier event. Unknown integer states retain inherited ERROR logging/classification as UNKNOWN, not a newly proven physical fault meaning.

Twenty new synthetic public MQTT cases cover fourteen initial/registered rejection cases (noninteger/empty IP and RSSI, negative/overflow IP, nonempty noninteger state), recovery, real registered-device update-boundary spies, no state writes, integer syntax compatibility, IP endpoints and non-symmetric little-endian order, raw strings, empty/unknown state codes, and missing fields with full replacement. The corrected pre-fix regression run against unchanged production source had 14 failures, 6 passes and 10 teardown errors from the existing IP/state conversion exceptions. At the initial P3b checkpoint, selected cases had **20 passes**; the full suite had **86 passes, one strict 1% xfail and 25 passing unittest subtests**, with five third-party deprecation warnings. The later P6a topic fixes that independent 1% defect. Ten package unittests, scoped formatting, Ruff lint and the offline dependency check (122 installed packages) pass. Active diagnostics for the two changed Python files report no primary findings, but retain three auxiliary unchecked-getter conversion warnings and 111 informational `hass` spelling findings. Getters rely on the newly validated ingestion boundary; no blanket diagnostic-clean claim is made.

Two independent read-only reviews found no blockers in the implementation or regression evidence; neither reviewer executed the checks. The main agent independently reran the full pytest suite, package unittests, lint, scoped formatting, offline dependency check and active diagnostics with the results above. At that offline checkpoint, the legacy CLI basedpyright job was not run locally. Subsequent required CI exposed three intentionally unused validation results; assigning them to `_` fixed the strict finding without suppressing a diagnostic or changing conversion semantics. All six checks then passed for fork PR #7. Current-HA strict typing is now also reproducible locally with the command above.

P3b's original results are offline evidence, not upstream acceptance or a firmware contract. Later independent topics handle unknown position, cached hydration, session availability and command boundaries without changing the MQTT-only identity/feature contract. Firmware numeric ranges, complete-versus-partial semantics, IP byte-order guarantees, freshness, real replay, settings safety, supported HA range and physical safety remain unverified. No live HA/broker/device, deployment or release was involved.

## Before any fork release

1. Add an HA regression harness and test the declared minimum and current stable HA. Record exact test dependencies and Python versions.
2. Assert the exact tilt-only feature mask, native tilt-service payloads, and tilt-position reporting. Keep observed state separate from inferred percentages.
3. Resolve parser, cached-state, availability, command-boundary, and inference defects in separate topics. Passing package tests does not close these gates.
4. Obtain specific authorization for each HA, broker, or hardware test. Use a disposable simulator before reconnect/failure tests on a live device. Never run two controllers against one device.
5. Verify firmware-specific stop/holding behavior, settings transactions, broker replay boundaries, device recovery, and physical safety controls. No blind retries or movement/Stop/Fix health probes. Do not enable writable calibrated distance without evidence.
6. Validate installation, update, and rollback with HACS and manual packages in an authorized disposable environment. Record firmware, HA, broker/session settings, test results, and limitations without credentials or private traces.
7. Set a tested HACS minimum, choose the independent fork version, and keep manifest, exact tag, changelog, and ZIP version consistent. Preserve license notices and build our own asset. Do not reuse upstream release assets.
8. Review the release policy and tooling before enabling publication. Publishing releases is separate from producing an Actions artifact. No tag or release is part of P1a.

There is no migration framework, broad historic support promise, or safety certification. Network Stop is not an emergency-stop guarantee. See the [upstream ledger](upstream.md) for intentional divergence and topic tracking.
