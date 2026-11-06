# Upstream and downstream ledger

## Repository policy

- Fork: <https://github.com/elmakus/hass-smarwi>; independently maintained releases.
- Upstream: <https://github.com/jirutka/hass-smarwi>; tracked at `upstream/master`.
- Release branch: `main`. The local `upstream-tracking` branch tracks `upstream/master`. Preserve upstream history; do not merge fork branding into upstream topics.
- Base inspected on 2026-11-06: v0.3.5, `6a528f35a695bfb5b70e5fe22eb113a163ef7999`. No newer default-branch commit or open upstream PR was found.
- Preserve MIT license notices, domain `smarwi`, serial-derived identities, and MQTT-only communication. Do not copy code from other forks to implement packaging.
- Keep parent workspace instructions, handoffs, credentials, and personal device traces out of this repository.

For an upstream-suitable fix, fetch upstream and branch from the fresh upstream base, not accumulated downstream `main`. Record its base, tests, downstream integration commit, and upstream PR status. Keep independent fixes separate; stack only real dependencies. Check for an equivalent upstream patch before applying it downstream. Our releases do not depend on upstream acceptance.

## Topics

| Topic | Base | Tests / evidence | Fork integration | Upstream status |
| --- | --- | --- | --- | --- |
| P1a: independent metadata and offline packaging | `6a528f35a695bfb5b70e5fe22eb113a163ef7999` | 10 offline unittest cases pass; 18 ZIP members match source bytes; production Python unchanged; read-only review found no blockers. GitHub checks are attached to the integration PR. | This fork-only topic commit (`chore/fork-bootstrap`); integration SHA is in `main`'s PR/commit history | Fork-only; do not submit upstream |

## Intentional P1a divergence

- Fork owner, support, documentation, HACS custom-repository links, and default branch point to elmakus rather than upstream. Existing copyright notices remain intact.
- Source version `0.4.0.dev0` identifies an unreleased fork baseline. It is not upstream v0.3.5 or a tested compatibility promise.
- The inherited, untested HACS minimum was removed. A tested minimum is a release gate, not inferred from the old dependency pins.
- ZIPs contain flat integration files and the unchanged root license. The builder checks exact version/asset agreement instead of rewriting a manifest from a tag.
- The package workflow produces inspection-only Actions artifacts. Automatic upload on a published GitHub release is removed until release gates pass. Workflow action references are pinned to inspected commit SHAs, repository permissions are read-only, and checkout credentials are not persisted.
- Production Python is unchanged. `WINDOW` and exactly the four tilt features remain; there are no standard-action aliases or UI-driven feature conversions.

P1a does not complete P1's HACS install/update acceptance. HA runtime regression work, telemetry freshness, 1% targeting, stop/holding policy, settings safety, broker recovery, hardware soak, and releases remain open. See [development and release gates](development.md).
