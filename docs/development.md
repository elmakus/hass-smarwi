# Development and release gates

See the [development MQTT protocol and safety boundaries](protocol.md) for evidence-backed topics, payloads and verification limits.

## Current status

This is an independently maintained, MQTT-only fork of `jirutka/hass-smarwi`, based on upstream v0.3.5 (`6a528f35a695bfb5b70e5fe22eb113a163ef7999`). Parser, state-reporting, lifecycle and configuration fixes are independent topics. The [upstream ledger](upstream.md) records their fork PRs, exact scope and publication status. Historical baseline counts below are not current totals.

The source version is `0.4.0.dev1`, a release candidate containing the merged idle-Stop local-intent fix. The published experimental `0.4.0.dev0` remains immutable at `c6017d4`, with bounded native installation and real-device telemetry acceptance recorded below. Publication and native version-transition results for `0.4.0.dev1` are not yet claimed. The development target is the latest stable Home Assistant only; older versions are outside the testing scope. On 2026-11-07, the [official latest release](https://github.com/home-assistant/core/releases/tag/2026.11.0) is `2026.11.0`, matching the existing runtime, official fixtures and strict-type-check baseline. `hacs.json` now declares that tested development floor instead of the inherited, previously removed untested `2024.1.0` value. This is not a firmware matrix or complete installation/update/physical-safety acceptance.

The integration domain remains `smarwi`. One `WINDOW` cover retains exactly `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION`, and `STOP_TILT`. Standard cover controls, standard-action aliases, HTTP control/polling/fallback, dashboard dependencies, and additional actuator entities are outside scope.

## Current behavior and evidence boundary

- Validate status numbers before snapshot replacement, entity discovery, registry work or update dispatch. Reject malformed messages atomically; do not invent mandatory complete snapshots, merging, firmware ranges or a state-code allowlist.
- Interpret only literal `pos:c`/`pos:o` as observed closed/open. Public tilt is zero only for accepted closed telemetry, including cache; otherwise it is unknown. Requested targets and near-frame estimates are not measured percentage feedback.
- Hydrate newly attached entities from cache after listener registration. Broker loss clears the session online observation without discarding telemetry. Reconnect alone cannot restore availability; retained online replay is an observation, not fresh liveness proof.
- Validate Remote ID as a literal MQTT segment without silent normalization. Native identity/in-progress checks and stored-data matching prevent duplicate new and legacy entries without modifying existing entries.
- Route 1% to `open;1`, zero to `close`, and every explicit tilt request to the existing command path even at an inferred equal position. Install requested intent before awaited publication; a late acknowledgement must not restore intent cleared by an actual Stop invalidation.
- On publication failure/cancellation, discard only the request that still owns the current local intent. Identity ownership distinguishes successive requests even at the same target. Do not restore an older target, retry automatically, change observed motion or interpret failure as proof of non-delivery. Other terminal cleanup and wire-Stop conditions remain unchanged.
- Every explicit tilt Stop clears the local requested target and owner, even when cached IDLE suppresses the wire command. This prevents that request from overriding later direction reporting; it does not cancel an already published device command.
- Keep runtime device maps owned by typed config entries, with native unload/reload cleanup and tests for independent entries and bounded setup/unload failures. If MQTT client readiness returns false, use native setup retry before allocating runtime data or subscriptions.
- Roll back failed/cancelled device subscription initialization without poisoning discovery. Preserve the provisional duplicate guard; run MQTT handlers only after all acquisitions succeed, and suppress handlers from abandoned attempts. Drain each returned native cleanup handle once.

The guarded public-interface unit tests use official HA fixtures and mocked Paho transport with explicit network guards. No HA server starts or live controller is installed. Passing them does not prove device execution, target accuracy, broker replay boundaries or safe physical Stop/holding. Retained telemetry remains last known.

Private motion/direction estimates remain inherited and unverified. The `OPENING` phase cannot simply be equated to physical opening toward every target. Wire Stop before moving telemetry, unchanged idle telemetry, release/disconnect intent invalidation, settings transactions and physical recovery remain separate gates. Native HA tilt-toggle opens at reported zero and closes when tilt is unknown; removing stale zero can change that default branch. Use explicit native actions when intent matters. No dashboard or standard-action alias compensates for these limits.

## Latest combined local verification (2026-11-07)

The combined source checkpoint passes **256 tests and 101 subtests, with no xfails** on Python `3.14.10`, HA/official `pytest-homeassistant` `2026.11.0` and Paho `2.1.0`. These local counts include 16 dependency-free hosted-harness helper tests; separately executed hosted results are recorded below. Five third-party aiohttp/backoff deprecation warnings remain visible. This is the declared development HA floor, not a firmware matrix or completed release acceptance.

```sh
.venv/bin/python -m pytest -q --tb=short --show-capture=no
python3 -m unittest discover -s tests -p test_package.py -v
.venv-tests/bin/ruff check .
.venv-tests/bin/ruff format --check scripts tests
.venv/bin/uv tool run --offline --from basedpyright==1.10.4 basedpyright --pythonpath .venv/bin/python --project pyproject.toml
.venv/bin/uv pip check --offline --python .venv/bin/python
git diff --check
```

The eleven package unittests, pinned strict checker (zero errors/warnings), Ruff, scoped formatting and installed-dependency check (122 compatible packages) pass. The offline tool command assumes its pinned tool is already cached; initial dependency/tool installation can need network access. Reuse existing environments and do not start `scripts/develop`.

Main independently reran the combined checks after adding the hosted acceptance harness. Two fresh independent reviewers found no blockers in the harness; they inspected source and evidence but did not execute tests. Main's active primary-server diagnostics checked its three Python and two workflow files with zero findings and no inconclusive outcomes. Auxiliary all-server findings and earlier inconclusive results remain separate, not a universal clean-LSP claim. Earlier interpreter-resolution findings and actual test-assertion issues are recorded in the ledger; no diagnostic rule was globally disabled. The explicit-interpreter strict CLI result covers production modules, not the new scripts or tests. Local checks do not establish the separate authorized hosted-runtime results recorded below.

A development ZIP was also built without overwriting an existing output: all 18 members matched current source bytes, including the unchanged MIT license. This checks packaging, not HACS installation or deployment. Fork CI and merge status are recorded per PR in the ledger; local green results alone do not authorize a release.

## Local intent after Stop with cached IDLE (2026-11-07)

This unreleased source change clears only the requested target and its owner
before the existing IDLE guard. A completed native request followed by Stop while
the cached state was still IDLE previously left its direction override installed.
Later injected motion telemetry could therefore report HA opening for the existing
closing-code fallback, or the reverse. Three native-service regressions reproduced
this on unchanged production, without suspending publication or claiming a physical
race. Three added idle cases in the bounded delayed-publication test also failed;
the existing three moving cases passed. All six now pass.

The earlier direct test deliberately characterized idle Stop as preserving intent.
That boundary changes explicitly; its unchanged-status/release/availability checks
remain. Three added direct subtests cover late success/failure/cancellation after
idle Stop while preserving the previous private position. Public percentage
reporting, raw telemetry, observed motion, payloads, QoS and non-retain stay unchanged.
No `stop` is sent while cached IDLE; the existing moving path still sends two.
**This does not fix early physical stopping or retract a published motion command.**

Three completed-request characterization cases also exercise identical open-IDLE
status, release/fix telemetry and native broker disconnect/reconnect with retained
online replay. These boundaries still preserve local intent until explicit Stop;
recovery adds only the inherited `lcfa` read, not an automatic motion retry.
This is documented existing policy, not new safety or freshness behavior. Tests use
official HA fixtures, mocked Paho and socket/DNS guards; no live system, real
broker outage, window movement, release asset or deployment accompanies this change.
The published `0.4.0.dev0` remains the exact earlier `c6017d4` snapshot.

## Offline native Marketplace package contract

Five cases in `tests/test_marketplace_package.py` build the current candidate with
our existing ZIP builder and use the official HA fixture with a temporary config
directory. Real `MarketplaceManager` and `IntegrationRepository` objects exercise
`_async_prepare_catalog_install(version, commit=False)` followed by
`_async_write_content(download)`. Only the manager's download response bytes are
replaced, with an exact three-URL allowlist and complete request-order assertion.
Socket connection, datagram, DNS, bind and listen guards block network access and
server startup. No new dependency or separate installer framework is added.

The native path installs every flat ZIP member with exact bytes on first write
and replacement; replacement also removes seeded stale files. An invalid written
domain or version restores the exact old nested tree. An invalid nested ZIP layout
removes failed first-install output. Every case checks that the native backup
directory is empty afterward. Negative archives are synthetic altered payloads,
not releases; old-tree sentinels are not validated installed integrations.

These are passing characterization tests, not a reproduced production defect or
red-before-fix evidence. Native metadata resolution, destination selection,
extraction, written-manifest checks and backup/restore remain real. The private
methods are coupled to the pinned latest-only HA baseline; inspect them when that
baseline changes. This is not public `async_install_repository`, catalog selection,
`update.install`, persisted installed-version metadata, post-install cache/import,
UI, real HTTP/GitHub downloads, account or published-release acceptance. It also
does not test the legacy HACS installer, interrupted restart/downgrade, complete
adversarial-ZIP security, firmware or physical behavior. Full native distribution
acceptance remains a release gate; historical hosted results are unchanged.

## Published prerelease and native installation (2026-11-07)

Published [GitHub prerelease `0.4.0.dev0`](https://github.com/elmakus/hass-smarwi/releases/tag/0.4.0.dev0)
points to exact source `c6017d43e37e5e00eef1e01bb0fff293ab9d942d`.
Its `smarwi.zip` is **82,518 bytes**, SHA256
`2374b0ab9194c3fa18e42e074b9a2c5ce0fa4118bce12c9b0eeb05746168ac34`;
all 18 members match source, including the unchanged MIT license. Exact-source
verification recorded 247 tests/98 subtests, five inherited warnings, eleven
package tests, Ruff and pinned strict typing with zero errors/warnings/notes;
all six protected source checks passed. These are source checks, not safety certification.

On the authorized HAOS/Core `2026.11.0` instance, the actual English custom-integration
warning was read and accepted through the normal public flow. The existing GitHub
connection was reused, the correct fork was registered, and repository prerelease
opt-in was enabled through the public WebSocket API. Native MCP download explicitly
selected `0.4.0.dev0` and succeeded. The original manual tree was backed up; all
18 installed files were verified. An actual restart confirmed installed-version
and repository persistence. Upstream was not installed alongside the fork.

This closes this prerelease's native download/install/restart path, not new GitHub
account setup, legacy HACS, native update/downgrade/reinstall or migrated-state
recovery. The earlier offline/manual/synthetic records below remain historical
evidence with their original scope; their exclusions describe those tests, not
an absence of this later installation.

## Bounded real-device telemetry acceptance (2026-11-07)

A separately authorized test used that installed prerelease, the existing EMQX
broker, firmware `3.4.1-15-g3d0f`, one native user config entry and one `WINDOW`
cover with features `240`. All four native tilt actions were exercised:

| Native action | Broker callback and real device telemetry |
| --- | --- |
| Close tilt from initial open/IDLE | `close`; states `220`, `230`, `250`, then `pos:c` and HA tilt zero. |
| Set tilt position to 1 | `open;1`; states `200`, `210`, `250`, then `pos:o` and HA tilt unknown. |
| Open tilt, then Stop after a moving condition was observed | `open;100`; state `212` (`REOPEN_START`). One Stop service call produced the inherited **two** `stop` payloads, followed by `250` (`IDLE`). |
| Final close tilt | `close`; states `220`, `230`, `250`, then closed/tilt zero. |

All captured statuses had `e:0`, `fix:1`, `ro:0`; these raw values are not a
fault-code or holding guarantee. Evidence is HA broker callbacks paired with
real device telemetry, not visual observation, independent receipt/QoS capture,
calibrated 1% accuracy, measured halt latency/force, mechanical holding or general
firmware compatibility/safety certification. No explicit Fix/release, calibration,
firmware or mechanical setting change, broker-fault test or old-HA mutation occurred.
No production code changed. The physical entry remains configured. A second actual
restart, now with that entry configured, preserved the same entry/device/cover
unique ID and fork version/repository metadata, with closed/zero, IDLE, fixation
on and tamper off reported afterward. All 40 baseline entries remained alongside
only the owned entry (41 total); upstream remained uninstalled. Calibrated distance,
error code and RSSI remained integration-disabled. The scoped structured SMARWI log
query returned zero entries, not a universal clean-HA claim. This bounded restart
and identity result does not prove telemetry freshness.

Stop-before-motion, unchanged-idle/release/disconnect intent handling, holding,
broader replay/failure and settings safety remain open. Future hardware tests need
fresh, specific operator readiness and authorization, physical safety controls and
one controller only; no automatic probes or blind retries. Do not publish another
release merely to increase coverage.

## Actual manual installation acceptance (2026-11-07)

An operator-authorized Home Assistant OS installation on Core `2026.11.0` passed
this manual sequence: current candidate `d77460b` → reference `ce8d31a` → current
candidate again. Both snapshots identify as `0.4.0.dev0`; exact Git-blob/member
hashes, not version strings, distinguish them. The reference differs in
`device.py`, `sensor.py` and `translations/en.json`.

All 18 ZIP members, including the unchanged MIT license, matched each exact source
snapshot before transfer and after installation. Initial installation required an
absent destination. Each replacement checked the existing tree, staged the next
package and preserved the previous tree before switching. No other integration
files or configuration were replaced.

Each of the three installations passed an actual HA restart, returned to
`RUNNING`, and opened the public SMARWI config-entry flow with its required
Remote ID field and no form errors. Each form was cancelled without submitting an
ID. Final config validation passed, current candidate files remained installed,
and no SMARWI config entry existed. The raw startup log had HA's standard
custom-integration warning; the final structured system log had no SMARWI errors.

This closes manual file installation, backward file replacement and return to the
current candidate with restart/import/config-flow smoke on that instance. It is
not a versioned release upgrade/downgrade, migrated-state compatibility or native
Marketplace/HACS acceptance. The repository requires a published `smarwi.zip`
asset for its native release path; none was published to make that manual test pass.
No real window was configured, controlled or used as a health probe in that test.

## Actual synthetic MQTT lifecycle (2026-11-07)

A separate operator-authorized test on the same Core `2026.11.0` installation used
`d77460b`, its existing EMQX broker and one fresh random synthetic Remote ID and
serial. It created a real SMARWI user config entry and simulated only that device's
online/status/configuration-response topics. No real controller namespace,
broker settings, broker restart, account or other config entry was changed.

The real HA state machine showed exactly one WINDOW cover with features `240`,
closed/tilt zero and open/unknown tilt without standard position. All four native
tilt actions targeted that verified synthetic cover. Native `mqtt.dump` callbacks
recorded `open;1`, `open;100`, `close`, `stop`, `stop` in order, plus four inherited
`lcfa` reads across initial online, offline, recovery and reload. The two Stop
payloads characterize existing software behavior, not physical stopping.

Synthetic offline/online changed availability and recovered cached state. One
malformed numeric status preserved state/attributes during a 1.5-second observation;
subsequent valid open/closed telemetry recovered normally. Native entry reload
kept the same cover entity ID, restored closed/zero and created no duplicate cover.
The test then removed its own entry and 12 states, preserving all 40 original
config entry IDs. A fresh scoped subscription saw no retained test messages before
a non-retained positive-control probe. No test controller was left configured.

This is real broker/HA integration evidence from the same HA MQTT client's
callbacks, not an independent client, packet capture, receipt QoS/retain-flag proof,
execution acknowledgement or physical test. It does not exercise broker failures,
persistence stress, native release installation or backwards migrated state.
The deliberate malformed status produced its expected rejection warning. The test
also exposed the deprecated unscoped device-registry lookup at `device.py`, tracked
as a separate compatibility fix; the original run is not a clean-warning claim.

## Entry-owned device-registry metadata

The actual synthetic MQTT run exposed HA's deprecation warning for the unscoped
`DeviceRegistry.async_get_device` lookup. Status-driven metadata updates now use
`async_get_device_by_identifier((DOMAIN, serial), config_entry_id)`. No identifiers,
entity identity, metadata fields or control policy change.

A new public HA/MQTT regression uses two native device entries with the same
identifier under different config entries. It failed against unchanged production
because telemetry modified the other entry's metadata. With the scoped lookup,
only the owning device updates; device/entity identity and the other entry remain
unchanged, with no deprecated-call warning. Parent independently reproduced red
and reran the full green suite. The strict checker covers production modules;
active primary-server checks of the two changed Python files are clean. Native
lookup returns no device rather than falling back to another owner.

## Current-stable Home Assistant policy

Test the latest stable HA release only. Keep that version pinned explicitly in
`requirements.txt` and `requirements-tests.txt`, with the matching official
`pytest-homeassistant` fixtures. Do not add historical-version jobs or compatibility
shims solely to support older HA installations. On a future baseline update, inspect
release changes, rerun the existing checks and update the HACS floor together.
The offline package test checks this alignment; it does not query the network or
prove that a pinned version is still the latest. Refresh that fact from the
[official release list](https://github.com/home-assistant/core/releases) when updating.

The native [`homeassistant` metadata key](https://contributors.home-assistant.io/marketplace/reference/hacs-json/)
is a lower-version filter for released repositories, not an exact-version lock,
an upper bound or a guarantee about untested future HA versions. It does not
create a release or validate the installer, firmware, delivery or physical safety.
Manual file extraction does not enforce this metadata. No custom runtime version
check, dependency, automatic updater or new version-test framework is added.

## Roadmap assessment (2026-11-07)

The next release work remains reliability and compatibility, not a larger actuator
feature list. The prerelease native install and bounded device tests above do not
close native update/recovery, broader broker/session behavior, holding or full
physical-safety acceptance. Older HA compatibility is not a release requirement.
The completed historical hosted milestone is not repeated or extended by this topic.

| Candidate | Decision and evidence boundary |
| --- | --- |
| Raw `e` error-code reporting | Implemented as a read-only diagnostic sensor, disabled by default. Reuses the existing MQTT snapshot, entity lifecycle and sensor platform; no dependency or additional subscription. Vendor code meanings remain unknown. |
| Infer unexpected physical movement from `pos`/`s` and missing HA intent | Unsupported as reliable attribution or intrusion detection. Binary position does not capture every open-to-open movement. Other controllers, physical buttons and autonomous plans need no local HA intent. |
| Vendor unexpected-open/close virtual sensor | Worth investigating further: [firmware 203.3.0](https://vektiva.gitlab.io/vektivadocs/en/changelog/smarwi.html) announces it. Topic, payload, trigger/reset rules, freshness and firmware compatibility are not established. Obtain the wire contract before implementation; physical characterization requires specific supervised authorization. |
| Plain `open` instead of `open;100` | No command change. [API documentation](https://vektiva.gitlab.io/vektivadocs/en/api/api.html) permits an optional target; [MQTT documentation](https://vektiva.gitlab.io/vektivadocs/en/api/mqtt.html) explicitly illustrates `open;100`. Neither establishes the omitted target default, equivalence or different smoothness/motor profiles. |
| Read-only calibrated distance | Deferred. [Finetune documentation](https://vektiva.gitlab.io/vektivadocs/en/settings/finetune.html) calls the measured distance read-only. Existing writable `cfdist` and filtered `cvdist` are not proven equivalent. Keep the inherited number disabled; do not invent a replacement mapping. |
| Unknown public tilt and 1% opening | Completed software behavior: observed closed gives zero; otherwise unknown. A positive 1% request publishes `open;1`. Neither result establishes physical percentage accuracy. |
| Stop/Fix and state recovery | Software intent-failure ownership and bounded lifecycle recovery are covered. Physical Stop/holding, Stop-before-motion and private direction/idle/disconnect policy remain separate gates; no safety-critical command change. |
| MQTT availability and reconnect | Bounded connection/session/status gating and native setup retry are covered. Retained online/status remain last-known observations; freshness, arbitrary replay and execution acknowledgement are not established. |

At startup/reload/reconnect, unknown or unavailable becoming open is not evidence
of a new physical movement. Do not infer transitions across missing, rejected or
disconnected telemetry, or interpret retained replay as an event. No documented
heartbeat deadline, trusted event clock or controller correlation closes these gaps.

[Alarmo](https://github.com/nielsfaber/alarmo#sensor-configuration) already combines
security-related binary sensors and owns arming, delays and actions. Reuse it rather
than building alarm policy into SMARWI if a trustworthy sensor contract is later
established. The raw error-code sensor is not an Alarmo window/intrusion input; the
existing ridge diagnostic is not proof of unexpected movement. An independently
validated contact sensor is a better source of physical open/closed observations,
not a source of actor attribution or a security guarantee. No automatic movement,
Stop or Fix response is added.

### Raw error-code diagnostic verification

Ten guarded public-HA cases failed before implementation because the entity did not
exist, then passed. They cover disabled-by-default registration and English naming;
initial retained-marked status hydration without post-attachment telemetry; raw
zero, leading-zero and unknown text values; missing/empty and HA state-length
boundaries; update/clear/rejected-message behavior; independence from `s`; native
broker disconnect/reconnect and retained-online cache recovery; reload identity
and unload cleanup. Tests use the existing official fixtures, mocked Paho and
network guards. No listening server, device fault or physical movement was tested.
The first green attempt exposed a test expectation at the wrong mocked MQTT layer;
correcting it to the existing native-client call signature left production unchanged.

Only `e` ingestion, its raw cached getter, sensor registration/presentation and
English translation change. No code table, problem boolean, custom timer, alarm
engine, motion/availability policy or settings write is introduced. The full local
suite and existing production-scope strict checker pass; this is not a complete
quality-tier, supported-version or release claim. Four changed Python/translation
paths have clean active primary-server diagnostics; this is not an all-server
cleanliness claim. The inspection-only ZIP contains 18 unique members matching
current source and the unchanged MIT license; no installer, release or deployment
was exercised. Independent source and protocol reviewers found no blockers;
neither executed the tests. The Bronze checklist still has unverified coverage
and branding items, field-description gaps and an unresolved connection-validation
exemption; this diagnostic does not claim or implement full-tier compliance.

## Discovery initialization recovery (P4d)

A failed per-device subscription acquisition previously left its provisional device in the entry cache, preventing rediscovery. Earlier acquired listeners remained effective until entry unload and could announce entities for that incomplete device. Initialization now rolls back returned handles on exception/cancellation and removes only its owned reservation. A local `asyncio.Event` gates the original HA MQTT jobs until acquisition succeeds; failure/unload wakes them to exit. A handle returned after teardown is removed immediately and initialization propagates cancellation. No custom replay scheduler or command queue is added.

Main independently reproduced ten initial red cases against unchanged production source. Seventeen final public HA/MQTT cases cover all three acquisition boundaries, error/cancellation, direct unload or retry, duplicate discovery, retained-marked status, successful/rejected unload, late-returned handles and another active entry. The seven additional cases were not separately claimed as red before production. The exact cover identity and four tilt features remain asserted.

Native HA 2026.11 public subscribe currently registers without yielding. Deliberately suspended acquisitions characterize defensive robustness, not demonstrated broker timing. The gate does not cancel original handlers already executing after commit or solve every queued discovery/unload race. Native registration failures before returning a handle and removal-callback failures remain unproven. Failed attempts keep an inert drained unload closure until entry teardown. These are software ownership guarantees, not firmware, freshness or physical-safety evidence.

## Pending native tilt-service lifecycle (P4e)

Six guarded public-HA cases hold a mocked tilt-command publish across successful native unload/reload or immediate rejected unload. Each lifecycle path resolves success, failure and publish-originated cancellation separately, paired with native open, close and set-tilt actions respectively. Adjacent tests cover shared request failure/cancellation across all three actions; this slice is not a full cross-product. In pinned HA 2026.11.0, the caller-created service task remains pending through unload.

Late completion stays with the old caller and object. The tests preserve replacement cache/device/entity ownership, telemetry, local intent and public state, with no late detached-entity write or extra publish. A changed synthetic status then produces exactly one effective active-cover update and state write. Rejected unload retains the active object and listeners. It is rejection before platform removal, not a partial-teardown test.

No production defect was reproduced and no production policy changed. Cancellation is injected by mocked publication, not caused by native unload. These are characterization tests, not red-before-fix regressions. They do not prove delivery, retraction, physical stopping, holding, real broker replay or behavior on other HA versions.

## MQTT-client setup retry (P4f)

If the existing MQTT readiness helper returns false, setup now raises native `ConfigEntryNotReady` rather than returning a fatal setup failure. HA owns reporting, scheduled backoff and cancellation. The successful path and exceptions raised by the helper remain unchanged. This retries integration setup only, never device commands.

Three guarded public lifecycle regressions cover native scheduled recovery without manual reload, cancellation on unload and cancellation on entry removal. Parent independently reproduced all three failures before the fix: recovery stayed in `SETUP_ERROR` with one readiness call after official frozen-time advancement. Failed readiness creates no runtime data, platforms, subscriptions, publications or registered entry entities. Another loaded entry remains functional.

The tests inject documented helper false/true results, not a real timeout, ordinary startup race or broker outage. MQTT dependency setup normally runs first; an already loaded MQTT client passes the actual helper without requiring broker connectivity. Retry does not repair missing, disabled or fatally misconfigured MQTT. Other HA versions and physical/broker acceptance remain unverified.

## Manual synthetic hosted acceptance

The separate **Synthetic hosted acceptance** workflow is `workflow_dispatch` only,
on one standard `ubuntu-24.04` GitHub-hosted VM, with read-only repository
permissions, no persisted checkout credentials, a 60-minute timeout and serialized
runs. It is not run by push, pull request, schedule or release events. Dispatch
requires the operator's specific synthetic-runtime/publication approval. Do not run
its orchestrator locally or point it at an existing HA installation or broker.

It builds the unchanged current flat-ZIP builder against exact tracked source
**A `43c22f5a3c427aa46040f175f770d3dfd0f016b8`** and
**B `635017321dab8c29bbeff5f5223bfe9461cdffd1`**. Both manifests must remain
byte-identical `0.4.0.dev0`; archive/source/install bytes and the unchanged license
are checked. Integration replacement removes stale files. No production source,
manifest, HACS metadata, dependency, tag or release changes enable this test.

Host staging pulls stock official `ghcr.io/home-assistant/home-assistant:2026.11.0`
and `eclipse-mosquitto:2.0`, resolves immutable digests/local image IDs and uses
`--pull=never` for runtime creation. Actual Docker, Python, HA, Paho, aiohttp,
Supervisor-client dependency and Mosquitto versions are recorded, not guessed.
Missing offline image dependencies, unavailable images or incompatible safety
controls block acceptance; there is no pip, bridge, proxy or internet fallback.

Only inert processes start before preflight. HA's inert PID 1 owns a `none`
network namespace; the inert broker joins `container:<exact HA ID>`. Both use the
runner's nonroot numeric UID/GID (so private stopped checkpoints can be copied
without root), dropped capabilities, no-new-privileges, read-only roots, bounded
resources, explicit fresh bind mounts and `/tmp` scratch. Preflight verifies the
actual IDs/image settings, namespace identity, only `lo`, no usable external IPv4
or IPv6 route, exact environment/mount allowlists, process UID/capabilities and no
initial listeners. No host ports, host namespaces, devices, host sockets, checkout
`.git`, home directory, runner tokens or credential stores enter the containers.
Containment is rechecked before every application stage and after clean stops;
the namespace-owning container stays alive throughout. This tests **application**
stop/start, not Docker-container restart, and assumes a trusted runner/kernel/Docker.

Inside that namespace, real native onboarding creates a synthetic HA-only admin;
local OAuth code/refresh grants, authenticated config flows, registry/state APIs,
native reload and a native tilt service run through actual HA. No fabricated
`.storage`, disabled authentication, injected entity state or mocked Paho is used.
Clients contact only `127.0.0.1`; credentials and private diagnostics stay in the
disposable sandbox. The core-config onboarding step that schedules unrelated
internet services is deliberately not completed. No Marketplace account is used.

The single sequence installs A, discovers `offline_remote` / `offline_serial`,
checks one serial-derived `WINDOW` cover and exactly four tilt features (240),
closed/zero and nonclosed/unknown tilt, one `open;1` captured at the synthetic
broker, and reload identity/no duplicates. A finishes observed closed; after clean
HA/broker stops, its complete configuration/state/integration and broker trees are
checkpointed. B replaces only integration bytes, repeats the smoke and finishes
observed open. Both stop; matching A state is restored into the same mounted roots.
Before publishing any new fixture telemetry, restored A must receive the retained
closed status at the test client and report the existing cover as closed/zero.
Only then does its ordinary smoke continue. This distinguishes saved A from later
B and tests one bounded retained-state recovery, not freshness or arbitrary replay.
Automatically requested `lcfa` reads are tolerated; no Stop, Fix, settings writes
or physical movement policy is tested.

This is **manual same-version code replacement and matching sandbox checkpoint
recovery**, not native HACS/Marketplace update/downgrade, HA backup restore,
arbitrary reverse migration, general replay/freshness, supported-version-range or
physical acceptance. Firmware is not applicable. Native distribution and hardware release
gates remain open. Adding the workflow is not evidence that any hosted run passed.

Only `hosted-evidence/report.json` is uploaded, with **seven-day retention**.
Workflow source, job status and allowlisted sanitized artifacts are public in a
public repository; seven days is artifact retention, not a promise to erase source
or job logs. Evidence contains stage verdicts, versions/digests, package/checkpoint
hashes, containment/assertion/restore/cleanup results and hashed synthetic registry
identity. Raw auth, HTTP, storage, inspect output, logs and checkpoint snapshots
are never uploaded. Exceptions expose only a public orchestrator source/function/line location, never messages, values or source excerpts. Cleanup runs
in `finally`, including termination signals, removes only exact job-created IDs
and scratch, attempts all owned resources on failure and never prunes the host.
Forced VM loss/SIGKILL cannot run Python cleanup; the disposable hosted VM is the
final disposal boundary. A failed cleanup is a failed job, never a pass.

Dependency-free local helper checks (imports cannot start apps/containers):

```sh
python3 -m unittest discover -s tests -p test_hosted_acceptance.py -v
```

These cover unsafe archives/links, stale-byte removal, restore root-inode
preservation, containment rejection, stage-specific evidence and failure cleanup.
They do not prove image compatibility or the native flow. Each hosted rerun must
check stock-image compatibility, containment and offline native behavior; preserve
guards and report blocked/failed rather than relaxing them.

### Scope and reuse decision

Keep this as a fixed historical gate, not a generic release framework. Its pinned
A/B refs intentionally do not test current main or future releases automatically.
Future releases need their own explicit version/source acceptance matrix.

The existing builder and official in-process HA fixtures are already reused.
Hosted sentinels add installed bytes and real native API/MQTT transport, rather than
copying the full mocked service suite. Review of
[pytest-docker/Compose](https://github.com/avast/pytest-docker),
[Testcontainers-Python](https://testcontainers-python.readthedocs.io/en/latest/core/README.html)
and [HomeAssistant-Test-Harness](https://github.com/HeadlessTarry/HomeAssistant-Test-Harness)
found useful lifecycle/client helpers, but no demonstrated net simplification
preserving this full contract.
Most package, state, native-interface, containment and sanitization logic would
remain custom. No new framework dependency or configurable ref input is added.
Consolidate shared package-layout policy only when that policy next changes;
installer trust-boundary validation must remain separate from producer validation.

### Recorded hosted baseline (2026-11-06)

The original byte-restoration scope passed in
[run 42312152414](https://github.com/elmakus/hass-smarwi/actions/runs/42312152414)
at harness commit `16ac338b1834d65449f47f18ad0d03a3d5a2ff49`: all three stages,
matching checkpoint bytes, stable synthetic identity, containment and cleanup.
HA `2026.11.0`, Python `3.14.10`, Mosquitto `2.0.22`, Paho `2.1.0`, aiohttp
`3.14.5`, aiohasupervisor `0.8.1` and Docker `28.0.4` were actually observed.
Main verified the artifact digest and installed hashes independently against Git
blobs. That run published fresh telemetry before state assertions; it does **not**
establish the later pre-publication retained-state assertion described above.
The stronger retained-state scope passed in
[run 42315158582](https://github.com/elmakus/hass-smarwi/actions/runs/42315158582)
at code commit `e6fa58ccfebacaf675550f9db96b738f1122db68`, using the same observed
versions. Terminal fixture states were closed, open, closed. Restored A received
retain-flagged closed status and HA reported the existing cover closed/zero before
fresh fixture publication. Exact source/install hashes, stable identity, matching
checkpoint bytes, containment and disposal of both containers/scratch passed.
Main independently verified the artifact SHA256 against GitHub metadata and the
installed-tree hashes against exact Git blobs. This paired broker/HA observation
does not independently trace how HA obtained that state or prove general replay,
freshness, backward migration or physical behavior.

The preceding run `42310285561` was blocked before application stages and cleaned
up; it is not a pass. None of these results establishes native distribution or
physical acceptance. Artifact retention is finite; retain sanitized receipts or
reproduce only with renewed applicable runtime approval.

## Consistent formatting

Use Ruff `0.14.3`, pinned in `requirements.txt`, for the fork-maintained Python scripts and tests. Both development requirement files now target HA `2026.11.0`; do not replace a working environment or install the historical HA 2024 pins/stubs from older revisions into it. Run these commands before committing:

```sh
ruff format scripts tests
ruff format --check scripts tests
ruff check .
```

The required **Linter** CI job runs both lint and the same format check. Formatting is therefore checked, not silently rewritten during CI. The committed files already use this format; editor reformatting with the project settings should leave no diff. `.editorconfig` explicitly keeps Python scripts space-indented while preserving the existing shell-script tab rule. Do not hide recurring formatter changes with stash or assume-unchanged flags: format and commit them with the relevant topic.

The formatting check deliberately covers only Python files in `scripts/` and `tests/`; it does not reformat inherited production integration files or change actuator behavior.

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

The experimental prerelease above is published; this checklist still governs further
release acceptance and is not a claim that every gate was closed before publication.

1. Run the existing HA regression harness and strict checker on the latest stable HA only. Keep the tested baseline, matching official fixtures and HACS floor aligned; record exact dependencies and Python versions. No older-HA matrix is required.
2. Assert the exact tilt-only feature mask, native tilt-service payloads, and tilt-position reporting. Keep observed state separate from inferred percentages.
3. Resolve parser, cached-state, availability, command-boundary, and inference defects in separate topics. Passing package tests does not close these gates.
4. Obtain specific authorization for each HA, broker, or hardware test. Use a disposable simulator before reconnect/failure tests on a live device. Never run two controllers against one device.
5. Verify firmware-specific stop/holding behavior, settings transactions, broker replay boundaries, device recovery, and physical safety controls. No blind retries or movement/Stop/Fix health probes. Do not enable writable calibrated distance without evidence.
6. Complete remaining native update/rollback and any legacy HACS acceptance in an explicitly authorized environment. This prerelease's native install/restart passed as recorded above. Manual current/reference/current file replacement with restart and config-flow smoke already passed as recorded above; do not repeat it as an untested gate. Versioned-release and migrated-state behavior remain separate. Record firmware, HA, broker/session settings, test results and limitations without credentials or private traces.
7. Recheck the current-stable HACS floor, choose the independent fork version, and keep manifest, exact tag, changelog, and ZIP version consistent. Preserve license notices and build our own asset. Do not reuse upstream release assets.
8. Review the release policy and tooling before enabling publication. Publishing releases is separate from producing an Actions artifact. No tag or release is part of P1a.

There is no migration framework, broad historic support promise, or safety certification. Network Stop is not an emergency-stop guarantee. See the [upstream ledger](upstream.md) for intentional divergence and topic tracking.
