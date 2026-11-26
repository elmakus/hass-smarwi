# Telemetry and Stop review (unreleased)

Known fixation and ridge-presence wire polarity is unchanged. Only literal 0
and 1 establish a boolean; absent/invalid values now remain unknown. The
tamper diagnostic no longer invents an alarm on missing telemetry. The cover
requires known fixation before becoming available. A fixation service request
with unknown fixation state fails without publishing. The missing number
value change was already included in the settings candidate.

The manufacturer documents Stop movement and Fix fixation as separate named
actions, but not their wire-level mechanical postconditions or correlated
acknowledgments. The inherited implementation sends two Stop messages when
cached status indicates movement and no Stop at cached IDLE; fixation toggles
use one Stop. Existing offline tests characterize this sequence, not measured
stopping or holding. A previous dev0-only physical test observed IDLE after
moving Stop but did not measure force, latency or holding. No replacement,
extra Stop, blind retry, motion probe or firmware command changes are proposed
without firmware-specific evidence. Network Stop is not an emergency stop.
The new unknown-state guard does not change the existing known-state payloads.

Source: https://vektiva.gitlab.io/vektivadocs/en/api/api.html and docs/protocol.md.
