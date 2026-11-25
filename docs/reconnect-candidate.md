# Reconnect status candidate (unreleased)

The integration retains last-known telemetry in memory, but availability now
requires an accepted online observation and accepted status in the current
broker/device session. Both orderings are supported. Broker disconnect or
device offline invalidates the observation. Valid retained status replay can
restore availability when online is also observed, so quiet devices need not
generate motion or a new status event just to become available.

The cover's status_source attribute distinguishes retained, non_retained,
previous_session and unknown. None of these is a proof of physical position
freshness. The manufacturer publishes retained online/status and Last Will
offline, and reports status on changes. No documented heartbeat interval or
non-actuating status request is established. Do not invent a heartbeat timeout
or trigger movement as a health check. Arbitrary queued callbacks delivered
after reconnect, broker replay/session persistence and firmware behavior remain
unvalidated. Motion/Stop/Fix wire commands are unchanged.

The two new order/provenance regression cases fail on the preceding candidate
and pass with the new policy. Existing multi-device/reload/error-code tests
retain their cache checks, but now explicitly require new session status before
availability is restored. No hardware or live broker used.

Source: https://vektiva.gitlab.io/vektivadocs/en/api/mqtt.html
