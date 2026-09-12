"""Period summaries and diagnostics, separate from historical Energy statistics."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .summaries import BILLING_FIELDS


@dataclass(frozen=True)
class SensorSpec:
    source: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    diagnostic: bool = False


ENERGY = SensorDeviceClass.ENERGY
SENSORS = {
    "import": SensorSpec("summary", ENERGY, "kWh"),
    "export": SensorSpec("summary", ENERGY, "kWh"),
    "reported_at": SensorSpec("summary", SensorDeviceClass.TIMESTAMP, diagnostic=True),
    "excluded_values": SensorSpec("summary", diagnostic=True),
    "daily_import": SensorSpec("summary", ENERGY, "kWh"),
    "daily_export": SensorSpec("summary", ENERGY, "kWh"),
    "daily_date": SensorSpec("summary", SensorDeviceClass.DATE),
    "refreshed_at": SensorSpec("root", SensorDeviceClass.TIMESTAMP, diagnostic=True),
    "missing_hours": SensorSpec("summary", diagnostic=True),
    "forecast_hours": SensorSpec("summary", diagnostic=True),
    "uncertain_hours": SensorSpec("summary", diagnostic=True),
    "unknown_hours": SensorSpec("summary", diagnostic=True),
    "coverage": SensorSpec("summary", unit="%", diagnostic=True),
    **{
        key: SensorSpec("monthly", ENERGY, "kWh")
        for key in ("month_import", "month_export", "year_import", "year_export")
    },
    **{
        key: SensorSpec("billing", ENERGY, "kWh")
        for key in BILLING_FIELDS
        if key != "oze_factor"
    },
    "oze_factor": SensorSpec("billing"),
    "billing_period_end": SensorSpec("billing", SensorDeviceClass.DATE),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        EonSensor(coordinator, ppe, key) for ppe in coordinator.data for key in SENSORS
    )


def serial(value):
    return value.isoformat() if isinstance(value, date) else value


class EonSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    # None is intentional: a period summary must not add energy at polling time.
    _attr_state_class = None

    def __init__(self, coordinator, ppe, key):
        super().__init__(coordinator)
        self.ppe, self.key = ppe, key
        self.spec = SENSORS[key]
        self._attr_unique_id = f"{ppe}_{key}"
        self._attr_translation_key = key
        self._attr_device_class = self.spec.device_class
        self._attr_native_unit_of_measurement = self.spec.unit
        if self.spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = {
            "identifiers": {(DOMAIN, ppe)},
            "name": coordinator.data[ppe]["point"]["name"],
            "manufacturer": "E.ON Polska",
        }

    @property
    def available(self):
        if not super().available:
            return False
        result = self.coordinator.data[self.ppe]
        return self.spec.source == "root" or result.get(self.spec.source) is not None

    @property
    def native_value(self):
        result = self.coordinator.data[self.ppe]
        source = result if self.spec.source == "root" else result.get(self.spec.source)
        value = source.get(self.key) if source else None
        return float(value) if isinstance(value, Decimal) else value

    @property
    def extra_state_attributes(self):
        result = self.coordinator.data[self.ppe]
        attrs = {
            "includes_estimates": self.coordinator.entry.data["include_estimates"],
            "statistics_import": f"{DOMAIN}:{self.ppe}_import",
            "statistics_export": f"{DOMAIN}:{self.ppe}_export",
        }
        if (
            self.spec.source in ("monthly", "billing")
            and result.get(self.spec.source) is None
        ):
            attrs.pop("includes_estimates")
            attrs.update(source="eon_" + self.spec.source, source_status="unavailable")
            return attrs
        if self.spec.source == "monthly" and (source := result.get("monthly")):
            kind = "year" if self.key.startswith("year_") else "month"
            attrs.update(
                source=source["source"],
                period_start=serial(source[kind + "_start"]),
                period_end=serial(source[kind + "_end"]),
                quality_policy="provider_aggregate_not_filtered",
            )
            # The provider's balanced aggregate has no per-value quality codes.
            attrs.pop("includes_estimates")
        elif self.spec.source == "billing" and (source := result.get("billing")):
            attrs.update(
                source=source["source"],
                period_start=serial(source["period_start"]),
                period_end=serial(source["period_end"]),
                oze_client_type=source.get("oze_client_type"),
            )
            attrs.pop("includes_estimates")
        elif self.key.startswith("daily_"):
            attrs.update(
                source="hourly_csv_complete_day",
                period_date=serial(result["summary"]["daily_date"]),
            )
        else:
            attrs.update(
                source="hourly_csv",
                data_status_counts=result["quality"],
                history_start=serial(result["history_start"]),
                history_end=serial(result["history_end"]),
                optional_sources={
                    k: "available" if result.get(k) is not None else "unavailable"
                    for k in ("monthly", "billing")
                },
            )
        return attrs
