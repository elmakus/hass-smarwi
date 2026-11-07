# SMARWI Integration — independently maintained fork
<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/custom_components/smarwi/brand/logo.png" width="250px" align="right">

[![GitHub Release][releases-shield]][releases]

Home Assistant integration for Vektiva [SMARWI][smarwi-website] window opener (actuator).

This independently maintained fork of [jirutka/hass-smarwi][upstream] uses only Home Assistant's MQTT connection. It has no cloud dependency, HTTP control, HTTP polling, or HTTP fallback. Device commissioning through the local web interface is separate from integration communication.

The top-mounted actuator controls window tilt. Its single `WINDOW` cover exposes only `OPEN_TILT`, `CLOSE_TILT`, `SET_TILT_POSITION`, and `STOP_TILT`. There are no standard cover-action aliases or standard position controls. Use native tilt actions in dashboards and automations.

> [!WARNING]
> Experimental prerelease: [`0.4.0.dev1`](https://github.com/elmakus/hass-smarwi/releases/tag/0.4.0.dev1) is available, with a completed native Marketplace upgrade/downgrade/upgrade cycle. Earlier bounded real-device tilt-action tests apply only to `0.4.0.dev0`, not `0.4.0.dev1`. This fork includes software fixes recorded in the upstream ledger. The development baseline is Home Assistant `2026.11.0`, the latest stable release checked on 2026-11-07. Older HA versions are outside the testing scope; general firmware compatibility and full release acceptance remain unvalidated. Live-window testing requires explicit, bounded operator authorization and physical safety controls.
>
> Public tilt percentage is zero only for accepted closed telemetry, including cache; otherwise it is unknown. Requested targets and private motion/direction estimates are not measured feedback. A moving Stop was followed by device IDLE telemetry; halt latency, force, mechanical holding, general broker replay, freshness and settings safety remain unverified. Do not treat network Stop as an emergency-stop guarantee or enable writable calibrated distance. Keep the physical safety controls available.

See [development and release gates](docs/development.md) and the [upstream ledger](docs/upstream.md).


## Installation

The available [experimental prerelease `0.4.0.dev1`][prerelease] targets Home Assistant `2026.11.0`. This fork retains domain `smarwi`; do not install it alongside another repository using that domain. Normal versioned replacement/restart passed for `0.4.0.dev0` → `0.4.0.dev1` → `0.4.0.dev0` → `0.4.0.dev1`; schema-migration compatibility and interrupted-install/restart recovery remain unverified.

### Using native Home Assistant Marketplace

1. Read and accept Home Assistant's custom-integration warning only if you accept its risks; use the normal GitHub connection flow if needed.
1. Add `https://github.com/elmakus/hass-smarwi` as a custom integration repository, not the upstream repository. This fork is not in the default catalog.
1. Enable prereleases for this repository and explicitly select `0.4.0.dev1`.
1. Download the integration and restart Home Assistant.

The native path was tested with explicit-version `update.install` calls, exact installed-file verification and three normal restarts preserving the configured entry and repository/version metadata. Initial installation reused an existing GitHub connection; new-account setup was not tested. See [current acceptance](docs/development.md#published-dev1-and-native-version-cycle-2026-11-07) for boundaries.

### Using Home Assistant Community Store (HACS)

These retained legacy instructions were not exercised in the native Marketplace test.

1. Ensure that [HACS] is installed.
1. Add `https://github.com/elmakus/hass-smarwi` as a custom repository with category **Integration**. This fork is not in the default catalog.
1. Select **SMARWI (elmakus fork)** and the published experimental prerelease (enable prereleases if needed).
1. Download the integration.
1. Restart Home Assistant.

**TIP:** You can skip steps 2–3 by opening:

[![Add elmakus/hass-smarwi repository to your Home Assistant instance][my-hacs-repo-img]][my-hacs-repo]


### Manually

1. Download `smarwi.zip` from the [available prerelease][prerelease].
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

The integration should now automatically detect all your SMARWI devices.

**TIP:** You can skip steps 1–4 by opening:

[![Add SMARWI integration to your Home Assistant instance][my-hass-config-start-img]][my-hass-smarwi]


## Entities

The integration will create the following entities for each discovered SMARWI device.

| Name                | Platform      | Category   | Description
| ------------------- | ------------- | ---------- | --------------------------------------------------------------------------|
| cover               | cover         |            | WINDOW cover with tilt-only actions: open tilt, close tilt, stop tilt, and set tilt position. Accepted closed telemetry reports 0%; other positions are unknown. |
| ridge_fix           | switch        |            | Fix or release the ridge. |
| ridge_inside        | binary_sensor | diagnostic | Shows if the ridge is inside the device (i.e. it’s operational). |
| rssi                | sensor        | diagnostic | Monitor WiFi signal strength (disabled by default). |
| error_code          | sensor        | diagnostic | Raw reported `e` value (disabled by default). Missing/empty values are unknown; no fault meanings or healthy-state guarantee are inferred. |
| calibrated_distance | number        | config     | Inherited writable calibration value, disabled by default. Do not enable: write semantics are unverified and the manufacturer's UI treats it as read-only. |
| closed_hold_power   | number        | config     | Set closed holding power (finetune setting). |
| closed_position     | number        | config     | Set window closed position finetune (finetune setting). |
| frame_power         | number        | config     | Set near frame power (finetune setting). |
| frame_speed         | number        | config     | Set near frame speed (finetune setting). |
| lock_err_trigger    | number        | config     | Set window locked error trigger (finetune setting). |
| max_open_position   | number        | config     | Set maximum open position (finetune setting). |
| move_power          | number        | config     | Set movement power (finetune setting). |
| move_speed          | number        | config     | Set movement speed (finetune setting). |
| opened_hold_power   | number        | config     | Set opened holding power (finetune setting). |


## Screenshots

<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/images/screenshot-device.png" width="500px" align="left" alt="Screenshot of the device dashboard">

<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/images/screenshot-cover-position.png" width="300px" alt="Screenshot of the cover control in position mode">

<img src="https://raw.githubusercontent.com/elmakus/hass-smarwi/main/images/screenshot-cover-buttons.png" width="300px" alt="Screenshot of the cover control in button mode">


## Removal

For an authorized test installation, remove the SMARWI configuration entry under **Settings > Devices & Services**, then remove this repository through the installer used (native Marketplace or HACS). For a manual installation, remove only `custom_components/smarwi`. Restart Home Assistant after removing the integration files.

Removing this integration does not change device plans, broker settings, calibration, or physical window position. Do not change shared MQTT settings or send movement/Stop commands as cleanup.


## Resources

- [SMARWI product website][smarwi-website]
- [SMARWI user manual][smarwi-manual]
- [SMARWI API documentation][smarwi-api-doc]


## License

This project is licensed under the [MIT License](LICENSE). Original copyright and attribution notices remain intact. Jakub Jirutka and Joakim Sørensen are credited in `LICENSE`; elmakus independently maintains this fork. Product names and images identify their respective owners and do not imply endorsement.


[upstream]: https://github.com/jirutka/hass-smarwi
[releases]: https://github.com/elmakus/hass-smarwi/releases
[prerelease]: https://github.com/elmakus/hass-smarwi/releases/tag/0.4.0.dev1
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
