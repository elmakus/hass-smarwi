# Settings transaction candidate (unreleased)

Base: main at 149a541, production source identical to 0.4.0.dev2.
This branch is an isolated software candidate, not a release or hardware approval.

Per-device serialization, complete non-retained readback before write, observed
full writable readback equality afterwards, vendor-documented value ranges,
idle/available checks, session invalidation, timeout, and explicit rejection of
calibrated-distance writes. Unknown integer settings are preserved as before,
except the two calibration-distance spellings which are never echoed into writes.
A write whose outcome is uncertain blocks further writes until explicit operator
verification and reload; reload does not cancel queued broker deliveries. Missing
number values clear their previous displayed value. No automatic retry.

The manufacturer documents setting ranges and read-only calibrated distance,
but not the inherited advanced-settings wire grammar, complete snapshot semantics,
correlated readbacks or execution acknowledgments. A non-retained response is
only an observation, not proof that it belongs to the current request, and an
idle/available cached status is not fresh physical telemetry. A delayed response,
external controller, offline/reconnect queue or firmware-specific behavior could
still affect results. Do not deploy until these boundaries are reviewed and
firmware-specific behavior is validated with specific operator authorization.
No real device, live Home Assistant or broker is used by the new tests.

Sources:
- https://vektiva.gitlab.io/vektivadocs/en/settings/finetune.html
- https://vektiva.gitlab.io/vektivadocs/en/api/mqtt.html
- docs/protocol.md

Initial four regressions failed against the original code, then passed.
The 13 targeted cases use the repository's real HA setup fixture and synthetic
responses at the command boundary. They cover serialization, missing data,
mismatch, read-only distance, retained response, timeout, session loss,
unload, cancellation, filtering calibration fields, clearing missing number
values, queued request session boundaries and post-write timeout. They are not
hardware tests or a proof of correlated protocol delivery.
