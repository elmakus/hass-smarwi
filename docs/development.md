# Development and release gates

## Current status

This is an independently maintained, MQTT-only fork of `jirutka/hass-smarwi`. The P1a bootstrap changes metadata, documentation, and packaging only. Production Python remains identical to upstream v0.3.5 at `6a528f35a695bfb5b70e5fe22eb113a163ef7999`.

The source version is `0.4.0.dev0`, not a published or hardware-tested release. There is no validated Home Assistant support range or firmware matrix. The inherited `homeassistant: 2024.1.0` HACS declaration was removed because it was not backed by tests. Omitting that filter does not mean every Home Assistant version works. A tested minimum must be declared before publishing a release.

The integration domain remains `smarwi`. One `WINDOW` cover retains exactly `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION`, and `STOP_TILT`. Standard cover controls, standard-action aliases, HTTP control/polling/fallback, dashboard dependencies, and additional actuator entities are outside scope.

## Offline package checks

Run these commands from the repository root. Python 3.13 and Git are sufficient; no third-party packages, HA instance, MQTT broker, or device are needed.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_release.py --tag 0.4.0.dev0
```

The builder creates `dist/smarwi.zip`, with a flat integration root and the original root `LICENSE`. It uses tracked integration source, translations, and PNG brand assets. It rejects unexpected tracked files, symlinks, missing required assets, mismatched tags, and mismatched HACS filenames. It ignores untracked local files and never packages repository metadata, parent workspace files, or the whole checkout. New integration files must be tracked before packaging; adding a new runtime file type requires updating the allowlist and tests.

The builder does not edit the manifest or overwrite an existing ZIP. Use `--output /path/to/a/new/directory/smarwi.zip` for another build. The output basename must match `hacs.json`. A matching tag is only a metadata check, not permission to publish.

The **Package** workflow runs the same checks on pull requests to `main`, pushes to `main`, and manual dispatch. Its optional `tag` input must match the source manifest exactly. It saves a development ZIP as an Actions artifact; it has no release event or release-upload step and cannot publish a release. Do not install its untested artifact on a live window.

Hassfest and HACS validation check metadata. The inherited Ruff/basedpyright workflow still uses HA 2024.8.0 on Python 3.12. Neither those checks nor Python 3.13 packaging tests establish runtime compatibility with current HA. Do not run `scripts/develop` as an offline check: it starts Home Assistant.

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
