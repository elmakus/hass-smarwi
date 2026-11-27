# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2024 Jakub Jirutka <jakub@jirutka.cz>
from typing import Any, cast  # pyright:ignore[reportAny]
from typing_extensions import override

from homeassistant.components import mqtt
from homeassistant.components.mqtt import valid_publish_topic, valid_subscribe_topic
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    ConfigEntryState,
    SOURCE_RECONFIGURE,
)
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo
from homeassistant.helpers.selector import (
    # HA's selector registry erases the concrete generic type.
    TextSelector,  # pyright:ignore[reportUnknownVariableType]
    TextSelectorConfig,
    TextSelectorType,
)
import probatio

from .const import CONF_REMOTE_ID, DOMAIN, NAME
from .device import SmarwiConfigEntry

DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_REMOTE_ID): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT),
        ),
    }
)


def _validate_remote_id(remote_id: str) -> None:
    """Validate one literal namespace shared by manual and discovery flows."""
    if (
        not remote_id
        or remote_id != remote_id.strip()
        or any(char in remote_id for char in "/+#")
    ):
        raise probatio.Invalid("Remote ID must be one literal topic segment")
    _ = valid_subscribe_topic(f"ion/{remote_id}/+/online")


class SmarwiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for SMARWI integration."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            remote_id: str = user_input[CONF_REMOTE_ID]
            try:
                _validate_remote_id(remote_id)
            except probatio.Invalid:
                errors[CONF_REMOTE_ID] = "invalid_remote_id"
            else:
                if (
                    not await mqtt.async_wait_for_mqtt_client(self.hass)
                    or not mqtt.is_connected(self.hass)
                ):
                    errors["base"] = "cannot_connect"
                else:
                    existing = await self.async_set_unique_id(remote_id)
                    self._async_abort_entries_match({CONF_REMOTE_ID: remote_id})
                    if self.source == SOURCE_RECONFIGURE:
                        entry = self._get_reconfigure_entry()
                        if existing is not None and existing is not entry:
                            return self.async_abort(reason="already_configured")
                        if entry.state == ConfigEntryState.LOADED and any(
                            device.finetune_settings.write_pending_or_uncertain
                            for device in cast(SmarwiConfigEntry, entry).runtime_data.values()
                        ):
                            return self.async_abort(reason="settings_unconfirmed")
                        return self.async_update_reload_and_abort(
                            entry,
                            data_updates=user_input,
                            unique_id=remote_id,
                            reload_even_if_entry_is_unchanged=False,
                        )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=NAME, data=user_input)

        if self.source == SOURCE_RECONFIGURE:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(
                    DATA_SCHEMA, self._get_reconfigure_entry().data
                ),
                errors=errors,
            )
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    @override
    async def async_step_mqtt(
        self, discovery_info: MqttServiceInfo
    ) -> ConfigFlowResult:
        """Offer a namespace discovered from a native MQTT online message."""
        parts = discovery_info.topic.split("/")
        if (
            len(parts) != 4
            or parts[0] != "ion"
            or not parts[2].startswith("%")
            or len(parts[2]) == 1
            or parts[3] != "online"
            or discovery_info.payload != "1"
        ):
            return self.async_abort(reason="invalid_discovery")
        remote_id = parts[1]
        try:
            _ = valid_publish_topic(discovery_info.topic)
            _validate_remote_id(remote_id)
        except probatio.Invalid:
            return self.async_abort(reason="invalid_discovery")

        _ = await self.async_set_unique_id(remote_id)
        self._async_abort_entries_match({CONF_REMOTE_ID: remote_id})
        self._abort_if_unique_id_configured()
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Require explicit confirmation before creating any discovered entry."""
        remote_id = self.unique_id
        assert remote_id is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            if (
                not await mqtt.async_wait_for_mqtt_client(self.hass)
                or not mqtt.is_connected(self.hass)
            ):
                errors["base"] = "cannot_connect"
            else:
                self._async_abort_entries_match({CONF_REMOTE_ID: remote_id})
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=NAME, data={CONF_REMOTE_ID: remote_id}
                )
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=probatio.Schema({}),
            description_placeholders={"remote_id": remote_id},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the MQTT namespace without replacing the config entry."""
        return await self.async_step_user(user_input)
