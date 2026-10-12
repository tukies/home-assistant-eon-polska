"""Allowlisted session metadata for Home Assistant diagnostic downloads."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return {"runtime_available": False}
    return {
        "runtime_available": True,
        "session": coordinator.client.diagnostic_data(),
        "renewal": coordinator.renewal.diagnostic_data(),
    }
