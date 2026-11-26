# SMARWI 0.4.0

## Changes

- MQTT-only native tilt controls; preserve the domain and entity identity.
- Serialize mechanical setting updates, request a complete non-retained readback before writing, verify the writable settings afterward, and block further writes after an uncertain result until operator verification and integration reload. Exclude calibration distances from writes; do not blindly retry.
- Require status and online observations in the current broker/device session. Expose status provenance as `status_source`; retained telemetry is not proof of physical freshness.
- Report missing/invalid fixation and tamper fields as unknown. Require known fixation for cover availability.
- Correct closing-direction reporting for a zero target after Stop invalidates the private position estimate.
- Preserve the inherited double Stop command. Public tilt position remains zero only when accepted closed telemetry reports closure; otherwise it is unknown.

## Acceptance (2026-11-26)

The candidate (before the stable manifest version change) passed 278 tests and 101 subtests with pinned Home Assistant and official fixtures 2026.11.0, Ruff and strict basedpyright. One supervised physical device on HA 2026.11.3 completed opening, changing tilt, closing, release and re-fix. Stop returned IDLE telemetry; the subsequent close-direction correction was verified by isolated regression tests. A reversible movement-speed setting change and restoration were confirmed by independent device readbacks, including unchanged remaining settings and calibration fields. A targeted broker-initiated device session disconnect produced unavailable and recovered with new telemetry, without restarting the broker or the HA MQTT client.

These are bounded observations, not a firmware compatibility matrix, mechanical safety certification, or a guarantee of physical holding or stopping latency. Extended Wi-Fi loss, message replay, correlated write acknowledgement, and arbitrary concurrent external controllers remain unverified. No calibration change was performed. Keep physical safety controls available. No new dependencies, entity IDs, config-entry migration or protocol changes to Stop.

The minimum declared HA version remains 2026.11.0. Older versions are untested. Install the exact published flat smarwi.zip and restart HA; the release tag must match the manifest. Historical prerelease and hosted acceptance evidence remains in development.md.
