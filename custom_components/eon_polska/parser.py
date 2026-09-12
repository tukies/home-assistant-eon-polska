"""Strict E.ON hourly report parsing, independent of Home Assistant."""

import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
STATUS_NAMES = {0: "confirmed", 1: "uncertain", 2: "missing", 3: "forecast"}
HEADER = [
    "Dzień odczytu",
    "Godzina odczytu",
    "Energia pobrana",
    "status danych",
    "Energia wprowadzona",
    "status danych",
    "Bilans energii",
    "status danych",
]


class ReportError(ValueError):
    """The response cannot safely be interpreted as an hourly report."""


@dataclass(frozen=True)
class Reading:
    start: datetime
    imported: Decimal | None
    exported: Decimal | None
    import_status: int | None
    export_status: int | None

    def value(self, direction, estimates=False):
        status = self.import_status if direction == "import" else self.export_status
        value = self.imported if direction == "import" else self.exported
        return value if status in ({0, 1, 3} if estimates else {0}) else None


def number(raw):
    if not raw.strip():
        return None
    try:
        value = Decimal(
            raw.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
        )
    except InvalidOperation as err:
        raise ReportError("Invalid energy value") from err
    if not value.is_finite() or value < 0:
        raise ReportError("Import/export must be finite and nonnegative")
    return value


def status(raw):
    if not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError as err:
        raise ReportError("Invalid status code") from err


def interval_start(day, label):
    """E.ON hour-ending labels; 2A is the second 02:00 on autumn DST day."""
    match = re.fullmatch(r"(\d{1,2})(A)?:00", label.strip(), re.IGNORECASE)
    if not match:
        raise ReportError("Unexpected hour label")
    hour, repeated = int(match[1]), bool(match[2])
    if not 1 <= hour <= 24 or (repeated and hour != 2):
        raise ReportError("Unexpected hour label")
    end = datetime.combine(day, time()) + timedelta(hours=hour)
    local = end.replace(tzinfo=WARSAW, fold=int(repeated))
    utc = local.astimezone(UTC)
    if utc.astimezone(WARSAW).replace(tzinfo=None) != end:
        return None  # Empty placeholder for spring's nonexistent 02:00.
    if repeated and end.replace(tzinfo=WARSAW, fold=0).utcoffset() == local.utcoffset():
        raise ReportError("Repeated hour outside DST transition")
    return utc - timedelta(hours=1)


def parse_report(text):
    rows = csv.reader(StringIO(text.lstrip("\ufeff")))
    if next(rows, [])[:8] != HEADER:
        raise ReportError("Expected E.ON CSV header; got another response")
    result = {}
    for row in rows:
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) < 8:
            raise ReportError("Truncated CSV row")
        try:
            day = datetime.strptime(row[0], "%d.%m.%Y").date()
            imported, exported = number(row[2]), number(row[4])
            si, se = status(row[3]), status(row[5])
            start = interval_start(day, row[1])
        except ValueError as err:
            raise ReportError(str(err)) from err
        if start is None:
            if (
                imported not in (None, Decimal(0))
                or exported not in (None, Decimal(0))
                or si is not None
                or se is not None
            ):
                raise ReportError("Nonempty nonexistent DST hour")
            continue
        reading = Reading(start, imported, exported, si, se)
        if start in result and result[start] != reading:
            raise ReportError("Conflicting duplicate interval")
        result[start] = reading
    if not result:
        raise ReportError("No hourly readings returned")
    return sorted(result.values(), key=lambda r: r.start)


def date_windows(start, end):
    """Inclusive, nonoverlapping windows, at most 180 calendar days."""
    while start <= end:
        stop = min(end, start + timedelta(days=179))
        yield start, stop
        start = stop + timedelta(days=1)


def complete_history(readings, start, end):
    """Keep the statistics origin stable and explicitly mark omitted hours missing."""
    indexed = {reading.start: reading for reading in readings}
    first = datetime.combine(start, time(), WARSAW).astimezone(UTC)
    stop = datetime.combine(end + timedelta(days=1), time(), WARSAW).astimezone(UTC)
    result = []
    while first < stop:
        result.append(indexed.get(first, Reading(first, None, None, 2, 2)))
        first += timedelta(hours=1)
    return result


def statistics(readings, direction, estimates=False):
    """Deterministic sums from a fixed history origin, including a zero baseline."""
    if not readings:
        return []
    total = Decimal(0)
    result = [{"start": readings[0].start - timedelta(hours=1), "sum": 0.0}]
    for reading in readings:
        value = reading.value(direction, estimates)
        # Keep sum flat across excluded hours; do not classify them as measured zero.
        # Quality diagnostics separately count excluded intervals.
        if value is not None:
            total += value
        result.append({"start": reading.start, "sum": float(total)})
    return result


def quality(readings):
    return dict(
        Counter(
            STATUS_NAMES.get(s, "unknown")
            for r in readings
            for s in (r.import_status, r.export_status)
        )
    )
