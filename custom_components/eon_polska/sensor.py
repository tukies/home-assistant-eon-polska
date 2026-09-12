"""Latest reported interval and data-quality sensors; history uses external statistics."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        EonSensor(coordinator, ppe, key)
        for ppe in coordinator.data
        for key in ("import", "export", "reported_at", "excluded_values")
    )


class EonSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, ppe, key):
        super().__init__(coordinator)
        self.ppe, self.key = ppe, key
        self._attr_unique_id = f"{ppe}_{key}"
        self._attr_name = {
            "import": "Latest hourly grid import",
            "export": "Latest hourly grid export",
            "reported_at": "Latest interval start",
            "excluded_values": "Excluded energy values",
        }[key]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, ppe)},
            "name": coordinator.data[ppe]["point"]["name"],
            "manufacturer": "E.ON Polska",
        }
        if key in ("import", "export"):
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = "kWh"
            # No state_class: polling old intervals must not create energy at poll time.
        elif key == "reported_at":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        result = self.coordinator.data[self.ppe]
        last = result["readings"][-1]
        if self.key == "reported_at":
            return last.start
        if self.key == "excluded_values":
            return sum(
                r.value(d, self.coordinator.entry.data["include_estimates"]) is None
                for r in result["readings"]
                for d in ("import", "export")
            )
        value = last.value(self.key, self.coordinator.entry.data["include_estimates"])
        return float(value) if value is not None else None

    @property
    def extra_state_attributes(self):
        result = self.coordinator.data[self.ppe]
        return {
            "data_status_counts": result["quality"],
            "interval_start": result["readings"][-1].start.isoformat(),
            "includes_estimates": self.coordinator.entry.data["include_estimates"],
            "statistics_import": f"{DOMAIN}:{self.ppe}_import",
            "statistics_export": f"{DOMAIN}:{self.ppe}_export",
        }
