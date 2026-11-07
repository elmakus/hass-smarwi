# Development MQTT protocol and safety boundaries

This is a development reference, not an actuation recipe or hardware certification.
Source version remains `0.4.0.dev0`; no tested firmware matrix or HA support range
is established. The fork includes a 1% encoding fix and broker-session gate;
merged code and passing CI are not complete release acceptance. Consult the
[upstream ledger](upstream.md) for accepted versions/topic status and the
[release gates](development.md#before-any-fork-release) before installation.

## Evidence and transport

Manufacturer pages inspected on 2026-11-06:

- [MQTT](https://vektiva.gitlab.io/vektivadocs/en/api/mqtt.html): topics, retained initial data, Last Will, status syntax and command delimiter.
- [API control interface](https://vektiva.gitlab.io/vektivadocs/en/api/api.html): named commands and opening targets.
- [Home panel](https://vektiva.gitlab.io/vektivadocs/en/home/index.html): state-dependent UI Stop/Release/Hold, not a wire-payload definition.
- [Finetune](https://vektiva.gitlab.io/vektivadocs/en/settings/finetune.html): UI settings; calibrated distance is non-editable information.
- [Safety](https://vektiva.gitlab.io/vektivadocs/en/install/safety.html) and [usage](https://vektiva.gitlab.io/vektivadocs/en/install/usage.html): physical safety controls and operating restrictions.
- [Advanced settings](https://vektiva.gitlab.io/vektivadocs/en/settings/advanced.html): broker changes and Wi-Fi-off restrictions.

Implementation evidence is [device.py](../custom_components/smarwi/device.py),
[setup/discovery](../custom_components/smarwi/__init__.py),
[cover.py](../custom_components/smarwi/cover.py) and the
[manifest](../custom_components/smarwi/manifest.json). Source behavior below is
not a manufacturer firmware contract. The integration uses HA MQTT only.
The registry's HTTP configuration link opens the commissioning UI; it is not
HTTP control, polling or fallback transport.

## Topics and commands (descriptive, not instructions to publish)

`<remote_id>` is the broker-owned MQTT username/credential namespace, not a
public example value; `<serial>` is the device identifier. Keep actual credentials,
IDs and private traces out of documentation. The literal `%` is significant.

| Topic | Evidence and role |
| --- | --- |
| `ion/<remote_id>/%<serial>/online` | Manufacturer: retained `1` after connection; offline `0` via Last Will. Fork discovers via `ion/<remote_id>/+/online`. |
| `ion/<remote_id>/%<serial>/status` | Manufacturer: LF-separated `key:value`, initial retained status and state-change publications. |
| `ion/<remote_id>/%<serial>/config/advanced` | Inherited settings response subscription; not defined by the cited manufacturer MQTT page. |
| `ion/<remote_id>/%<serial>/cmd` | Manufacturer command destination; fork also sends inherited settings requests/writes here. |

Manufacturer command names are `open` (optional integer target `1..100`),
`close`, `stop` (stop movement) and `fix` (window fixation). The MQTT page explicitly
replaces API path slashes with semicolons and illustrates `open;50`.
These documented command bodies do not specify holding postconditions or ACKs.
The fork maps zero tilt to `close` and positive targets to `open;<target>`;
its 1% regression checks `open;1`, not the inherited erroneous `close`.

Inherited implementation choices, not vendor guarantees:

- Per-device subscriptions request QoS 1; commands publish at QoS 2, using HA's
  non-retained default. The manufacturer pages do not specify firmware QoS.
- `lcfa` requests settings; `scfa01/1|` precedes encoded newline `key:value` writes.
  These settings payloads are not documented by the cited vendor pages.
- Moving Stop sends two `stop` payloads; fixation on/off conditionally sends one
  `stop` using cached fixation state. Neither physical outcome is verified.
  The UI's Stop/Release/Hold description does not prove that wire mapping.
  Do not automatically substitute documented `fix`, duplicate or retry Stop.

## Telemetry: observations, not measured percentages

The manufacturer defines `pos:c` as closed and `pos:o` as open: binary position,
not measured percentage feedback. Unknown/missing position is unknown locally.
The tilt cover exposes exactly `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION` and
`STOP_TILT` on one `WINDOW` entity, without standard-action aliases.
Requested targets and near-frame/idle inference in `cover.py` are not measurements,
execution acknowledgements or a calibrated accuracy claim. Do not add timers
or use inferred equality as proof of a physical position.

The vendor identifies `s` as state code, `rssi` as signal strength, `fix` as fixation,
`ro` as ridge-inside indication and `ip` as a 32-bit address representation.
Its MQTT page does not formalize state-code tables, RSSI units, boolean domains
or polarity. Source maps `fix == "1"`, `ro == "0"`, and little-endian packed IP;
these are implementation mappings, not a formal firmware contract.
Unknown integer state codes map to `UNKNOWN`; inherited error classification/logging
of UNKNOWN does not establish a physical fault. Sample `ok` is not a documented ACK.

The MQTT page separately defines `e` as "error code" and illustrates `e:0`, without
a code table, value grammar or explicit zero-value meaning. The optional, disabled
by default `error_code` diagnostic sensor exposes nonempty values verbatim. Missing,
empty or values exceeding HA's 255-character state limit report unknown, never a
truncated code. Raw snapshot storage remains unchanged by this presentation limit.
Accepted snapshots missing `e` clear the sensor; rejected snapshots preserve it.
The sensor reuses device availability, including retained last-known data, and does
not derive faults, severity, motion, Stop/Fix actions or availability from `e`.
See the [roadmap assessment](development.md#roadmap-assessment-2026-11-07) for the
separate unexpected-movement and parameterless-opening research decisions.

Fork ingestion ignores empty lines, splits at the first colon and rejects malformed
records atomically. Present numeric `s`/`rssi`/`ip` conversions and unsigned IP packing
are validated before committing status. Empty/missing `s` retains UNKNOWN fallback;
no new state-code range or RSSI bounds are asserted. Accepted snapshots replace,
not merge, previous data; missing fields remain optional. Rejected data preserves
last-known state, not freshness. Atomic rejection is fork policy: vendor pages do
not settle complete-versus-partial snapshots or stricter numeric domains.

## Availability, settings and safety limits

Before runtime setup, a false MQTT-client readiness result requests native HA setup retry. This does not require a connected broker, retry device commands or repair missing/disabled/fatally misconfigured MQTT. Tests inject that documented result; no actual client timeout or broker outage is established.

Retained online/status are last-known data. The availability gate requires
HA broker connectivity, a session online observation and accepted status; disconnect
clears the online observation, not cached telemetry. Reconnect alone cannot restore
availability, but retained online replay can satisfy that observation. This is not
fresh device proof, a heartbeat deadline or a read-only freshness handshake.
QoS/publish success is not execution ACK, physical completion, no-replay protection
or an emergency stop. No command expiry, safe retry or firmware deduplication is
established; do not claim that a connectivity gate prevents all queued replay.

Per-device subscription initialization now rolls back returned handles and its owned
discovery reservation on failure/cancellation. A local readiness gate suppresses
provisional and abandoned-attempt callbacks. This is HA resource ownership, not a
firmware acknowledgement or freshness handshake. Native subscribe currently does
not yield; test-only suspension does not establish actual broker replay ordering.
Handlers already executing after successful initialization remain a separate limit.

Inherited settings handling replaces its cached response, filters `cvdist`, copies
the cached dictionary for a write, then requests refresh without awaiting a correlated
response. Firmware full-snapshot application, concurrent-write preservation and
rollback are unverified. Writable `cfdist` versus filtered `cvdist` and the vendor's
read-only calibrated-distance UI remain a mismatch. Keep calibrated distance disabled;
require separate P0 stop/holding and P7 settings evidence before any safety claim or
settings change. Never enable unsafe defaults to work around missing evidence.

Changing brokers can disable vendor service; dual-broker operation is not promised.
Device plans can still act independently; Wi-Fi-off periods prevent remote control.
No broker port, TLS capability, firmware QoS, heartbeat or offline deadline is inferred.

## Software evidence versus remaining acceptance

| Evidence boundary | What it establishes | What it does not establish |
| --- | --- | --- |
| [Direct entity tests](../tests/test_cover_contract.py) | Tilt-only features/properties and delegation to a fake device. | Wire delivery or physical position/holding. |
| [HA service/MQTT tests](../tests/test_cover_services.py) | Real config-entry/platform/service paths with synthetic messages and mocked Paho: payload/QoS/non-retain assertions, 1% target, rejection, hydration, session gating, initialization rollback/retry and bounded unload cases. | Real broker replay/session persistence, execution ACK, fresh hardware telemetry or safe Stop/Fix. |
| [Decoder tests](../tests/test_keyval.py) | Parser syntax/rejection cases. | Firmware field domains or snapshot completeness. |
| [Package tests](../tests/test_package.py) | Offline archive/metadata boundaries. | HACS installation, upgrade, rollback or supported HA range. |
| [Synthetic hosted acceptance](development.md#manual-synthetic-hosted-acceptance) | Exact manual A/B package bytes, matching stopped checkpoint recovery, real isolated broker receipt, stable identity, and retained closed status plus HA closed/zero before fresh fixture publication on restored A. | Native HACS/Marketplace workflows, A reading B-migrated state, general replay/freshness, an independent causal trace of HA updates, firmware or physical Stop/holding. |

Consult the ledger and recorded hosted results for exact versions, source commits
and observed scope. The named synthetic manual transition is tested, not every
release or migration. Supervised hardware, broader broker/session failure and
replay/freshness, native distribution acceptance and a supported HA range remain
release gates.
Any future hardware test needs fresh operator readiness and specific test agreement,
physical safety controls available, and one controller only. No automatic close,
Stop or Fix health probe, blind retry, jam test or second controller is permitted.
Network Stop is not a substitute for the physical safety controls.
