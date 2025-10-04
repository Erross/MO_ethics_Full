"""
Step 8: Multi-Year Processing with Captcha Avoidance
VERSION: 8.0 - Process all available years while avoiding detection

Key strategies for captcha avoidance:
- Longer delays between years
- Human-like reading behavior
- Process years in chronological order (most recent first)
- Respectful request pacing
"""

import random
import time
import pyautogui
import re
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

class StealthBrowser:
    """Enhanced stealth browser with anti-detection measures"""

    def __init__(self, driver):
        self.driver = driver
        self.actions = ActionChains(driver)

    def human_delay(self, min_seconds=0.5, max_seconds=2):
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def long_human_delay(self, min_seconds=3, max_seconds=8):
        """Longer delays for between-year processing"""
        delay = random.uniform(min_seconds, max_seconds)
        print(f"      Taking {delay:.1f}s break (captcha avoidance)...")
        time.sleep(delay)

    def human_click(self, element):
        self.actions.move_to_element(element).perform()
        self.human_delay(0.5, 1.2)
        element.click()
        self.human_delay(0.5, 1.2)

    def mimic_reading(self, duration_seconds=None):
        if duration_seconds is None:
            duration_seconds = random.uniform(2, 5)  # Longer reading times
        print(f"      Reading page for {duration_seconds:.1f}s...")
        time.sleep(duration_seconds)


def get_existing_report_ids(downloads_dir):
    """Get list of report IDs that have already been downloaded"""
    existing_ids = set()

    for pdf_file in downloads_dir.glob("*.pdf"):
        filename = pdf_file.name
        match = re.search(r'(\d{5,})\.pdf$', filename)
        if match:
            report_id = match.group(1)
            existing_ids.add(report_id)

    return existing_ids


def wait_for_generation_complete_simple(driver, max_wait=60):
    """Wait for generation to complete"""
    start_time = time.time()

    while (time.time() - start_time) < max_wait:
        try:
            elapsed = int(time.time() - start_time)

            page_source = driver.page_source.lower()
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()

            generation_indicators = [
                "generating report",
                "this may take several minutes",
                "% completed",
                "gathering the required information"
            ]

            still_generating = any(indicator in page_source or indicator in page_text
                                 for indicator in generation_indicators)

            if not still_generating:
                return True

            if elapsed % 10 == 0:
                print(f"          {elapsed}s: Still generating...")
            time.sleep(2)

        except Exception as e:
            time.sleep(2)

    return False


def download_pdf_simple(downloads_dir, target_filename):
    """Simple PDF download"""
    try:
        pyautogui.hotkey('ctrl', 's')
        time.sleep(3)

        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.5)

        full_path = str(downloads_dir / target_filename)
        pyautogui.write(full_path, interval=0.03)
        time.sleep(2)

        pyautogui.press('enter')

        for i in range(20):
            time.sleep(1)
            if (downloads_dir / target_filename).exists():
                file_size = (downloads_dir / target_filename).stat().st_size
                return True, file_size

        return False, 0

    except Exception as e:
        return False, 0


def download_single_report(driver, stealth, report_link, downloads_dir, year, report_num, total_reports):
    """Download a single report"""

    report_id = report_link.text.strip()
    target_filename = f"FHF_{year}_Step8_{report_id}.pdf"

    print(f"    Report {report_num}/{total_reports}: {report_id}")

    try:
        original_window = driver.current_window_handle
        stealth.human_click(report_link)

        # Wait for new tab
        new_window = None
        for wait_time in range(1, 10):
            time.sleep(1)
            all_windows = driver.window_handles
            for window in all_windows:
                if window != original_window:
                    new_window = window
                    break
            if new_window:
                break

        if not new_window:
            print(f"      ERROR: No new tab opened")
            return False, 0

        driver.switch_to.window(new_window)

        if not wait_for_generation_complete_simple(driver, max_wait=60):
            print(f"      ERROR: Generation failed")
            driver.close()
            driver.switch_to.window(original_window)
            return False, 0

        time.sleep(10)  # Wait for rendering
        success, file_size = download_pdf_simple(downloads_dir, target_filename)

        driver.close()
        driver.switch_to.window(original_window)

        if success:
            print(f"      SUCCESS: {file_size:,} bytes")
        else:
            print(f"      FAILED: Download error")

        return success, file_size

    except Exception as e:
        print(f"      ERROR: {e}")
        try:
            driver.switch_to.window(original_window)
        except:
            pass
        return False, 0


def process_single_year(driver, stealth, year, downloads_dir, existing_ids):
    """Process all reports for a single year - IMPROVED VERSION"""

    print(f"\n=== Processing Year {year} ===")

    try:
        # IMPORTANT: Get fresh elements each time to avoid stale references
        main_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_grvReportOutside")
        expand_buttons = main_table.find_elements("css selector", "input[id*='ImgRptRight']")
        year_labels = main_table.find_elements("css selector", "span[id*='lblYear']")

        # Find the specific year and its expand button
        year_index = None
        for i, label in enumerate(year_labels):
            if str(year) in label.text.strip():
                year_index = i
                print(f"  Found {year} at index {i}")
                break

        if year_index is None or year_index >= len(expand_buttons):
            print(f"  Year {year} not found or no expand button")
            return 0, 0, 0

        # Check if year is already expanded by looking at the expand button
        expand_button = expand_buttons[year_index]

        # Click to expand this specific year
        print(f"  Expanding {year} section...")
        stealth.human_click(expand_button)
        stealth.mimic_reading(4)  # Wait for expansion

        # Wait for the specific year's content to load
        time.sleep(5)

        # Now find ALL links on the page and try to identify which belong to this year
        # This is tricky - we need to find links that appeared after expanding this year
        all_links = driver.find_elements("tag name", "a")
        potential_report_links = []

        for link in all_links:
            try:
                link_text = link.text.strip()
                if link_text.isdigit() and len(link_text) >= 5:
                    # Check if this link is visible and belongs to our year section
                    if link.is_displayed():
                        potential_report_links.append(link)
            except:
                continue

        print(f"  Found {len(potential_report_links)} potential report links")

        # Filter out already downloaded reports
        new_report_links = []
        skipped_count = 0

        for link in potential_report_links:
            try:
                report_id = link.text.strip()
                if report_id in existing_ids:
                    skipped_count += 1
                else:
                    new_report_links.append(link)
            except:
                continue

        print(f"  Skipped {skipped_count} already downloaded")
        print(f"  Will attempt to download {len(new_report_links)} new reports")

        if len(new_report_links) == 0:
            print(f"  All {year} reports already downloaded")
            return len(potential_report_links), skipped_count, 0

        # Download new reports for this year
        successful_downloads = 0

        for i, report_link in enumerate(new_report_links):
            try:
                success, file_size = download_single_report(
                    driver, stealth, report_link, downloads_dir, year, i+1, len(new_report_links)
                )

                if success:
                    successful_downloads += 1
                    # Add to existing_ids to avoid downloading again
                    report_id = report_link.text.strip()
                    existing_ids.add(report_id)

                # Pause between downloads within a year
                if i < len(new_report_links) - 1:
                    time.sleep(random.uniform(2, 4))

            except Exception as e:
                print(f"    Error downloading report {i+1}: {e}")
                continue

        print(f"  Year {year} complete: {successful_downloads}/{len(new_report_links)} downloaded")
        return len(potential_report_links), skipped_count, successful_downloads

    except Exception as e:
        print(f"  ERROR processing year {year}: {e}")
        return 0, 0, 0


def run_step_8_multi_year():
    """Step 8: Process ALL available years - FIXED VERSION"""

    downloads_dir = Path.cwd() / "PDFs"
    downloads_dir.mkdir(exist_ok=True)

    print("=== Step 8: Multi-Year Processing (FIXED) ===")
    print("Will process ALL available years, no matter how many")
    print("Each committee may have different years available")
    print("This may take 45-90 minutes for committees with many years")

    # Check existing files
    existing_ids = get_existing_report_ids(downloads_dir)
    print(f"\nFound {len(existing_ids)} existing reports to skip")

    # Chrome setup - NUCLEAR OPTION: Let Selenium find ChromeDriver automatically
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('--window-size=1366,768')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    prefs = {
        "plugins.always_open_pdf_externally": False,
        "download.default_directory": str(downloads_dir)
    }
    chrome_options.add_experimental_option("prefs", prefs)

    # NUCLEAR OPTION: No ChromeDriverManager - let Selenium handle it
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    stealth = StealthBrowser(driver)

    try:
        # Navigate to reports page
        print(f"\n1. Navigating to Francis Howell Families reports...")
        driver.get("https://mec.mo.gov/MEC/Campaign_Finance/CFSearch.aspx#gsc.tab=0")
        stealth.mimic_reading(2)

        wait = WebDriverWait(driver, 15)
        committee_input = wait.until(EC.presence_of_element_located(("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtComm")))
        committee_input.clear()
        for c in "Francis Howell Families":
            committee_input.send_keys(c)
            time.sleep(random.uniform(0.05,0.15))
        stealth.human_delay(1,3)

        search_button = driver.find_element("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$btnSearch")
        stealth.human_click(search_button)
        stealth.mimic_reading(3)

        results_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_gvResults")
        mecid_links = results_table.find_elements("partial link text", "C2116")
        stealth.human_click(mecid_links[0])
        stealth.mimic_reading(3)

        reports_link = driver.find_element("link text", "Reports")
        stealth.human_click(reports_link)
        stealth.mimic_reading(4)

        # Discover ALL available years - IMPROVED VERSION
        print(f"2. Discovering ALL available years...")

        # Get fresh elements
        main_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_grvReportOutside")
        year_labels = main_table.find_elements("css selector", "span[id*='lblYear']")

        available_years = []
        print("   Available year sections:")
        for i, label in enumerate(year_labels):
            year_text = label.text.strip()
            print(f"     Section {i}: '{year_text}'")

            # Extract 4-digit year - be more flexible with matching
            year_matches = re.findall(r'(20\d{2})', year_text)
            for year_match in year_matches:
                year = int(year_match)
                if year not in available_years:
                    available_years.append(year)

        # Sort years in reverse chronological order (most recent first)
        available_years.sort(reverse=True)
        print(f"   Extracted years: {available_years}")

        if len(available_years) == 0:
            print("   ERROR: No years found!")
            return False

        # Process each year individually
        session_stats = {
            'total_found': 0,
            'total_skipped': 0,
            'total_downloaded': 0,
            'years_processed': 0,
            'years_failed': 0
        }

        session_start = datetime.now()

        for year_num, year in enumerate(available_years):
            print(f"\n{'='*60}")
            print(f"Processing Year {year} ({year_num+1}/{len(available_years)})")

            # Process this specific year
            found, skipped, downloaded = process_single_year(
                driver, stealth, year, downloads_dir, existing_ids
            )

            session_stats['total_found'] += found
            session_stats['total_skipped'] += skipped
            session_stats['total_downloaded'] += downloaded

            if found > 0 or downloaded > 0:
                session_stats['years_processed'] += 1
            else:
                session_stats['years_failed'] += 1

            # Long delay between years for captcha avoidance
            if year_num < len(available_years) - 1:
                print(f"   Completed {year}. Taking break before next year...")
                stealth.long_human_delay(6, 15)  # Longer delays between years

        # Final summary
        session_end = datetime.now()
        runtime = session_end - session_start

        print(f"\n{'='*80}")
        print(f"=== STEP 8 FINAL SUMMARY ===")
        print(f"Session runtime: {runtime}")
        print(f"Years available: {len(available_years)} {available_years}")
        print(f"Years with reports: {session_stats['years_processed']}")
        print(f"Years failed/empty: {session_stats['years_failed']}")
        print(f"Total reports found: {session_stats['total_found']}")
        print(f"Reports skipped (existing): {session_stats['total_skipped']}")
        print(f"NEW reports downloaded: {session_stats['total_downloaded']}")

        final_existing_ids = get_existing_report_ids(downloads_dir)
        print(f"Total unique reports now in directory: {len(final_existing_ids)}")

        if session_stats['total_downloaded'] > 0:
            print(f"\nSUCCESS: Downloaded {session_stats['total_downloaded']} new reports across all years!")
            return True
        elif len(final_existing_ids) > 0:
            print(f"\nCOMPLETE: All available reports already downloaded")
            return True
        else:
            print(f"\nISSUE: No reports found or downloaded")
            return False

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        try:
            driver.quit()
        except:
            pass
        print("Browser closed.")


if __name__ == "__main__":
    print("Step 8: Multi-Year Processing with Captcha Avoidance")
    print("=" * 55)

    success = run_step_8_multi_year()

    if success:
        print("\nStep 8 COMPLETE - All years processed!")
        print("Francis Howell Families dataset is now complete")
    else:
        print("\nStep 8 had issues - check errors above")