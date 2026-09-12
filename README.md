# E.ON Polska for Home Assistant

Custom integration, version 0.1.0. Reads hourly grid import/export for E.ON Polska **prosumer (OZE)** supply points. Uses the private Mój E.ON website API.

## What it does

- Discovers active OZE supply points from the authenticated account.
- Downloads hourly CSV reports once daily, in inclusive windows of at most 180 days.
- Imports historical grid import/export into Recorder as external energy statistics.
- Re-downloads the configured history window each day, so provider corrections update downstream cumulative sums without duplicating hours.
- Exposes latest hourly import/export, latest interval start and excluded-value count sensors.
- Renews the browser session every 10 minutes while loaded, persists rotated cookies and requests reauthentication if the session expires.

E.ON says reports update every two days. This is delayed historical energy, not live power. Export is not total PV production. The CSV import/export columns are used directly; monthly billing charts can differ because of hourly balancing and settlement rules.

## Install with HACS

1. Open HACS → menu → **Custom repositories**.
2. Add `https://github.com/tukies/home-assistant-eon-polska` and select **Integration**.
3. Download E.ON Polska and restart Home Assistant.
4. Add **E.ON Polska** under Settings → Devices & services, then follow the authentication steps below.

This repository is a HACS custom repository, not a default-store listing.

## Manual installation and setup

1. Copy `custom_components/eon_polska` into Home Assistant's `config/custom_components/` directory.
2. Restart Home Assistant, then open **Settings → Devices & services → Add integration → E.ON Polska**.
3. In a browser, sign in at https://eon.pl/mojeon. In Developer Tools → Network, inspect a successful `GetPHList` request. Copy its **Cookie** request-header value into the integration's password field. Use the same browser's User-Agent if different from the default.
4. Select the prosumer supply point(s), a fixed history start date and whether to include estimates. The default start is approximately one month ago. A long history requires more downloads at startup and each daily refresh.
5. In Energy settings, select the external **grid import** and **grid export** statistics for the supply point. Do not use the latest-hour sensors as accumulating energy meters.

Requires Home Assistant 2026.9 or later for the tested Recorder API. Tested version: 2026.9.2, Python 3.14. Treat this as a local custom integration, not an official E.ON integration.

## Authentication

Password-only login is not implemented. The captured browser login contains a separate token and anti-forgery token; the integration does not try to bypass that flow. Session-cookie access and renewal were verified by direct Python requests. Long-running renewal across days, server restarts, or forced sign-outs has not been proven. Home Assistant being offline may require another browser login.

The Cookie header is a credential. Home Assistant stores it in its local config-entry storage and backups. The package contains no account credentials, private account identifiers or captured household data. The client sends credentials only to fixed E.ON HTTPS endpoints and does not follow redirects. Do not publish a config-entry export containing the cookie.

A replacement session must have access to all configured supply points. The integration verifies this before accepting reauthentication. Standard electricity accounts (product type 100) are intentionally not offered: the verified hourly endpoint is for OZE accounts (type 300).

## Time and quality handling

CSV labels are interpreted as **hour-ending times in Europe/Warsaw**. `24:00` ends the final hour of the stated date. During spring DST, E.ON includes a zero-valued `02:00` placeholder with empty statuses; it is discarded. During autumn DST, E.ON appends `2A:00`, which is the second occurrence of 02:00. It is assigned to the correct UTC interval and sorted chronologically. Both conventions were exercised against live transition-day reports.

Status definitions from E.ON's report guide:

| Code | Meaning | Default import |
|---|---|---|
| 0 | Confirmed | Included |
| 1 | Uncertain | Excluded |
| 2 | Missing | Excluded |
| 3 | Forecast | Excluded |
| Other / blank | Unknown | Excluded |

**Include uncertain and forecast readings** adds codes 1 and 3. Missing or unknown values are never counted. The cumulative statistics stay flat through excluded intervals; Energy totals therefore undercount where values are excluded. The excluded-value sensor and status-count attributes disclose this. They are counts across both directions for the whole configured history window. Later provider corrections are reconciled on the next successful complete refresh.

Import/export interval sensors intentionally have no `state_class`: polling a past interval must not record that energy at today's polling time. Historical statistics use a zero baseline before the first interval so its energy is counted.

## Limits and recovery

- The history start and estimate policy are fixed at setup. When recreating an entry, keep the same start and policy, or remove the old external statistics before rebuilding history; otherwise older rows outside the new range remain in Recorder.
- The website API may change. Unexpected schemas, invalid numbers, conflicting duplicate hours and malformed DST rows are rejected.
- Missing/unknown energy is excluded rather than treated as a confirmed zero. If all values for the latest interval are excluded, its energy sensors are unknown.
- A network failure leaves the previous successful state available in memory but marks entities unavailable. A later successful refresh rebuilds history from E.ON.
- Existing Recorder history is not deleted when an entry is removed.
- The report form's current ItemId is discovered from the website rather than hardcoded.

## Development

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python homeassistant==2026.9.2 pytest pytest-asyncio ruff
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check .
```

See [VERIFICATION.md](VERIFICATION.md) for the evidence and remaining validation boundaries.

## Sources

- [E.ON report guide](https://eon.pl/-/media/Files/Instrukcje/Ulotka_do_raportu_danych_pomiarowych): hourly data, source, two-day update cadence and quality legend.
- [Home Assistant Recorder API changes](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/): `mean_type` and `unit_class` metadata.
- [Home Assistant statistics](https://data.home-assistant.io/docs/statistics/): external historical statistics.
