# SMARWI 0.5.0

## Changes

- Validate the local MQTT connection at configuration time; add native MQTT namespace discovery with explicit confirmation and duplicate protection.
- Support native reconfiguration without replacing existing config entries or registry identities. Block reconfiguration while a settings write is pending or unconfirmed.
- Add redacted cached diagnostics, availability transition logging, translated errors and entity icons, and actionable Repairs warnings for uncertain settings writes.
- Allow manual removal of an undiscovered stale device from a loaded entry, without automatically removing temporarily offline devices.
- Preserve the last valid device configuration URL when a new status omits its IP.
- Add the integration quality-scale checklist, enforce per-module branch/statement coverage above 95% and config-flow coverage of 100%, and check both the HA minimum and HA 2026.11.3 in CI.
- Correct the dark brand icon dimensions and include new metadata in the flat release ZIP.

## Compatibility and limitations

The minimum remains Home Assistant 2026.11.0. The domain, entity identities, MQTT transport, tilt-only controls, inherited double Stop command, unknown nonzero position feedback, and read-only calibration remain unchanged.

Discovery observes `ion/+/+/online` on the configured broker; broker ACLs still govern visibility. It does not authenticate devices, establish physical freshness or publish actuator commands before confirmation. Only confirm your own namespaces. A persistent Repairs warning requires independent verification after an uncertain write; it does not establish success.

See [0.4.0 acceptance](release-0.4.0.md) for earlier bounded physical-device observations. No new physical action tests or mechanical safety certification are claimed for this candidate. Quality-scale statuses are a self-assessment of the integration, not an official Home Assistant Core certification.

## Installation

Install the exact published `smarwi.zip` through Marketplace and restart Home Assistant after the update. Keep the previous stable release available for rollback. The ZIP tag must match the manifest.
