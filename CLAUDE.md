# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the application
python PlateScraper.py

# Install dependencies
pip install -r requirements.txt

# Build Windows executable
python build.py
```

There is no test suite or linter configured.

## Architecture

The entire application lives in `PlateScraper.py` (one class, `CarPlateScraper`). `build.py` is only for packaging.

### High-level flow

1. User picks a save path and clicks **Start Scraping**.
2. `start_scraping()` flips UI state and spawns a daemon thread running `scrape_data()`.
3. `scrape_data()` launches Chrome, injects a JS hook, loads the JPJ page, then iterates every area code in the dropdown.
4. For each area code, `submit_and_get_data()` solves the CAPTCHA, submits the form, and parses the JSON response.
5. Successful rows append to an in-memory list; the list is written to `.xlsx` via Pandas at checkpoints and again at the end.

### Chrome setup

`scrape_data()` configures Chrome with anti-detection flags (`--disable-blink-features=AutomationControlled`, `excludeSwitches=enable-automation`, `useAutomationExtension=False`) and uses CDP `Page.addScriptToEvaluateOnNewDocument` to:

- Hide the `navigator.webdriver` property.
- Inject `FETCH_INTERCEPT_SCRIPT` (see below) on every new document — so the hook survives `driver.refresh()` and any in-page navigation.

`goog:loggingPrefs` performance logging was previously used and has been **removed** — it slowed Chrome startup to ~3 minutes and produced stale CDP request IDs (`No resource with given identifier found`).

### CAPTCHA / response interception (`FETCH_INTERCEPT_SCRIPT`)

A monkey-patch of `window.fetch` runs in the page context. It writes captured values to two globals that Python reads via `execute_script`:

- `window.__lastCaptchaText` — set when a `generate-captcha` response is seen. The body is JSON-encoded base64 of `{"data": "<plaintext captcha>"}`. The hook decodes it and stores the plaintext.
- `window.__lastResponseRaw` — set when a `semak-no-pendaftaran-terkini` (form submit) response is seen. Stored as the raw response text.

Python helpers:

- `intercept_captcha(timeout=5)` — polls `__lastCaptchaText` every 100 ms; consumes (sets to `null`) on read so the same captcha is never reused.
- `intercept_latest_response(timeout=5)` — same pattern for `__lastResponseRaw`.
- `clear_pending_response()` — explicitly nulls `__lastResponseRaw` *before* clicking submit, so we never read a stale body from a prior attempt.

### Per-area-code loop (`scrape_data`)

After `wait_for_dropdown_loaded()` confirms the locations dropdown has populated (waits for `>1` `<option>` element under `#area_code_select`), the loop:

1. Re-fetches the `Select` (DOM may have been replaced).
2. Updates progress bar / status text / log.
3. Calls `select_by_index(idx)` to select the area code.
4. Calls `submit_and_get_data(idx, area_code)`.
5. Appends the row (or records the failure in `failed[]`).
6. Sleeps 2 s before the next state to avoid hammering the server.

Important: changing the dropdown does **not** trigger a new captcha — the captcha only loads on page load and after a submit. The hook captures the initial captcha during `driver.get(url)`, and each retry's refresh produces a fresh one.

### Submit + retry (`submit_and_get_data`)

Loops up to 3 attempts. Each attempt:

1. `get_captcha_text()` → reads `__lastCaptchaText`. If missing, refresh + retry.
2. Wait for `#captcha`, fill it.
3. `clear_pending_response()` to drop any stale body.
4. Click `#inquiry-latest-regno-submit-btn`.
5. `intercept_latest_response()` → if it returns parsed data, return it.
6. Otherwise: log "captcha mismatch", `reset_page_and_reselect`, sleep, retry.

Exceptions inside the loop are caught per-attempt so one failure doesn't abort all retries. Backoff between attempts is `1 + attempt` seconds (1 s, 2 s, 3 s).

### Page reset (`reset_page_and_reselect`)

Used to recover from captcha failures. Sequence:

1. **Sleep 2.5 s** — cooldown before refresh. Back-to-back refreshes cause the locations API to return an error and the dropdown text turns to `"gagal mendapat..."` (Malay: "failed to retrieve"). This sleep is the single most important guard against that failure mode.
2. `driver.refresh()`.
3. `wait_for_dropdown_loaded()` — the locations dropdown is async-loaded via `fetch(/api/locations)`; waiting only for the `<select>` element is not enough.
4. Re-select the same area by index.
5. Wait for `#captcha` element.

Failures are logged and re-raised so the caller's exception handler runs.

### Response parsing (`_parse_response`)

The submit response body is either raw JSON or a JSON-encoded base64 string. The parser handles both:

- If `stripped.startswith("{")` → already JSON.
- Else → `base64.b64decode(stripped).decode("utf-8")`. (`b64decode` silently skips the surrounding quote chars.)

Then by `type` field:

- `"success"` → returns `{area_code_select, regno, current_time}`.
- `"error"` → returns the same shape with `regno = "Tiada Nombor Pendaftaran Terkini"` ("no latest registration number"), so empty areas still produce a row.
- Anything else → logged as unclassified and returns `None`.

`current_time` has its `\/` escapes normalized to `/`.

### Output

`save_results(results)` writes the in-memory list to `self.save_path` as `.xlsx` via Pandas. Triggered:

- Every `CHECKPOINT_EVERY = 10` successful rows (mid-run crash safety).
- When the user stops mid-run.
- At the end of the run.

If no save path was selected, a default `carplate_data_<YYYYMMDD_HHMMSS>.xlsx` is created in the CWD.

### GUI (Flet)

Material Design widgets. The scraping thread updates UI state (`status_text`, `progress_bar`, `log_container`, button labels) and must call `self.page.update()` after each change. `log()` appends a timestamped, optionally colored `ft.Text` to the log column and auto-scrolls.

The file picker uses `page.services.append(file_picker)` and `await self.file_picker.save_file(...)` for the save dialog (Flet async API).

## Key hardcoded values

| Value | Location | Purpose |
| --- | --- | --- |
| `https://www.jpj.gov.my/semakan-nombor-pendaftaran-terkini/` | `scrape_data()` | Target URL |
| `800 × 700` | `__init__` | Window size |
| `5 s` | `intercept_captcha`, `intercept_latest_response` | Interception timeouts |
| `3` | `submit_and_get_data` | Retry limit per area code |
| `1 + attempt s` | `submit_and_get_data` | Retry backoff (1 s, 2 s, 3 s) |
| `2.5 s` | `reset_page_and_reselect` | Pre-refresh cooldown — prevents `gagal mendapat...` |
| `2 s` | `scrape_data` loop tail | Inter-state delay |
| `15 s` | `wait_for_dropdown_loaded` | Locations dropdown wait |
| `10` | `CHECKPOINT_EVERY` | Save interval (rows) |

## Known failure modes

- **`gagal mendapat...`** in the dropdown — locations API throttling from too-fast refreshes. Guarded by the 2.5 s cooldown in `reset_page_and_reselect`.
- **Captcha mismatch** — handled by the retry loop; refreshes the page to get a new captcha.
- **Stale CDP request IDs** — historical issue from the old performance-log approach; eliminated by the `window.fetch` wrapper.
- **`Could not locate element with index N`** — historical; was caused by selecting before the locations API populated. Fixed by `wait_for_dropdown_loaded()`.
