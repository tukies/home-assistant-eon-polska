from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from custom_components.eon_polska.parser import (
    HEADER,
    ReportError,
    date_windows,
    interval_start,
    parse_report,
    quality,
    statistics,
)


def report(*rows):
    return ",".join(HEADER) + "\n" + "\n".join(rows)


def row(day="01.08.2026", hour="01:00", imp="1,250", exp="0,500", si="0", se="0"):
    return f'{day},{hour},"{imp}",{si},"{exp}",{se},"0,750",0'


def test_localized_csv_and_baseline():
    data = parse_report("\ufeff" + report(row()))
    assert data[0].imported == Decimal("1.250")
    assert data[0].start == datetime(2026, 7, 31, 22, tzinfo=UTC)
    assert [s["sum"] for s in statistics(data, "import")] == [0, 1.25]


def test_midnight_belongs_to_previous_day():
    assert interval_start(date(2026, 8, 1), "24:00") == datetime(
        2026, 8, 1, 21, tzinfo=UTC
    )


def test_spring_empty_placeholder_and_continuity():
    data = parse_report(
        report(
            row("29.03.2026", "01:00"),
            row("29.03.2026", "02:00", "0,000", "0,000", "", ""),
            row("29.03.2026", "03:00"),
        )
    )
    assert len(data) == 2
    assert data[1].start - data[0].start == timedelta(hours=1)


def test_autumn_extra_hour_sorted_correctly():
    data = parse_report(
        report(
            row("26.10.2025", "01:00"),
            row("26.10.2025", "02:00"),
            row("26.10.2025", "03:00"),
            row("26.10.2025", "2A:00"),
        )
    )
    assert len(data) == 4
    assert all(b.start - a.start == timedelta(hours=1) for a, b in zip(data, data[1:]))


@pytest.mark.parametrize(
    "bad",
    [
        row(imp="NaN"),
        row(imp="Infinity"),
        row(imp="-1"),
        row(hour="00:00"),
        row(hour="2A:00"),
        row("29.03.2026", "02:00"),
    ],
)
def test_invalid_values_and_times_rejected(bad):
    with pytest.raises(ReportError):
        parse_report(report(bad))


def test_statuses_never_turn_missing_into_energy():
    data = parse_report(
        report(
            row(hour="01:00", si="0"),
            row(hour="02:00", si="1"),
            row(hour="03:00", si="2"),
            row(hour="04:00", si="3"),
            row(hour="05:00", si="9"),
        )
    )
    assert statistics(data, "import")[-1]["sum"] == 1.25
    assert statistics(data, "import", True)[-1]["sum"] == 3.75
    assert quality(data)["unknown"] == 1


def test_correction_recomputes_downstream_sums_idempotently():
    old = parse_report(report(row(), row(hour="02:00")))
    new = parse_report(report(row(imp="2,000"), row(hour="02:00")))
    assert statistics(old, "import")[-1]["sum"] == 2.5
    assert statistics(new, "import")[-1]["sum"] == 3.25
    assert statistics(new, "import") == statistics(new, "import")


def test_duplicate_conflicts_and_schema():
    assert len(parse_report(report(row(), row()))) == 1
    with pytest.raises(ReportError):
        parse_report(report(row(), row(imp="2")))
    with pytest.raises(ReportError):
        parse_report("<html>login</html>")


def test_windows_inclusive_no_overlap():
    windows = list(date_windows(date(2024, 1, 1), date(2025, 1, 1)))
    assert len(windows) == 3
    assert all((b - a).days < 180 for a, b in windows)
    assert all(
        left[1] + timedelta(days=1) == right[0]
        for left, right in zip(windows, windows[1:])
    )


def test_omitted_hours_keep_origin_and_replace_old_energy():
    from custom_components.eon_polska.parser import complete_history

    rows = parse_report(report(row(hour="02:00")))
    complete = complete_history(rows, date(2026, 8, 1), date(2026, 8, 1))
    assert len(complete) == 24
    assert complete[0].import_status == 2
    assert statistics(complete, "import")[0]["start"] == datetime(
        2026, 7, 31, 21, tzinfo=UTC
    )
    assert statistics(complete, "import")[-1]["sum"] == 1.25
