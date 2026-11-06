# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2024 Jakub Jirutka <jakub@jirutka.cz>
from typing import Any  # pyright:ignore[reportAny]
from typing_extensions import override

from homeassistant.components.mqtt import valid_subscribe_topic
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers.selector import (
    # HA's selector registry erases the concrete generic type.
    TextSelector,  # pyright:ignore[reportUnknownVariableType]
    TextSelectorConfig,
    TextSelectorType,
)
import probatio

from .const import CONF_REMOTE_ID, DOMAIN, NAME

DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_REMOTE_ID): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT),
        ),
    }
)


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
                if (
                    not remote_id
                    or remote_id != remote_id.strip()
                    or any(char in remote_id for char in "/+#")
                ):
                    raise probatio.Invalid(
                        "Remote ID must be one literal topic segment"
                    )
                _ = valid_subscribe_topic(f"ion/{remote_id}/+/online")
            except probatio.Invalid:
                errors[CONF_REMOTE_ID] = "invalid_remote_id"
            else:
                _ = await self.async_set_unique_id(remote_id)
                self._abort_if_unique_id_configured()
                self._async_abort_entries_match({CONF_REMOTE_ID: remote_id})
                return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
