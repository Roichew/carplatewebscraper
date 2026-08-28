import flet as ft
import threading
import time
import base64
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
import pandas as pd
from datetime import datetime
import os
import sys
import logging
from logging.handlers import RotatingFileHandler


def get_base_dir():
    """Directory to anchor the log file to.

    When frozen by PyInstaller (--onedir) sys.executable points at the built
    exe, so logs land next to the app. In dev it's the script's folder.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logging():
    """Configure a rotating file logger.

    Writes to logs/platescraper.log next to the app. Rotates at 2 MB, keeping
    5 backups, so long-running scrapes never grow the file unbounded.
    """
    log_dir = os.path.join(get_base_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "platescraper.log")

    logger = logging.getLogger("PlateScraper")
    logger.setLevel(logging.DEBUG)

    # Guard against duplicate handlers if setup runs more than once.
    if not logger.handlers:
        file_handler = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

        # Also echo to stdout/console for dev runs.
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(stream_handler)

    logger.info("Log file initialized at %s", log_path)
    return logger

# Injected before any document loads. Wraps window.fetch so every captcha and
# every submit response is captured into window vars we can read from Python.
FETCH_INTERCEPT_SCRIPT = r"""
(function() {
  if (window.__plateScraperHook) return;
  window.__plateScraperHook = true;
  window.__lastCaptchaText = null;
  window.__lastResponseRaw = null;

  const origFetch = window.fetch;
  window.fetch = function(input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const promise = origFetch.apply(this, arguments);

    if (url.indexOf('generate-captcha') !== -1) {
      promise.then(function(res) { return res.clone().json(); })
        .then(function(data) {
          try {
            const decoded = JSON.parse(atob(data));
            window.__lastCaptchaText = decoded.data;
          } catch (e) {}
        }).catch(function() {});
    } else if (url.indexOf('semak-no-pendaftaran-terkini') !== -1) {
      promise.then(function(res) { return res.clone().text(); })
        .then(function(text) { window.__lastResponseRaw = text; })
        .catch(function() {});
    }

    return promise;
  };
})();
"""

class CarPlateScraper:
    def __init__(self, page: ft.Page):
        self.logger = setup_logging()
        self.logger.info("Application starting up")

        self.page = page
        self.page.title = "Car Plate Number Scraper"
        self.page.window_width = 800
        self.page.window_height = 700
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 30

        self.save_path = ""
        self.is_scraping = False
        self.driver = None

        # File path display
        self.path_text = ft.Text(
            "No file selected",
            size=14,
            color=ft.Colors.GREY_600,
            italic=True
        )

        # Select file button
        self.select_file_btn = ft.Button(
            "Select Save Location",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self.select_location,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.GREEN_700,
                padding=15,
            ),
        )

        # Start button
        self.start_btn = ft.Button(
            "Start Scraping",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.start_scraping,
            disabled=True,
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.BLUE_700,
                padding=20,
            ),
            width=200,
            height=50,
        )

        # Status text
        self.status_text = ft.Text(
            "Status: Ready",
            size=16,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700,
        )

        # Progress bar
        self.progress_bar = ft.ProgressBar(
            width=700,
            visible=False,
            color=ft.Colors.BLUE_700,
        )

        # Log container
        self.log_container = ft.Container(
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                spacing=5,
            ),
            width=700,
            height=300,
            border=ft.Border.all(1, ft.Colors.GREY_400),
            border_radius=10,
            padding=15,
            bgcolor=ft.Colors.GREY_100,
        )

        # File picker
        self.file_picker = ft.FilePicker()
        self.page.services.append(self.file_picker)

        self.build_ui()

    def build_ui(self):
        self.page.add(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),

                        # File selection section
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("Save Location", size=16, weight=ft.FontWeight.BOLD),
                                    ft.Row(
                                        [
                                            self.path_text,
                                            self.select_file_btn,
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                ],
                                spacing=10,
                            ),
                            padding=20,
                            border=ft.Border.all(1, ft.Colors.GREY_300),
                            border_radius=10,
                            bgcolor=ft.Colors.WHITE,
                        ),

                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),

                        # Start button
                        ft.Container(
                            content=self.start_btn,
                            alignment=ft.alignment.Alignment.CENTER,
                        ),

                        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),

                        # Status
                        ft.Container(
                            content=self.status_text,
                            alignment=ft.alignment.Alignment.CENTER,
                        ),

                        # Progress bar
                        self.progress_bar,

                        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),

                        # Log section
                        ft.Text("Activity Log", size=16, weight=ft.FontWeight.BOLD),
                        self.log_container,
                    ],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                alignment=ft.alignment.Alignment.CENTER,
            )
        )

    def log(self, message, color=None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = ft.Text(
            f"[{timestamp}] {message}",
            size=12,
            color=color or ft.Colors.BLACK87,
        )
        self.log_container.content.controls.append(log_entry)
        self.log_container.content.scroll_to(offset=-1, duration=100)
        self.page.update()

        # Mirror every UI log line to the file logger, mapping the message
        # colour to a log level so warnings/errors stand out in the file.
        if color == ft.Colors.RED_700:
            self.logger.error(message)
        elif color == ft.Colors.ORANGE_700:
            self.logger.warning(message)
        else:
            self.logger.info(message)

    async def select_location(self, e):
        default_name = self.generate_default_filename()
        path = await self.file_picker.save_file(
            dialog_title="Select save location",
            file_name=default_name,
            allowed_extensions=["xlsx"],
        )
        if path:
            if not path.lower().endswith(".xlsx"):
                path += ".xlsx"
            self.save_path = path
            filename = os.path.basename(path)
            self.path_text.value = filename
            self.path_text.color = ft.Colors.GREEN_700
            self.path_text.italic = False
            self.start_btn.disabled = False
            self.page.update()
            self.log(f"Save location set: {filename}", ft.Colors.GREEN_700)

    def get_captcha_text(self):
        captcha = self.intercept_captcha()
        if captcha:
            return captcha
        self.log("Captcha interception failed", ft.Colors.RED_700)
        return None

    # FIX #10: try/except moved inside the loop so one bad attempt doesn't abort all retries
    # FIX #8: exponential backoff between retries (0s, 1s, 2s)
    def submit_and_get_data(self, dropdown_index, area_code):
        for attempt in range(3):
            try:
                captcha_text = self.get_captcha_text()
                if not captcha_text:
                    self.log(f"Captcha not found (attempt {attempt + 1}/3)", ft.Colors.ORANGE_700)
                    self.reset_page_and_reselect(dropdown_index, area_code)
                    time.sleep(1.0 + attempt * 1.0)
                    continue

                captcha_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "captcha"))
                )
                captcha_input.clear()
                captcha_input.send_keys(captcha_text)

                # Drop any stale response so we only see the one this click produces.
                self.clear_pending_response()

                self.driver.find_element(
                    By.ID, "inquiry-latest-regno-submit-btn"
                ).click()

                data = self.intercept_latest_response()

                if data:
                    return data

                self.log(
                    f"Captcha mismatch, refreshing page (attempt {attempt + 1}/3)",
                    ft.Colors.ORANGE_700,
                )
                self.reset_page_and_reselect(dropdown_index, area_code)
                time.sleep(1.0 + attempt * 1.0)

            except Exception as e:
                self.log(f"Attempt {attempt + 1} error: {e}", ft.Colors.RED_700)
                self.logger.exception(
                    "Attempt %s failed for area '%s'", attempt + 1, area_code
                )
                print(f"Attempt {attempt + 1} error: {e}")
                try:
                    self.reset_page_and_reselect(dropdown_index, area_code)
                except Exception:
                    pass
                time.sleep(1.0 + attempt * 1.0)

        return None

    def wait_for_dropdown_loaded(self, timeout=15):
        # The dropdown options are async-loaded via fetch(/api/locations).
        # Waiting for the <select> element alone is not enough.
        WebDriverWait(self.driver, timeout).until(
            lambda d: len(d.find_element(By.ID, "area_code_select")
                          .find_elements(By.TAG_NAME, "option")) > 1
        )

    # FIX #11: wrapped in try/except so failures are reported and re-raised cleanly
    # FIX #12: replaced time.sleep(1.5) with WebDriverWait for captcha input element
    def reset_page_and_reselect(self, dropdown_index, area_code):
        self.log(
            f"Refreshing page due to captcha issue ({area_code})",
            ft.Colors.ORANGE_700,
        )
        print(f"Refreshing page due to captcha issue ({area_code})")

        try:
            # Cooldown before refresh — back-to-back refreshes cause the
            # locations API to fail and the dropdown turns to "gagal mendapat..."
            time.sleep(2.5)
            self.driver.refresh()

            self.wait_for_dropdown_loaded()

            dropdown = Select(self.driver.find_element(By.ID, "area_code_select"))
            dropdown.select_by_index(dropdown_index)

            # Wait for the captcha input to be present instead of a blind sleep
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "captcha"))
            )
        except Exception as e:
            self.log(f"Page reset failed: {e}", ft.Colors.RED_700)
            self.logger.exception("Page reset failed for area '%s'", area_code)
            print(f"Page reset failed: {e}")
            raise

    # FIX #4: proper JSON parsing with fallback; returns None on failure instead of crashing
    def decode_base64(self, response):
        try:
            decoded = base64.b64decode(response).decode("utf-8")
            try:
                parsed = json.loads(decoded)
                return parsed["data"]
            except (json.JSONDecodeError, KeyError):
                # fallback to string split for unexpected formats
                return decoded.split('"data":"')[1].split('"')[0]
        except Exception as e:
            self.log(f"Base64 decode error: {e}", ft.Colors.RED_700)
            return None

    def generate_default_filename(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"carplate_data_{ts}.xlsx"

    def ensure_save_path(self):
        if not self.save_path:
            self.save_path = os.path.join(
                os.getcwd(),
                self.generate_default_filename()
            )
        if not self.save_path.lower().endswith(".xlsx"):
            self.save_path += ".xlsx"

    # FIX #15: extracted into a helper so incremental saves and final save use the same path
    def save_results(self, results):
        if not results:
            return
        self.ensure_save_path()
        df = pd.DataFrame(results)
        df.to_excel(self.save_path, index=False)
        self.logger.info("Saved %d rows to %s", len(results), self.save_path)

    def scrape_data(self):
        try:
            url = "https://www.jpj.gov.my/semakan-nombor-pendaftaran-terkini/"
            if not self.save_path:
                self.save_path = os.path.join(
                    os.getcwd(),
                    self.generate_default_filename()
                )
                self.log(f"No save path selected, using default: {self.save_path}", ft.Colors.ORANGE_700)

            self.log("Initializing Chrome driver...", ft.Colors.BLUE_700)
            chrome_options = Options()
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)

            self.driver = webdriver.Chrome(options=chrome_options)

            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    """
                }
            )
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": FETCH_INTERCEPT_SCRIPT},
            )
            self.log(f"Navigating to {url}...", ft.Colors.BLUE_700)
            self.driver.get(url)

            self.wait_for_dropdown_loaded()

            dropdown = Select(self.driver.find_element(By.ID, "area_code_select"))
            total_options = len(dropdown.options) - 1  # skip placeholder

            results = []
            failed = []
            CHECKPOINT_EVERY = 10

            for idx in range(1, total_options + 1):
                if not self.is_scraping:
                    self.log("Scraping stopped by user", ft.Colors.ORANGE_700)
                    # FIX #17: save whatever was collected before the user stopped
                    if results:
                        self.save_results(results)
                        self.log(f"Partial results saved: {len(results)} records", ft.Colors.ORANGE_700)
                    break

                dropdown = Select(self.driver.find_element(By.ID, "area_code_select"))
                option = dropdown.options[idx]
                area_code = option.text

                progress = idx / total_options
                self.progress_bar.value = progress
                self.status_text.value = f"Status: Processing {area_code} ({idx}/{total_options})"
                self.page.update()

                self.log(f"Processing {idx}/{total_options}: {area_code}", ft.Colors.GREEN_700)

                dropdown.select_by_index(idx)

                data = self.submit_and_get_data(idx, area_code)

                if data:
                    if data.get("area_code_select") == "":
                        results.append({
                            "Area Code": area_code,
                            "Reg No": data["regno"],
                            "Date": data["current_time"],
                        })
                    else:
                        results.append({
                            "Area Code": data["area_code_select"],
                            "Reg No": data["regno"],
                            "Date": data["current_time"],
                        })
                    self.log(f"✓ Got data: {data.get('regno')}", ft.Colors.GREEN_700)
                    print(f"✓ Got data: {data.get('regno')}")

                    # FIX #15: checkpoint save every N records so a mid-run crash loses minimal data
                    if len(results) % CHECKPOINT_EVERY == 0:
                        self.save_results(results)
                        self.log(f"Checkpoint: {len(results)} records saved", ft.Colors.BLUE_700)
                else:
                    # FIX #9: track all failed area codes for the final summary
                    failed.append(area_code)
                    self.log(f"✗ Failed to get data for {area_code}", ft.Colors.RED_700)

                # Slight pause between states to avoid hammering the server
                time.sleep(2)

            if results:
                self.save_results(results)
                self.log(f"✓ Successfully saved {len(results)} records!", ft.Colors.GREEN_700)
                summary = f"Scraping completed!\n{len(results)} records saved to:\n{self.save_path}"
                if failed:
                    self.log(f"Failed area codes ({len(failed)}): {', '.join(failed)}", ft.Colors.RED_700)
                    summary += f"\n\nFailed ({len(failed)}): {', '.join(failed)}"
                self.show_success(summary)
            else:
                self.log("No data collected", ft.Colors.ORANGE_700)
                self.show_warning("No data was collected")

        except Exception as e:
            self.log(f"ERROR: {str(e)}", ft.Colors.RED_700)
            self.logger.exception("Fatal error during scraping")
            self.show_error(f"An error occurred: {str(e)}")

        finally:
            self.logger.info("Scraping run finished; cleaning up driver")
            if self.driver:
                self.driver.quit()
            self.is_scraping = False
            self.start_btn.disabled = False
            self.start_btn.text = "Start Scraping"
            self.start_btn.icon = ft.Icons.PLAY_ARROW
            self.progress_bar.visible = False
            self.status_text.value = "Status: Completed"
            self.status_text.color = ft.Colors.GREEN_700
            self.page.update()

    # Reads window.__lastCaptchaText set by FETCH_INTERCEPT_SCRIPT.
    # The JS hook is auto-reinjected on every navigation, so this also
    # works after driver.refresh().
    def intercept_captcha(self, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            try:
                captcha = self.driver.execute_script(
                    "return window.__lastCaptchaText;"
                )
            except Exception as e:
                self.log(f"Captcha read failed: {e}", ft.Colors.RED_700)
                return None
            if captcha:
                # Consume so we don't reuse the same captcha twice.
                self.driver.execute_script("window.__lastCaptchaText = null;")
                return captcha
            time.sleep(0.1)
        return None

    def clear_pending_response(self):
        try:
            self.driver.execute_script("window.__lastResponseRaw = null;")
        except Exception:
            pass

    def intercept_latest_response(self, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            try:
                raw = self.driver.execute_script(
                    "return window.__lastResponseRaw;"
                )
            except Exception as e:
                self.log(f"Response read failed: {e}", ft.Colors.RED_700)
                return None
            if raw:
                self.driver.execute_script("window.__lastResponseRaw = null;")
                return self._parse_response(raw)
            time.sleep(0.1)
        return None

    def _parse_response(self, raw):
        try:
            stripped = raw.strip()
            if stripped.startswith("{"):
                decoded = stripped
            else:
                # Body is a JSON-encoded base64 string like "eyJ0...".
                # base64.b64decode silently skips non-alphabet chars (the quotes).
                decoded = base64.b64decode(stripped).decode("utf-8")

            parsed = json.loads(decoded)
        except Exception as e:
            self.log(f"Response parse error: {e}", ft.Colors.RED_700)
            return None

        def normalize_time(value):
            return value.replace("\\/", "/") if value else ""

        response_type = parsed.get("type")
        payload = parsed.get("data") or {}

        if response_type == "error":
            return {
                "area_code_select": "",
                "regno": "Tiada Nombor Pendaftaran Terkini",
                "current_time": normalize_time(payload.get("current_time", "")),
            }

        if response_type == "success":
            return {
                "area_code_select": payload.get("area_code_select", ""),
                "regno": payload.get("regno", ""),
                "current_time": normalize_time(payload.get("current_time", "")),
            }

        self.log(
            f"Unclassified response type '{response_type}': {decoded[:100]}",
            ft.Colors.ORANGE_700,
        )
        return None

    def start_scraping(self, e):
        if not self.save_path:
            self.show_error("Please select save location first")
            return

        self.is_scraping = True
        self.start_btn.disabled = True
        self.start_btn.text = "Scraping..."
        self.start_btn.icon = ft.Icons.HOURGLASS_EMPTY
        self.progress_bar.visible = True
        self.progress_bar.value = 0
        self.status_text.value = "Status: Initializing..."
        self.status_text.color = ft.Colors.BLUE_700
        self.log_container.content.controls.clear()
        self.page.update()

        self.log("Starting scraping process...", ft.Colors.BLUE_700)

        thread = threading.Thread(target=self.scrape_data, daemon=True)
        thread.start()

    def show_error(self, message):
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Error", color=ft.Colors.RED_700),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close_dlg)],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def show_success(self, message):
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Success", color=ft.Colors.GREEN_700),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close_dlg)],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def show_warning(self, message):
        def close_dlg(e):
            dlg.open = False
            self.page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Warning", color=ft.Colors.ORANGE_700),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close_dlg)],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()


def main(page: ft.Page):
    CarPlateScraper(page)

if __name__ == "__main__":
    # Ensure the log dir/handlers exist and capture any unhandled exception
    # (including ones raised before the UI is built) with a full traceback.
    _logger = setup_logging()

    def _log_uncaught(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        _logger.critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _log_uncaught

    try:
        ft.run(main)
    except Exception:
        _logger.exception("Application terminated with an unhandled exception")
        raise
