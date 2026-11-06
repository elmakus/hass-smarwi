# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2024 Jakub Jirutka <jakub@jirutka.cz>
from typing import Any  # pyright:ignore[reportAny]
from typing_extensions import override

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
        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)

        # If there is no user input, show the form again.
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
