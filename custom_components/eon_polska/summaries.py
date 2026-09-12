"""Energy summaries with explicit periods and missing-data semantics."""

import re
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from .parser import WARSAW


class SummaryError(ValueError):
    """Optional API data cannot safely be interpreted."""


def amount(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise SummaryError("Invalid energy amount")
    try:
        parsed = Decimal(
            str(value).strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        )
    except InvalidOperation as err:
        raise SummaryError("Invalid energy amount") from err
    if not parsed.is_finite() or parsed < 0:
        raise SummaryError("Invalid energy amount")
    return float(parsed)


def period(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}", value
    ):
        raise SummaryError("Missing or invalid reporting period")
    first, last = [
        datetime.strptime(v.strip(), "%d.%m.%Y").date() for v in value.split("-")
    ]
    if last < first:
        raise SummaryError("Invalid reporting period order")
    return first, last


def check_result(data):
    if not isinstance(data, dict) or data.get("Faulted"):
        raise SummaryError("E.ON did not return summary data")
    status = data.get("Status")
    if isinstance(status, dict) and status.get("ReturnCode", 0) != 0:
        raise SummaryError("E.ON did not return summary data")
    if not isinstance(data.get("Results"), list):
        raise SummaryError("Invalid summary schema")


def monthly_summary(data):
    check_result(data)
    if data.get("Dictionary", {}).get("Unit", "kWh") != "kWh":
        raise SummaryError("Unexpected energy unit")
    candidates = []
    for year in data["Results"]:
        for month in year.get("Data", []):
            start, end = period(month.get("Range"))
            if (
                start.month != end.month
                or start.year != end.year
                or int(month["Year"]) != start.year
                or int(month["MonthNumber"]) != start.month
            ):
                raise SummaryError("Inconsistent monthly reporting period")
            candidates.append((end, start, month, year.get("Summary", {})))
    if not candidates:
        raise SummaryError("No monthly data available")
    end, start, month, annual = max(candidates, key=lambda c: c[0])
    if annual and int(annual.get("Year", start.year)) != start.year:
        raise SummaryError("Inconsistent annual reporting period")
    return {
        "month_import": amount(month.get("P")),
        "month_export": amount(month.get("O")),
        "year_import": amount(annual.get("P")),
        "year_export": amount(annual.get("O")),
        "month_start": start,
        "month_end": end,
        "year_start": start.replace(month=1, day=1),
        "year_end": end,
        "source": "eon_monthly_balanced",
    }


BILLING_FIELDS = {
    "billing_import": "EnergyConsumed",
    "billing_export": "EnergyProvided",
    "oze_recovered": "EnergyRecovered",
    "oze_previous_surplus": "PreviousPeriodsEnergySurplus",
    "oze_settled_surplus": "CurrentPeriodEnergySurplus",
    "oze_stored_surplus": "EnergyStoredSurplus",
    "oze_expired_surplus": "OverdueEnergySurplus",
    "oze_factor": "OzeFactor",
}


def billing_summary(data):
    check_result(data)
    chart = data.get("ChartsData", {})
    if chart.get("Unit", "kWh") != "kWh":
        raise SummaryError("Unexpected billing unit")
    periods = {}
    for row in chart.get("Results", []):
        key = str(row.get("X"))
        dates = period(row.get("TooltipDescription"))
        if key in periods and periods[key] != dates:
            raise SummaryError("Conflicting billing dates")
        periods[key] = dates
    candidates = [
        (periods[str(row["Id"])], row)
        for row in data["Results"]
        if str(row.get("Id")) in periods
    ]
    if not candidates:
        raise SummaryError("No dated billing periods available")
    (start, end), row = max(candidates, key=lambda item: item[0][1])
    result = {key: amount(row.get(field)) for key, field in BILLING_FIELDS.items()}
    if result["oze_factor"] is not None and result["oze_factor"] > 1:
        raise SummaryError("Invalid OZE factor")
    # EnergyStoredDueDate is deliberately not exposed: it repeats across historical rows.
    result.update(
        period_start=start,
        period_end=end,
        billing_period_end=end,
        source="eon_billing_period",
        oze_client_type=data.get("OzeClientType"),
    )
    return result


def hourly_summary(readings, include_estimates=False):
    days = defaultdict(list)
    missing = forecast = uncertain = unknown = eligible = excluded = 0
    latest = None
    for reading in readings:
        days[reading.start.astimezone(WARSAW).date()].append(reading)
        statuses = (reading.import_status, reading.export_status)
        values = (reading.imported, reading.exported)
        accepted = [reading.value(d, include_estimates) for d in ("import", "export")]
        excluded += sum(value is None for value in accepted)
        eligible += all(value is not None for value in accepted)
        missing += any(s == 2 or v is None for s, v in zip(statuses, values))
        forecast += 3 in statuses
        uncertain += 1 in statuses
        unknown += any(s not in (0, 1, 2, 3) for s in statuses)
        if any(s in (0, 1, 3) and v is not None for s, v in zip(statuses, values)):
            if latest is None or reading.start > latest.start:
                latest = reading
    result = {
        "import": latest.value("import", include_estimates) if latest else None,
        "export": latest.value("export", include_estimates) if latest else None,
        "reported_at": latest.start if latest else None,
        "excluded_values": excluded,
        "missing_hours": missing,
        "forecast_hours": forecast,
        "uncertain_hours": uncertain,
        "unknown_hours": unknown,
        "coverage": round(100 * eligible / len(readings), 2) if readings else None,
        "daily_import": None,
        "daily_export": None,
        "daily_date": None,
    }
    for day, rows in sorted(days.items(), reverse=True):
        start = datetime.combine(day, time(), WARSAW).astimezone(UTC)
        end = datetime.combine(day + timedelta(days=1), time(), WARSAW).astimezone(UTC)
        expected = int((end - start).total_seconds() / 3600)
        if len(rows) != expected or len({r.start for r in rows}) != expected:
            continue
        if any(
            r.value(d, include_estimates) is None
            for r in rows
            for d in ("import", "export")
        ):
            continue
        result.update(
            daily_date=day,
            daily_import=sum(
                (r.value("import", include_estimates) for r in rows), Decimal(0)
            ),
            daily_export=sum(
                (r.value("export", include_estimates) for r in rows), Decimal(0)
            ),
        )
        break
    return result
