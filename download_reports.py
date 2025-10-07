"""
Multi-Year Processing with Captcha Avoidance - MECID Subfolder Version
Downloads to PDFs/{MECID}/ subdirectories
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

from config import Config


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
            duration_seconds = random.uniform(2, 5)
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

        # Use absolute path to ensure Chrome finds the directory
        full_path = str(downloads_dir.resolve() / target_filename)
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
    target_filename = Config.get_filename_pattern(year, report_id)

    print(f"    Report {report_num}/{total_reports}: {report_id}")

    try:
        original_window = driver.current_window_handle
        stealth.human_click(report_link)

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

        time.sleep(10)
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
    """Process all reports for a single year"""
    print(f"\n=== Processing Year {year} ===")

    try:
        main_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_grvReportOutside")
        expand_buttons = main_table.find_elements("css selector", "input[id*='ImgRptRight']")
        year_labels = main_table.find_elements("css selector", "span[id*='lblYear']")

        year_index = None
        for i, label in enumerate(year_labels):
            if str(year) in label.text.strip():
                year_index = i
                print(f"  Found {year} at index {i}")
                break

        if year_index is None or year_index >= len(expand_buttons):
            print(f"  Year {year} not found or no expand button")
            return 0, 0, 0

        expand_button = expand_buttons[year_index]
        print(f"  Expanding {year} section...")
        stealth.human_click(expand_button)
        stealth.mimic_reading(4)
        time.sleep(5)

        all_links = driver.find_elements("tag name", "a")
        potential_report_links = []

        for link in all_links:
            try:
                link_text = link.text.strip()
                if link_text.isdigit() and len(link_text) >= 5:
                    if link.is_displayed():
                        potential_report_links.append(link)
            except:
                continue

        print(f"  Found {len(potential_report_links)} potential report links")

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

        successful_downloads = 0

        for i, report_link in enumerate(new_report_links):
            try:
                success, file_size = download_single_report(
                    driver, stealth, report_link, downloads_dir, year, i+1, len(new_report_links)
                )

                if success:
                    successful_downloads += 1
                    report_id = report_link.text.strip()
                    existing_ids.add(report_id)

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
    """Process ALL available years with MECID subfolders"""

    if not Config.COMMITTEE_MECID:
        print("ERROR: MECID must be discovered or set before downloading")
        print("Run orchestrator.py instead, which discovers MECID automatically")
        return False

    # Create MECID folder BEFORE configuring Chrome
    downloads_dir = Config.ensure_mecid_folder()

    # Verify folder exists
    if not downloads_dir.exists():
        print(f"ERROR: Could not create folder {downloads_dir}")
        return False

    print("=== Step 8: Multi-Year Processing with MECID Folders ===")
    print(f"Target MECID: {Config.COMMITTEE_MECID}")
    print(f"Downloads folder: {downloads_dir}")
    print(f"Folder exists: {downloads_dir.exists()}")

    existing_ids = get_existing_report_ids(downloads_dir)
    print(f"\nFound {len(existing_ids)} existing reports to skip")

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

    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    stealth = StealthBrowser(driver)

    try:
        print(f"\n1. Navigating to search page...")
        print(f"   Search type: {Config.SEARCH_TYPE}")
        print(f"   Search value: {Config.get_search_value()}")

        driver.get("https://mec.mo.gov/MEC/Campaign_Finance/CFSearch.aspx#gsc.tab=0")
        stealth.mimic_reading(2)

        wait = WebDriverWait(driver, 15)

        if Config.SEARCH_TYPE == "candidate":
            print(f"   Searching by candidate: {Config.CANDIDATE_NAME}")
            candidate_input = wait.until(EC.presence_of_element_located(
                ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtCand")
            ))
            candidate_input.clear()
            for c in Config.CANDIDATE_NAME:
                candidate_input.send_keys(c)
                time.sleep(random.uniform(0.05, 0.15))

        elif Config.SEARCH_TYPE == "mecid":
            print(f"   Searching by MECID: {Config.COMMITTEE_MECID}")
            mecid_input = wait.until(EC.presence_of_element_located(
                ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtMECID")
            ))
            mecid_input.clear()
            mecid_input.send_keys(Config.COMMITTEE_MECID)
            time.sleep(random.uniform(0.05, 0.15))

        else:  # committee (default)
            print(f"   Searching by committee: {Config.COMMITTEE_NAME}")
            committee_input = wait.until(EC.presence_of_element_located(
                ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtComm")
            ))
            committee_input.clear()
            for c in Config.COMMITTEE_NAME:
                committee_input.send_keys(c)
                time.sleep(random.uniform(0.05, 0.15))

        stealth.human_delay(1, 3)

        search_button = driver.find_element("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$btnSearch")
        stealth.human_click(search_button)
        stealth.mimic_reading(5)

        # Check if exact match took us directly to committee page
        try:
            reports_link = driver.find_element("link text", "Reports")
            print(f"   Direct match - already on committee page")
        except:
            # We're on the results page - need to select committee
            results_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_gvResults")
            all_links = results_table.find_elements("tag name", "a")
            mecid_pattern = re.compile(r'^[A-Z]\d{5,7}$')

            if Config.SEARCH_TYPE == "mecid":
                target_mecid = Config.COMMITTEE_MECID
                print(f"   Looking for exact MECID match: {target_mecid}")

                mecid_found = False
                for link in all_links:
                    link_text = link.text.strip()
                    if link_text == target_mecid:
                        print(f"   Found exact MECID: {link_text}")
                        stealth.human_click(link)
                        mecid_found = True
                        break

                if not mecid_found:
                    print(f"   ERROR: MECID {target_mecid} not found in results")
                    print("   Available MECIDs:")
                    for link in all_links:
                        link_text = link.text.strip()
                        if mecid_pattern.match(link_text):
                            print(f"     - {link_text}")
                    return False
            else:
                if Config.COMMITTEE_MECID:
                    target_mecid = Config.COMMITTEE_MECID
                    mecid_found = False
                    for link in all_links:
                        link_text = link.text.strip()
                        if link_text == target_mecid:
                            print(f"   Found committee with exact MECID {target_mecid}")
                            stealth.human_click(link)
                            mecid_found = True
                            break

                    if not mecid_found:
                        print(f"   WARNING: MECID {target_mecid} not found, using first result")
                        first_link = results_table.find_element("tag name", "a")
                        stealth.human_click(first_link)
                else:
                    print(f"   Using first search result")
                    first_link = results_table.find_element("tag name", "a")
                    stealth.human_click(first_link)

            stealth.mimic_reading(3)
            reports_link = driver.find_element("link text", "Reports")

        stealth.human_click(reports_link)
        stealth.mimic_reading(4)

        print(f"2. Discovering ALL available years...")

        main_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_grvReportOutside")
        year_labels = main_table.find_elements("css selector", "span[id*='lblYear']")

        available_years = []
        print("   Available year sections:")
        for i, label in enumerate(year_labels):
            year_text = label.text.strip()
            print(f"     Section {i}: '{year_text}'")

            year_matches = re.findall(r'(20\d{2})', year_text)
            for year_match in year_matches:
                year = int(year_match)
                if year not in available_years:
                    available_years.append(year)

        available_years.sort(reverse=True)
        print(f"   Extracted years: {available_years}")

        if len(available_years) == 0:
            print("   ERROR: No years found!")
            return False

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

            if year_num < len(available_years) - 1:
                print(f"   Completed {year}. Taking break before next year...")
                stealth.long_human_delay(6, 15)

        session_end = datetime.now()
        runtime = session_end - session_start

        print(f"\n{'='*80}")
        print(f"=== STEP 8 FINAL SUMMARY ===")
        print(f"Session runtime: {runtime}")
        print(f"MECID: {Config.COMMITTEE_MECID}")
        print(f"Download folder: {downloads_dir}")
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
    import argparse

    parser = argparse.ArgumentParser(description='Download MEC reports')

    search_group = parser.add_mutually_exclusive_group()
    search_group.add_argument('--committee', type=str, help='Committee name to process')
    search_group.add_argument('--candidate', type=str, help='Candidate name to process')
    search_group.add_argument('--mecid-only', type=str, dest='mecid_only', help='Search by MEC ID only')

    parser.add_argument('--mecid', type=str, help='MEC Committee ID for filtering results')

    args = parser.parse_args()

    if args.mecid_only:
        Config.set_search(mecid=args.mecid_only)
    elif args.candidate:
        Config.set_search(candidate=args.candidate, mecid=args.mecid)
    elif args.committee:
        Config.set_search(committee=args.committee, mecid=args.mecid)

    print("Step 8: Multi-Year Processing with MECID Folders")
    print("=" * 55)
    print(f"Target: {Config.get_display_name()}")
    print(f"Search type: {Config.SEARCH_TYPE}")
    print(f"File prefix: {Config.get_file_prefix()}")

    if Config.COMMITTEE_MECID:
        print(f"MECID folder: {Config.get_mecid_folder()}")
        success = run_step_8_multi_year()

        if success:
            print("\nStep 8 COMPLETE - All years processed!")
            print(f"{Config.get_display_name()} dataset is now complete")
        else:
            print("\nStep 8 had issues - check errors above")
    else:
        print("\nERROR: MECID must be provided")
        print("Use: python download_reports.py --mecid-only C2116")
        print("Or run orchestrator.py which discovers MECID automatically")