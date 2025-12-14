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

class CarPlateScraper:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Car Plate Number Scraper"
        self.page.window_width = 800
        self.page.window_height = 700
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 30
        
        self.save_path = ""
        self.is_scraping = False
        self.driver = None
        
        # URL input
        # self.url_input = ft.TextField(
        #     label="Website URL",
        #     hint_text="Enter the website URL",
        #     width=700,
        #     prefix_icon=ft.Icons.LINK,
        # )
        
        # File path display
        self.path_text = ft.Text(
            "No file selected",
            size=14,
            color=ft.Colors.GREY_600,
            italic=True
        )
        
        # Select file button
        self.select_file_btn = ft.ElevatedButton(
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
        self.start_btn = ft.ElevatedButton(
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
            border=ft.border.all(1, ft.Colors.GREY_400),
            border_radius=10,
            padding=15,
            bgcolor=ft.Colors.GREY_100,
        )
        
        # File picker
        self.file_picker = ft.FilePicker(on_result=self.file_picker_result)
        self.page.overlay.append(self.file_picker)
        
        self.build_ui()
    
    def build_ui(self):
        """Build the UI layout"""
        self.page.add(
            ft.Container(
                content=ft.Column(
                    [
                        # Header
                        # ft.Container(
                        #     content=ft.Row(
                        #         [
                        #             ft.Icon(ft.Icons.DIRECTIONS_CAR, size=40, color=ft.Colors.BLUE_700),
                        #             ft.Text(
                        #                 "Car Plate Number Scraper",
                        #                 size=28,
                        #                 weight=ft.FontWeight.BOLD,
                        #                 color=ft.Colors.BLUE_700,
                        #             ),
                        #         ],
                        #         alignment=ft.MainAxisAlignment.CENTER,
                        #     ),
                        #     margin=ft.margin.only(bottom=30),
                        # ),
                        
                        # URL Input
                        # self.url_input,
                        
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
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=10,
                            bgcolor=ft.Colors.WHITE,
                        ),
                        
                        ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                        
                        # Start button
                        ft.Container(
                            content=self.start_btn,
                            alignment=ft.alignment.center,
                        ),
                        
                        ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                        
                        # Status
                        ft.Container(
                            content=self.status_text,
                            alignment=ft.alignment.center,
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
                alignment=ft.alignment.center,
            )
        )
    
    def log(self, message, color=None):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = ft.Text(
            f"[{timestamp}] {message}",
            size=12,
            color=color or ft.Colors.BLACK87,
        )
        self.log_container.content.controls.append(log_entry)
        self.log_container.content.scroll_to(offset=-1, duration=100)
        self.page.update()
    
    def select_location(self, e):
        """Open file picker"""
        default_name = self.generate_default_filename()
        self.file_picker.save_file(
            dialog_title="Select save location",
            file_name=default_name,
            allowed_extensions=["xlsx"],
        )
    
    def file_picker_result(self, e: ft.FilePickerResultEvent):
        """Handle file picker result"""
        if e.path:
            self.save_path = e.path
            filename = e.path.split('\\')[-1] if '\\' in e.path else e.path.split('/')[-1]
            self.path_text.value = filename
            self.path_text.color = ft.Colors.GREEN_700
            self.path_text.italic = False
            self.start_btn.disabled = False
            self.page.update()
            self.log(f"Save location set: {filename}", ft.Colors.GREEN_700)
    
    def get_captcha_text(self):
        captcha = self.intercept_captcha()
        if captcha:
            # self.log(f"Captcha intercepted: {captcha}")
            return captcha
        self.log("Captcha interception failed", ft.Colors.RED_700)
        return None
    
    def submit_and_get_data(self, dropdown_index, area_code):
        try:
            for attempt in range(3):
                captcha_text = self.get_captcha_text()
                if not captcha_text:
                    self.log("Captcha not found, retrying...", ft.Colors.ORANGE_700)
                    self.reset_page_and_reselect(dropdown_index, area_code)
                    continue

                decoded = self.decode_base64(captcha_text)
                # self.log(f"Using captcha: {decoded}")

                captcha_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "captcha"))
                )
                captcha_input.clear()
                captcha_input.send_keys(decoded)

                time.sleep(0.5)

                self.driver.find_element(
                    By.ID, "inquiry-latest-regno-submit-btn"
                ).click()

                data = self.intercept_latest_response()

                if data:
                    return data

                # 🔁 Captcha mismatch → full reset
                self.log(
                    f"Captcha mismatch, refreshing page (retry {attempt + 1}/3)",
                    ft.Colors.ORANGE_700,
                )
                self.reset_page_and_reselect(dropdown_index, area_code)
            
            return None

        except Exception as e:
            print(f"Submit error: {e}")
            self.log(f"Submit error: {e}", ft.Colors.RED_700)
            return None
    
    def reset_page_and_reselect(self, dropdown_index, area_code):
        self.log(
            f"Refreshing page due to captcha issue ({area_code})",
            ft.Colors.ORANGE_700,
        )
        print(f"Refreshing page due to captcha issue ({area_code})")

        self.driver.refresh()

        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "area_code_select"))
        )

        dropdown = Select(self.driver.find_element(By.ID, "area_code_select"))
        dropdown.select_by_index(dropdown_index)

        time.sleep(1.5)

    def decode_base64(self, response):
        decoded = base64.b64decode(response).decode("utf-8")
        return decoded.split('"data":"')[1].split('"')[0]
    
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

    def scrape_data(self):
        """Main scraping logic"""
        try:
            url = "https://www.jpj.gov.my/semakan-nombor-pendaftaran-terkini/"
            # if not url:
            #     self.show_error("Please enter website URL")
            #     return
            if not self.save_path:
                self.save_path = os.path.join(
                        os.getcwd(),
                        self.generate_default_filename()
                    )                
                self.log(f"No save path selected, using default: {self.save_path}", ft.Colors.ORANGE_700)

            
            self.log("Initializing Chrome driver...", ft.Colors.BLUE_700)
            chrome_options = Options()
            # ===== Stealth / anti-detection =====
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)

            # ===== Performance logging (captcha interceptor NEEDS THIS) =====
            chrome_options.set_capability(
                "goog:loggingPrefs",
                {"performance": "ALL"}
            )

            self.driver = webdriver.Chrome(options=chrome_options)

            # Hide webdriver flag
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
            self.log(f"Navigating to {url}...", ft.Colors.BLUE_700)
            self.driver.get(url)
            
            time.sleep(1.5)
            
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "area_code_select"))
            )
            
            dropdown = Select(self.driver.find_element(By.ID, "area_code_select"))
            total_options = len(dropdown.options) - 1  # skip placeholder

            results = []

            for idx in range(1, total_options + 1):
                if not self.is_scraping:
                    self.log("Scraping stopped by user", ft.Colors.ORANGE_700)
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
                time.sleep(1.5)

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
                else:
                    self.log(f"✗ Failed to get data for {area_code}", ft.Colors.RED_700)
                
                time.sleep(1)
            
            if results:
                df = pd.DataFrame(results)
                self.ensure_save_path()
                df.to_excel(self.save_path, index=False)
                self.log(f"\n✓ Successfully saved {len(results)} records!", ft.Colors.GREEN_700)
                self.show_success(f"Scraping completed!\n{len(results)} records saved to:\n{self.save_path}")
            else:
                self.log("No data collected", ft.Colors.ORANGE_700)
                self.show_warning("No data was collected")
            
        except Exception as e:
            self.log(f"ERROR: {str(e)}", ft.Colors.RED_700)
            self.show_error(f"An error occurred: {str(e)}")
        
        finally:
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
    
    def intercept_captcha(self, timeout=5):
        start = time.time()
        seen = set()
        try:
            while time.time() - start < timeout:
                logs = self.driver.get_log("performance")

                for entry in logs:
                    msg = json.loads(entry["message"])["message"]

                    if msg["method"] == "Network.responseReceived":
                        url = msg["params"]["response"]["url"]

                        if "generate-captcha" in url:
                            request_id = msg["params"]["requestId"]

                            if request_id in seen:
                                continue
                            seen.add(request_id)

                            try:
                                body = self.driver.execute_cdp_cmd(
                                    "Network.getResponseBody",
                                    {"requestId": request_id}
                                )
                                captcha = body.get("body")
                                if captcha:
                                    return captcha.strip()
                            except:
                                pass
                time.sleep(0.2)
            return None
        except Exception as e:
            print(f"Error intercepting captcha: ({e})")
    
    def intercept_latest_response(self, timeout=5):
        start = time.time()
        seen = set()

        while time.time() - start < timeout:
            logs = self.driver.get_log("performance")

            for entry in logs:
                msg = json.loads(entry["message"])["message"]

                if msg["method"] == "Network.responseReceived":
                    response = msg["params"]["response"]
                    url = response.get("url", "")

                    if "semak-no-pendaftaran-terkini" in url:
                        request_id = msg["params"]["requestId"]

                        if request_id in seen:
                            continue
                        seen.add(request_id)

                        try:
                            body = self.driver.execute_cdp_cmd(
                                "Network.getResponseBody",
                                {"requestId": request_id}
                            )

                            raw = body.get("body")
                            if not raw:
                                print("Cant find body")
                                continue

                            print("raw: ", raw)

                            if raw.strip().startswith("{"):
                                decoded = raw
                            else:
                                decoded = base64.b64decode(raw).decode("utf-8")
                            
                            def extract(key):
                                return decoded.split(f'"{key}":"')[1].split('"')[0]
                            
                            def normalize_time(value):
                                return value.replace("\\/", "/")

                            if '"type":"error"' in decoded:
                                return {
                                    "area_code_select": "",
                                    "regno": "Tiada Nombor Pendaftaran Terkini",
                                    "current_time": normalize_time(extract("current_time")),
                                }

                            if '"type":"success"' in decoded:
                                return {
                                    "area_code_select": extract("area_code_select"),
                                    "regno": extract("regno"),
                                    "current_time": normalize_time(extract("current_time")),
                                }
                        except Exception as e:
                            self.log(f"Response parse error: {e}", ft.Colors.RED_700)

            time.sleep(0.2)

        return None

    def start_scraping(self, e):
        """Start scraping in a separate thread"""
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
        """Show error dialog"""
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
        """Show success dialog"""
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
        """Show warning dialog"""
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
    ft.app(target=main)