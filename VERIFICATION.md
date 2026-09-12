# Verification — 12 September 2026

## Passed

- **24 automated tests** on Home Assistant 2026.9.2 / Python 3.14.7, including actual Recorder with temporary SQLite storage.
- Ruff lint passed; source formatted.
- Direct HTTPS requests using the integration client successfully discovered the accessible OZE point and fetched a fresh 48-hour CSV.
- Session renewal returned application status 200. A subsequent account request remained authenticated.
- A complete multi-day report parsed into continuous hourly intervals with confirmed and forecast quality statuses.
- Live spring DST report (29 March 2026) parsed into **23** continuous UTC intervals; zero-valued 02:00 row with empty statuses was discarded.
- Live autumn DST report (26 October 2025) parsed into **25** continuous UTC intervals; appended `2A:00` was placed between the corresponding repeated-hour intervals.
- Real Recorder accepted **769 rows** (768 hours and a baseline), repeated import did not duplicate rows, and a historical correction changed downstream sums. The automated test uses synthetic data and an explicit Recorder queue barrier to avoid racing an in-flight database write.
- A temporary local Home Assistant instance completed the actual config flow, fetched live reports, loaded **four sensors**, imported **two external energy series / 1,970 rows**, and unloaded with its HTTP session closed.

## Behavior guarded by tests

Polish decimal formatting, midnight, DST, malformed headers, nonfinite/negative values, conflicting duplicates, status-based exclusions, historical revisions, omitted-hour handling, nonoverlapping 180-day windows, expired-session redirects, anonymous HTTP-200 responses, cookie rotation and sanitized errors.

## Boundaries

- Testing did not modify a production Home Assistant installation. Runtime tests used temporary local configuration and databases, subsequently deleted.
- No browser UI walkthrough of the Energy dashboard was performed. Recorder imports, entity creation and config-flow calls were tested directly.
- Automatic password login is not implemented. Browser login includes a separate token and an anti-forgery token. The package accepts an authenticated session and provides renewal/reauthentication.
- Renewal across days, prolonged downtime or server-side forced expiration remains unverified. The ten-minute schedule is implemented; live renewal requests were tested directly.
- Live data access was tested for one OZE point. Ordinary electricity accounts were discovered earlier, but the OZE report endpoint has not been established for them; they are excluded from setup.
- The public report guide establishes status meanings and two-day cadence. Timestamp mapping uses the observed hour-ending labels and verified DST-transition structures; no separate E.ON timestamp specification was found.
- Home Assistant and its dependencies emitted six deprecation/advisory warnings during tests. The tests passed.

## Sources

- [E.ON measurement-report guide](https://eon.pl/-/media/Files/Instrukcje/Ulotka_do_raportu_danych_pomiarowych)
- Authenticated HTTP Toolkit captures and fresh direct requests to `GetPHList`, `resetauthorizationcookie`, `Historia-zuzycia`, and `OzeReport/GenerateOzeReport`.
- [Recorder metadata API changes](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/)

No cookies, credentials, personal account identifiers or actual household CSV records are included in this package.
