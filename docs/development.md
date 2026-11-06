# Development and release gates

## Current status

This is an independently maintained, MQTT-only fork of `jirutka/hass-smarwi`. The P1a bootstrap changed metadata, documentation, and packaging only. The local P3a topic below adds bounded message-syntax handling and a direct `DeviceInfo` import to the inherited upstream v0.3.5 production baseline (`6a528f35a695bfb5b70e5fe22eb113a163ef7999`).

The source version is `0.4.0.dev0`, not a published or hardware-tested release. There is no validated Home Assistant support range or firmware matrix. The inherited `homeassistant: 2024.1.0` HACS declaration was removed because it was not backed by tests. Omitting that filter does not mean every Home Assistant version works. A tested minimum must be declared before publishing a release.

The integration domain remains `smarwi`. One `WINDOW` cover retains exactly `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION`, and `STOP_TILT`. Standard cover controls, standard-action aliases, HTTP control/polling/fallback, dashboard dependencies, and additional actuator entities are outside scope.

## Consistent formatting

Use Ruff `0.14.3`, pinned in `requirements.txt`, for the fork-maintained packaging script and tests. Install that version in your tooling environment without replacing the HA test environment or installing the legacy HA 2024 requirements into it. Run these commands before committing:

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

Hassfest and HACS validation check metadata. The inherited Ruff/basedpyright workflow still uses HA 2024.8.0 on Python 3.12. Neither those checks nor Python 3.13 packaging tests establish runtime compatibility with current HA. Do not run `scripts/develop` as an offline check: it starts Home Assistant.

## Direct tilt-contract baseline (P2a)

Use Python 3.14.2 or newer in a dedicated development environment. These tests import the real pinned HA entity classes but do not construct or start a Home Assistant instance. They use only a fake device, mock its commands, and block socket connections, DNS and HA MQTT publish/subscribe calls during each test. Do not run them inside an operating HA installation.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-tests.txt
.venv/bin/python -m unittest discover -s tests -p test_cover_contract.py -v
```

For an existing environment, install the test requirements into that environment; do not replace it. A uv-created environment may have no pip; use an installed `uv pip install --python .venv/bin/python -r requirements-tests.txt` in that case. The **Tests / Tilt contract** job uses Python 3.14 and the same pins. Package checks select only `test_package.py`, so they remain usable without HA installed. Importing the entity can create Python bytecode caches; packaging fixtures exclude those caches instead of treating them as runtime source.

Eight direct entity tests protect `WINDOW`, exactly four tilt features, absence of standard-action aliases, the tilt-position property, `is_closed`, and delegation of the four native tilt methods. The Stop case supplies an actual moving state and checks that inferred position is invalidated. The 0/1/10/30/100 entity-payload cases stop at a mocked device boundary: they do not exercise or fix the known `device.async_open(1)` command-encoding defect.

These direct tests remain useful unit tests, not integration acceptance. The next slice exercises setup and services through HA instead of replacing those interfaces.

## Public setup and tilt-service baseline (P2b)

`requirements-tests.txt` pairs HA `2026.11.0` with the official `pytest-homeassistant==2026.11.0` fixtures and `paho-mqtt==2.1.0`. It also pins `aiohasupervisor==0.8.1`, matching HA's Supervisor manifest: MQTT's config flow imports it even without a Supervisor installation. The [official fixture README](https://github.com/home-assistant/core/blob/74cf5a49c63ed8d4d87717844bf14f79c28c9cea/packages/pytest-homeassistant/README.md) explains the version pairing and pytest settings. Do not install the overlapping legacy `pytest-homeassistant-custom-component`; its `0.13.375` release requires HA `2026.10.4`, not our pinned version.

```sh
.venv/bin/python -m pytest tests/test_cover_services.py -q
.venv/bin/python -m pytest -q
```

The P2b baseline introduced 36 passing tests and one strict expected failure. The required **Tilt contract** job runs the full pytest suite, including the original direct entity and packaging tests. The dependency-free package-only unittest command above is unchanged. See P3a below for the current local test count.

The new tests set up a real SMARWI config entry through `hass.config_entries.async_setup`, load its real platforms, and discover a synthetic serial through HA's MQTT message callbacks. They resolve the registered cover by its existing serial-derived unique ID. Calls through `hass.services.async_call` verify native tilt payloads, QoS 2 and non-retained publishing at the mocked HA client boundary. HA rejects invalid tilt payloads and explicitly targeted standard actions without publishing. State-machine assertions verify WINDOW, exactly the four tilt features, unknown tilt and observed closed/zero tilt without standard position attributes. A moving Stop case characterizes the inherited two mocked `stop` publishes and position invalidation after subsequent idle telemetry. Public unload removes the active cover and prevents later synthetic discovery from recreating it.

The 1% target remains a **strict xfail**, not a pass: the desired `open;1` payload currently becomes `close` in production device code. Only one `close` publish with the exact expected topic, QoS and flags raises the dedicated expected-failure exception. Missing/duplicate publishes, other payloads, service errors and fixture assertions fail normally. An unexpected pass fails CI, so a later P6 fix must remove that marker. Dependency and setup checks are not bypassed.

The official `hass` and `mqtt_mock` fixtures create disposable in-process HA objects with a mocked Paho client. No HA server is started, no live HA installation is accessed, and no real broker or device is connected. Additional guards block socket connections, UDP sends, server binds/listens and DNS, including loopback. A small fixture completes the upstream Paho mock's missing socket-close callback on disconnect, so HA cancels its actual MQTT timer; cleanup checks remain enabled. Storage, translations, registries, platform forwarding and HA service dispatch use the official fixtures, not a hand-built HA replacement.

This is still a bounded baseline, not full P2/P8 acceptance. Initial retained/cached hydration, broker reconnect/session replay, availability/freshness, reload races, settings, config-flow validation, supported-version range and HACS install/update remain open. The synthetic fixture deliberately sends a separate online update after discovery; that does not prove initial cached hydration. Stop does not immediately refresh the HA state machine before telemetry, and two mocked payloads do not validate physical halt or holding. At the P2b baseline, production Python and the source release version remained unchanged. No hardware safety or Bronze quality-scale compliance is claimed; config-flow coverage, duplicate prevention and typed runtime data are among the existing gaps.

## Key/value message syntax (P3a local topic)

```sh
.venv/bin/python -m pytest tests/test_keyval.py tests/test_cover_services.py -q
.venv/bin/python -m pytest -q
```

The shared decoder ignores empty lines, including leading/internal/trailing empty LF or CRLF lines. It still splits only at the first colon. Values, unknown keys and the inherited duplicate-key behavior are unchanged; whitespace is not normalized. A nonempty line without a colon rejects the entire message. Both MQTT callbacks catch that parse failure before changing a snapshot or dispatching an update. The advanced-configuration callback also catches failed integer conversions before assignment. New rejection warnings do not include raw payloads.

An empty or unknown-only status is ignored without entity registration, snapshot replacement or an update signal. An advanced-configuration message with no writable records, including a response containing only the inherited read-only `cvdist` field, also leaves the previous snapshot unchanged. Unknown integer configuration keys remain preserved. Accepted nonempty snapshots still replace the previous dictionary; this topic does not introduce merging or require a complete set of fields. The [manufacturer MQTT documentation](https://vektiva.gitlab.io/vektivadocs/en/api/mqtt.html) describes newline-separated `key:value` status but does not settle complete-versus-partial updates. The rejection policy is a conservative implementation choice, not a verified firmware contract.

Twelve decoder cases and eighteen additional public MQTT cases cover blank lines, malformed records, ignored empty/unknown-only status, noninteger configuration values, snapshot preservation, no discovery/update signal or command publish on rejection, and recovery on the next valid message. The first regression run failed before the production change. The local full suite now has **66 passes and one strict expected failure**, plus 25 unittest subtests, on the existing pinned HA 2026.11.0 environment. The expected failure still represents the separate 1% command-encoding defect. All transport remains mocked and network guards remain enabled.

Active diagnostics also identified the inherited indirect `DeviceInfo` import as private in pinned HA. Importing the same class directly from `homeassistant.helpers.device_registry` resolves that finding without changing runtime behavior. Three inherited numeric-conversion warnings for status `ip`, `rssi` and `s` remain. Status numeric/domain validation, unknown position handling, topic validation, initial cached hydration, availability and settings transactions remain separate work. Keeping the previous snapshot does not establish freshness or safe writes.

This topic was developed offline. Upstream, current contributor documentation and remote CI were not refreshed; no upstream-ready branch, PR, deployment or release was created. Refresh upstream and prepare an isolated production topic before submission. These checks do not complete P3 or establish Bronze compliance, a supported HA range or physical safety.

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
