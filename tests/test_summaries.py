from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from custom_components.eon_polska.parser import WARSAW, Reading
from custom_components.eon_polska.summaries import (
    SummaryError,
    amount,
    billing_summary,
    hourly_summary,
    monthly_summary,
)


def day_rows(day, missing=False, forecast=False):
    start = datetime.combine(day, time(), WARSAW).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(), WARSAW).astimezone(UTC)
    result = []
    while start < end:
        result.append(
            Reading(
                start,
                Decimal("1.25"),
                None if missing else Decimal("0.5"),
                3 if forecast else 0,
                2 if missing else 0,
            )
        )
        start += timedelta(hours=1)
    return result


@pytest.mark.parametrize(
    "day,hours",
    [(date(2026, 3, 29), 23), (date(2025, 10, 26), 25), (date(2024, 1, 1), 24)],
)
def test_complete_days_respect_dst(day, hours):
    summary = hourly_summary(day_rows(day))
    assert summary["daily_date"] == day
    assert summary["daily_import"] == Decimal("1.25") * hours
    assert summary["daily_export"] == Decimal("0.5") * hours
    assert summary["coverage"] == 100


def test_partial_latest_day_falls_back_to_complete_day():
    rows = day_rows(date(2024, 1, 1)) + day_rows(date(2024, 1, 2))[:-1]
    assert hourly_summary(rows)["daily_date"] == date(2024, 1, 1)


def test_forecast_policy_and_missing_hours_are_separate():
    rows = day_rows(date(2024, 1, 1), forecast=True)
    assert hourly_summary(rows)["daily_date"] is None
    assert hourly_summary(rows)["forecast_hours"] == 24
    assert hourly_summary(rows)["missing_hours"] == 0
    assert hourly_summary(rows, True)["daily_date"] == date(2024, 1, 1)
    assert (
        hourly_summary(day_rows(date(2024, 1, 1), missing=True), True)["daily_date"]
        is None
    )


def test_freshness_does_not_use_padded_missing_tail():
    rows = day_rows(date(2024, 1, 1))
    last = rows[-1].start
    rows.append(Reading(last + timedelta(hours=1), None, None, 2, 2))
    result = hourly_summary(rows)
    assert result["reported_at"] == last
    assert result["missing_hours"] == 1
    assert result["excluded_values"] == 2


def test_unknown_is_not_confirmed_zero():
    rows = day_rows(date(2024, 1, 1))
    rows[0] = Reading(rows[0].start, Decimal(0), Decimal(0), 9, None)
    result = hourly_summary(rows)
    assert result["unknown_hours"] == 1
    assert result["daily_import"] is None


def monthly_payload():
    return {
        "Faulted": False,
        "Results": [
            {
                "Data": [
                    {
                        "Year": 2026,
                        "MonthNumber": 9,
                        "Range": "01.09.2026 - 10.09.2026",
                        "P": "10,25",
                        "O": "5,50",
                    }
                ],
                "Summary": {"Year": 2026, "P": "100,25", "O": "50,50"},
            }
        ],
        "Dictionary": {"Unit": "kWh"},
        "Status": {"ReturnCode": 0},
    }


def test_provider_monthly_totals_are_not_recomputed_from_partial_history():
    result = monthly_summary(monthly_payload())
    assert result["month_import"] == 10.25
    assert result["year_import"] == 100.25
    assert result["month_end"] == date(2026, 9, 10)
    assert result["source"] == "eon_monthly_balanced"


def test_missing_annual_fields_are_unknown():
    payload = monthly_payload()
    payload["Results"][0]["Summary"] = {}
    assert monthly_summary(payload)["year_import"] is None


def test_monthly_fault_and_period_mismatch_rejected():
    data = monthly_payload()
    data["Faulted"] = True
    with pytest.raises(SummaryError):
        monthly_summary(data)
    data = monthly_payload()
    data["Results"][0]["Data"][0]["Year"] = 2025
    with pytest.raises(SummaryError):
        monthly_summary(data)


def billing_payload():
    return {
        "Faulted": False,
        "OzeClientType": "Metering",
        "Results": [
            {
                "Id": 1,
                "EnergyConsumed": 20,
                "EnergyProvided": 10,
                "EnergyRecovered": 8,
                "EnergyStoredSurplus": 0,
                "OverdueEnergySurplus": 0,
                "OzeFactor": "0,8",
                "EnergyStoredDueDate": "2099 I",
            },
            {"Id": 0, "EnergyConsumed": 50, "EnergyProvided": 30},
        ],
        "ChartsData": {
            "Unit": "kWh",
            "Results": [
                {"X": 0, "TooltipDescription": "01.01.2024 - 30.06.2024"},
                {"X": 1, "TooltipDescription": "01.07.2024 - 31.12.2024"},
            ],
        },
    }


def test_latest_billing_uses_dates_and_preserves_zero():
    result = billing_summary(billing_payload())
    assert result["billing_import"] == 20
    assert result["oze_stored_surplus"] == 0
    assert result["oze_factor"] == 0.8
    assert result["period_end"] == date(2024, 12, 31)
    assert result["oze_previous_surplus"] is None
    assert not any("due" in k for k in result)


def test_undated_or_conflicting_billing_is_rejected():
    payload = billing_payload()
    payload["ChartsData"]["Results"] = []
    with pytest.raises(SummaryError):
        billing_summary(payload)
    payload = billing_payload()
    payload["ChartsData"]["Results"].append(
        {"X": 1, "TooltipDescription": "01.01.2025 - 30.06.2025"}
    )
    with pytest.raises(SummaryError):
        billing_summary(payload)


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", True])
def test_invalid_optional_values_are_not_zero(bad):
    with pytest.raises(SummaryError):
        amount(bad)


def test_duplicate_interval_is_not_a_complete_day():
    rows = day_rows(date(2024, 1, 1))
    assert hourly_summary(rows + rows[:1])["daily_date"] is None
