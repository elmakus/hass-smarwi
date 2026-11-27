# SMARWI Integration — independently maintained fork
<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/custom_components/smarwi/brand/logo.png" width="250px" align="right">

[![GitHub Release][releases-shield]][releases]

Home Assistant integration for Vektiva [SMARWI][smarwi-website] window opener (actuator).

This independently maintained fork of [jirutka/hass-smarwi][upstream] uses only Home Assistant's MQTT connection. It has no cloud dependency, HTTP control, HTTP polling, or HTTP fallback. Device commissioning through the local web interface is separate from integration communication.

The top-mounted actuator controls window tilt. Its single `WINDOW` cover exposes only `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION`, and `STOP_TILT`. There are no standard cover-action aliases or standard position controls. Use native tilt actions in dashboards and automations.

**Version 0.5.0** targets Home Assistant 2026.11.0 and later. See [release notes](docs/release-0.5.0.md) for the quality improvements and acceptance scope. The previous [0.4.0 release](docs/release-0.4.0.md) includes bounded physical-device observations; they are not new physical tests of 0.5.0.

> [!WARNING]
> Public tilt percentage is zero only for accepted closed telemetry, including cache; otherwise it is unknown. Requested targets and private motion estimates are not measured feedback. A moving Stop retains the inherited double command; network Stop is not an emergency-stop guarantee. Keep physical safety controls available. Other firmware, extended outages, stopping force and general mechanical safety are not certified. Calibrated distance remains read-only.

See [development and release gates](docs/development.md) and the [upstream ledger](docs/upstream.md).


## Installation

The [stable version][stable-release] targets Home Assistant 2026.11.0 and later. The domain remains `smarwi`; do not install this fork alongside another repository using that domain. Back up the existing integration before updating and restart Home Assistant after installation.

### Using native Home Assistant Marketplace

1. Read and accept Home Assistant's custom-integration warning only if you accept its risks; use the normal GitHub connection flow if needed.
1. Add `https://github.com/elmakus/hass-smarwi` as a custom integration repository, not the upstream repository. This fork is not in the default catalog.
1. Select the latest stable version. Prereleases are not required.
1. Download the integration and restart Home Assistant.

Earlier native prerelease installation and update evidence is recorded in [development.md](docs/development.md). See the [0.5.0 release notes](docs/release-0.5.0.md) for the current acceptance scope.

### Using Home Assistant Community Store (HACS)

These retained legacy instructions were not exercised in the native Marketplace test.

1. Ensure that [HACS] is installed.
1. Add `https://github.com/elmakus/hass-smarwi` as a custom repository with category **Integration**. This fork is not in the default catalog.
1. Select **SMARWI (elmakus fork)** and the latest stable version.
1. Download the integration.
1. Restart Home Assistant.

**TIP:** You can skip steps 2–3 by opening:

[![Add elmakus/hass-smarwi repository to your Home Assistant instance][my-hacs-repo-img]][my-hacs-repo]


### Manually

1. Download `smarwi.zip` from the [stable version][stable-release].
1. Create `custom_components/smarwi` inside the Home Assistant configuration directory.
1. Extract the ZIP contents directly into that directory. `manifest.json` and `__init__.py` must be immediately inside `custom_components/smarwi`, without an extra enclosing folder.
1. Restart Home Assistant.


## Configuration

These are commissioning instructions, not part of an offline development test. Changing the device's configured broker can disable vektiva.online service. No simultaneous vendor/local broker operation is promised. Device plans can still act independently; Wi-Fi-off periods prevent remote control.

### 1. Set up MQTT broker

1. Install the Mosquitto broker app and set up the [MQTT integration][mqtt-integration], if you don’t have it already (see [documentation][mosquitto-addon]).
1. Create a new (MQTT) user for SMARWI. You have two options:
   * Go to **[Settings > Apps > Mosquitto broker][my-hass-mosquitto] > Configuration** and click **Add** below **Logins** to create a local MQTT user,
   * _or_ go to **[Settings > People > Users][my-hass-users]** and click **Add user** to create a Home Assistant user that can be used to connect to MQTT.

> [!IMPORTANT]
> Don’t set a password longer than 18 characters (limitation of SMARWI)!

> [!NOTE]
> You may also use an external Mosquitto broker (or any other MQTT broker), for example, if you are _not_ running Home Assistant Operating System (HAOS).


### 2. Prepare SMARWI devices

For each SMARWI device:

1. Connect to your SMARWI device and open its web interface in the browser (see section 6.1.2 in the [SMARWI manual][smarwi-manual]).
1. Go to **Settings > Advanced**, fill domain name or IP address of your local MQTT broker (i.e. your Home Assistant, if you use the Mosquitto broker app on HAOS), and click **Save**.
1. Go to **Basic** and fill in the following:
   - **Device name** – this will be used in Home Assistant to identify each SMARWI device;
   - **Remote ID** – the MQTT username (use the same for all your SMARWI devices), it will also be used as a prefix for MQTT topics (`ion/<remote-id>/%<device-id>/+`);
   - **Remote Key** – the MQTT password (max 18 characters) or leave empty if you connect to the MQTT broker anonymously;
   - **Wifi Mode** – change to `Client`;
   - **Select Wifi network** – select SSID of your Wi-Fi network;
   - **Wifi Password** – password for your Wi-Fi network (max 32 characters).
1. Click on **Save**.

SMARWI should be connected to your Wi-Fi network and MQTT broker now.


### 3. Add integration

1. Browse to your Home Assistant instance.
1. Go to **Settings > Devices & Services**.
1. In the bottom right corner, select the **⊕ Add Integration** button.
1. From the list, select **SMARWI**.
1. Fill in the **Remote ID** that you choose for your SMARWI devices (see above).

The configuration flow checks that Home Assistant MQTT is connected before saving the entry. This validates the transport, not the identity or physical state of any window. Devices are discovered when their MQTT messages arrive under the selected Remote ID. Home Assistant can also offer a new namespace for explicit confirmation after observing a documented online message through its native MQTT discovery. The discovery subscription matches ion/+/+/online, subject to the configured broker ACLs. It does not publish commands, establish physical freshness or authenticate a device. Confirm only namespaces belonging to your devices; manual setup remains available if the broker restricts wildcard subscriptions.

**TIP:** You can skip steps 1–4 by opening:

[![Add SMARWI integration to your Home Assistant instance][my-hass-config-start-img]][my-hass-smarwi]


### Configuration parameters

| Parameter | Description |
| --- | --- |
| Remote ID | Required MQTT topic namespace configured on your SMARWI devices; case-sensitive, no leading/trailing whitespace or MQTT topic separators/wildcards. Not a password. |

Broker address, authentication and connection settings are managed by the separate MQTT integration. To correct the Remote ID, use **Settings > Devices & Services > SMARWI > Reconfigure**. This updates the existing config entry without creating another one. The integration reloads only if entry data or its identity changes. It does not change the namespace on the physical devices. Confirm any unconfirmed device settings independently before a reload or reconfiguration; an active or unconfirmed settings write blocks reconfiguration while the entry is loaded.

## Entities

The integration will create the following entities for each discovered SMARWI device.

| Name                | Platform      | Category   | Description
| ------------------- | ------------- | ---------- | --------------------------------------------------------------------------|
| cover               | cover         |            | WINDOW cover with tilt-only actions: open tilt, close tilt, stop tilt, and set tilt position. Accepted closed telemetry reports 0%; other positions are unknown. |
| ridge_fix           | switch        |            | Fix or release the ridge. |
| ridge_inside        | binary_sensor | diagnostic | Shows if the ridge is inside the device (i.e. it’s operational). |
| rssi                | sensor        | diagnostic | Monitor WiFi signal strength (disabled by default). |
| error_code          | sensor        | diagnostic | Raw reported `e` value (disabled by default). Missing/empty values are unknown; no fault meanings or healthy-state guarantee are inferred. |
| calibrated_distance | number        | config     | Legacy number identity, disabled by default. The integration rejects all writes; the observed calibration distance is read-only. |
| closed_hold_power   | number        | config     | Set closed holding power (finetune setting). |
| closed_position     | number        | config     | Set window closed position finetune (finetune setting). |
| frame_power         | number        | config     | Set near frame power (finetune setting). |
| frame_speed         | number        | config     | Set near frame speed (finetune setting). |
| lock_err_trigger    | number        | config     | Set window locked error trigger (finetune setting). |
| max_open_position   | number        | config     | Set maximum open position (finetune setting). |
| move_power          | number        | config     | Set movement power (finetune setting). |
| move_speed          | number        | config     | Set movement speed (finetune setting). |
| opened_hold_power   | number        | config     | Set opened holding power (finetune setting). |


## Data updates and limitations

SMARWI pushes status over the configured MQTT broker. Devices are discovered under the configured Remote ID; no polling or vendor cloud account is required. The integration requires accepted online and status observations in the current broker session. Retained observations can restore cached state but do not establish physical freshness. Advanced settings are requested when online messages arrive; a write requires an idle device and complete live readbacks before and after the write.

Only the Vektiva SMARWI tilt actuator using the documented MQTT protocol is supported. Other window actuators and firmware variants are not verified. The Remote ID is an MQTT topic namespace, not a password; authentication is configured in the MQTT integration and on each device.

## Automation example

Use the native tilt action, not standard cover open/close actions. Replace the entity ID with your own. Only use remote movement when it is mechanically safe.

```yaml
action: cover.set_cover_tilt_position
target:
  entity_id: cover.example_window
data:
  tilt_position: 30
```

This requests ventilation; it does not report measured tilt percentage.

## Troubleshooting

- If entities are unavailable, check the MQTT integration, device power, Wi-Fi and matching Remote ID. After reconnect, both online and status observations must arrive.
- If a window cover is unavailable while other entities are available, check the actual fixation and device state locally. Unknown fixation and error/calibration states disable the cover.
- If a settings write is unconfirmed, Home Assistant creates a persistent repair warning. Do not retry blindly or move the window to test the settings. Independently verify the device settings before reloading the integration; dismiss the repair only after verification.
- Download integration diagnostics from Settings > Devices & Services for cached, allowlisted availability and status information. Raw topics, device IDs, names and IP addresses are intentionally omitted.

## Screenshots

<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/images/screenshot-device.png" width="500px" align="left" alt="Screenshot of the device dashboard">

<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/images/screenshot-cover-position.png" width="300px" alt="Screenshot of the cover control in position mode">

<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/images/screenshot-cover-buttons.png" width="300px" alt="Screenshot of the cover control in button mode">


## Removal

For an authorized test installation, remove the SMARWI configuration entry under **Settings > Devices & Services**, then remove this repository through the installer used (native Marketplace or HACS). For a manual installation, remove only `custom_components/smarwi`. Restart Home Assistant after removing the integration files.

A device that has been permanently removed can be removed manually from the device registry when it has not been discovered in the loaded entry. Temporary outages do not cause automatic removal. Reload only after verifying any pending settings. If the device publishes again, it will be rediscovered.

Removing this integration does not change device plans, broker settings, calibration, or physical window position. Do not change shared MQTT settings or send movement/Stop commands as cleanup.


## Resources

- [SMARWI product website][smarwi-website]
- [SMARWI user manual][smarwi-manual]
- [SMARWI API documentation][smarwi-api-doc]


## License

This project is licensed under the [MIT License](LICENSE). Original copyright and attribution notices remain intact. Jakub Jirutka and Joakim Sørensen are credited in `LICENSE`; elmakus independently maintains this fork. Product names and images identify their respective owners and do not imply endorsement.


[upstream]: https://github.com/jirutka/hass-smarwi
[releases]: https://github.com/elmakus/hass-smarwi/releases
[stable-release]: https://github.com/elmakus/hass-smarwi/releases/latest
[releases-shield]: https://img.shields.io/github/release/elmakus/hass-smarwi.svg?style=flat-square
[HACS]: https://hacs.xyz/
[smarwi-website]: https://vektiva.com/index.php/en/
[smarwi-manual]: https://vektiva.com/downloads/SMARWI_manual_EN.pdf
[smarwi-api-doc]: https://vektiva.gitlab.io/vektivadocs/en/api/index.html
[my-hass-smarwi]: https://my.home-assistant.io/redirect/config_flow_start/?domain=smarwi
[my-hass-config-start-img]: https://my.home-assistant.io/badges/config_flow_start.svg
[my-hass-mosquitto]: https://my.home-assistant.io/redirect/supervisor_addon/?addon=core_mosquitto
[my-hass-users]: https://my.home-assistant.io/redirect/users/
[my-hacs-repo]: https://my.home-assistant.io/redirect/hacs_repository/?owner=elmakus&repository=hass-smarwi&category=Integration
[my-hacs-repo-img]: https://my.home-assistant.io/badges/hacs_repository.svg
[mosquitto-addon]: https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md
[mqtt-integration]: https://www.home-assistant.io/integrations/mqtt/
