"""
MEC Report Orchestrator - MECID Subfolder Version
Ensures all reports are downloaded to MECID folders, then runs extractors
"""

import subprocess
import sys
import time
import re
import argparse
from pathlib import Path
from typing import Set

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import Config


def get_expected_reports_from_website() -> Set[str]:
    """Navigate to MEC website and discover all available report IDs."""
    print("=" * 80)
    print("CHECKING MEC WEBSITE FOR AVAILABLE REPORTS")
    print("=" * 80)

    expected_files = set()
    driver = None

    try:
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--window-size=1366,768')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

        print("Initializing Chrome driver...")
        driver = webdriver.Chrome(options=chrome_options)
        print("Chrome driver initialized successfully")

        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("Navigating to MEC website...")
        driver.get("https://mec.mo.gov/MEC/Campaign_Finance/CFSearch.aspx#gsc.tab=0")
        time.sleep(3)

        wait = WebDriverWait(driver, 15)

        if Config.SEARCH_TYPE == "candidate":
            print(f"Searching by candidate: {Config.CANDIDATE_NAME}")
            candidate_input = wait.until(EC.presence_of_element_located(
                ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtCand")
            ))
            candidate_input.clear()
            candidate_input.send_keys(Config.CANDIDATE_NAME)

        elif Config.SEARCH_TYPE == "mecid":
            print(f"Searching by MECID: {Config.COMMITTEE_MECID}")
            mecid_input = wait.until(EC.presence_of_element_located(
                ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtMECID")
            ))
            mecid_input.clear()
            mecid_input.send_keys(Config.COMMITTEE_MECID)

        else:  # committee
            print(f"Searching by committee: {Config.COMMITTEE_NAME}")
            committee_input = wait.until(EC.presence_of_element_located(
                ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtComm")
            ))
            committee_input.clear()
            committee_input.send_keys(Config.COMMITTEE_NAME)

        time.sleep(2)

        search_button = driver.find_element(
            "name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$btnSearch"
        )
        search_button.click()
        time.sleep(5)

        # Check if exact match took us directly to committee page
        try:
            reports_link = driver.find_element("link text", "Reports")
            print("Direct match - already on committee page")
        except:
            # We're on the results page - need to select committee
            results_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_gvResults")
            all_links = results_table.find_elements("tag name", "a")

            mecid_link = None
            discovered_mecid = None
            mecid_pattern = re.compile(r'^[A-Z]\d{5,7}$')

            if Config.SEARCH_TYPE == "mecid":
                target_mecid = Config.COMMITTEE_MECID
                print(f"Looking for exact MECID match: {target_mecid}")

                for link in all_links:
                    link_text = link.text.strip()
                    if link_text == target_mecid:
                        mecid_link = link
                        discovered_mecid = link_text
                        print(f"Found exact MECID: {link_text}")
                        break

                if not mecid_link:
                    print(f"ERROR: MECID {target_mecid} not found in search results")
                    print("Available MECIDs:")
                    for link in all_links:
                        link_text = link.text.strip()
                        if mecid_pattern.match(link_text):
                            print(f"  - {link_text}")
                    return set()
            else:
                for link in all_links:
                    link_text = link.text.strip()
                    if mecid_pattern.match(link_text):
                        mecid_link = link
                        discovered_mecid = link_text
                        print(f"Found MECID: {link_text}")
                        if not Config.COMMITTEE_MECID:
                            Config.COMMITTEE_MECID = discovered_mecid
                            print(f"Saved MECID to Config: {discovered_mecid}")
                        break

            if mecid_link:
                mecid_link.click()
            else:
                print("WARNING: No MECID link found in results")
                return set()

            time.sleep(3)
            reports_link = driver.find_element("link text", "Reports")

        reports_link.click()
        time.sleep(4)

        print("Discovering available years...")
        main_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_grvReportOutside")
        year_labels = main_table.find_elements("css selector", "span[id*='lblYear']")

        available_years = []
        for label in year_labels:
            year_text = label.text.strip()
            year_matches = re.findall(r'(20\d{2})', year_text)
            for year_match in year_matches:
                year = int(year_match)
                if year not in available_years:
                    available_years.append(year)

        available_years.sort(reverse=True)
        print(f"Found years: {available_years}")

        for year in available_years:
            print(f"\nChecking year {year}...")
            main_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_grvReportOutside")
            expand_buttons = main_table.find_elements("css selector", "input[id*='ImgRptRight']")
            year_labels = main_table.find_elements("css selector", "span[id*='lblYear']")

            year_index = None
            for i, label in enumerate(year_labels):
                if str(year) in label.text.strip():
                    year_index = i
                    break

            if year_index is not None and year_index < len(expand_buttons):
                expand_buttons[year_index].click()
                time.sleep(5)

                all_links = driver.find_elements("tag name", "a")
                report_ids = []
                for link in all_links:
                    try:
                        link_text = link.text.strip()
                        if link_text.isdigit() and len(link_text) >= 5 and link.is_displayed():
                            report_ids.append(link_text)
                    except:
                        continue

                for report_id in report_ids:
                    filename = Config.get_filename_pattern(year, report_id)
                    expected_files.add(filename)

                print(f"  Found {len(report_ids)} reports for {year}")

        print(f"\nTotal expected reports: {len(expected_files)}")
        return expected_files

    except Exception as e:
        print(f"\nERROR checking website: {e}")
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        return set()

    finally:
        if driver:
            print("Closing browser...")
            driver.quit()


def get_existing_files(downloads_dir: Path) -> Set[str]:
    """Get set of filenames that already exist in MECID directory."""
    if not downloads_dir.exists():
        return set()
    return {pdf_file.name for pdf_file in downloads_dir.glob("*.pdf")}


def run_downloader() -> bool:
    """Run the download_reports.py script with appropriate arguments."""
    print("\n" + "=" * 80)
    print("RUNNING DOWNLOADER")
    print("=" * 80)

    try:
        cmd = [sys.executable, "download_reports.py"]

        if Config.SEARCH_TYPE == "candidate":
            cmd.extend(["--candidate", Config.CANDIDATE_NAME])
            if Config.COMMITTEE_MECID:
                cmd.extend(["--mecid", Config.COMMITTEE_MECID])
        elif Config.SEARCH_TYPE == "mecid":
            cmd.extend(["--mecid-only", Config.COMMITTEE_MECID])
        else:
            cmd.extend(["--committee", Config.COMMITTEE_NAME])
            if Config.COMMITTEE_MECID:
                cmd.extend(["--mecid", Config.COMMITTEE_MECID])

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0

    except Exception as e:
        print(f"ERROR running downloader: {e}")
        return False


def run_extractors() -> None:
    """Run all extractor scripts for the current MECID."""
    print("\n" + "=" * 80)
    print("RUNNING EXTRACTORS")
    print("=" * 80)

    if not Config.COMMITTEE_MECID:
        print("ERROR: MECID not set, cannot run extractors")
        return

    extractors = [
        ("expense_extractor.py", "expenses"),
        ("donor_extractor.py", "donors")
    ]

    for extractor_file, data_type in extractors:
        print(f"\n>>> Running {extractor_file} for MECID {Config.COMMITTEE_MECID}...")
        try:
            cmd = [sys.executable, extractor_file, "--mecid", Config.COMMITTEE_MECID]
            result = subprocess.run(cmd, capture_output=False, text=True)
            if result.returncode == 0:
                print(f"✓ {extractor_file} completed successfully")
            else:
                print(f"✗ {extractor_file} failed with code {result.returncode}")
        except Exception as e:
            print(f"ERROR running {extractor_file}: {e}")


def main():
    """Main orchestrator logic."""
    parser = argparse.ArgumentParser(
        description='MEC Report Orchestrator - Download and extract campaign finance reports'
    )

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

    print(f"Search configured:")
    print(f"  Type: {Config.SEARCH_TYPE}")
    print(f"  Value: {Config.get_search_value()}")
    print(f"  File prefix: {Config.get_file_prefix()}")

    MAX_RETRIES = 20

    print("\n" + "=" * 80)
    print("MEC REPORT ORCHESTRATOR - MECID SUBFOLDER VERSION")
    print("=" * 80)
    print(f"Target: {Config.get_display_name()}")
    print(f"File prefix: {Config.get_file_prefix()}")
    print(f"Max retry attempts: {MAX_RETRIES}")

    print("\n" + "=" * 80)
    print("STEP 1: CHECKING WHAT REPORTS SHOULD EXIST")
    print("=" * 80)
    expected_files = get_expected_reports_from_website()

    if not expected_files:
        print("\nERROR: Could not determine expected reports from website")
        sys.exit(1)

    if not Config.COMMITTEE_MECID:
        print("\nERROR: Could not determine MECID from website")
        sys.exit(1)

    downloads_dir = Config.ensure_mecid_folder()
    print(f"\nMECID: {Config.COMMITTEE_MECID}")
    print(f"Downloads directory: {downloads_dir}")
    print(f"Expected {len(expected_files)} total reports")

    print("\n" + "=" * 80)
    print("STEP 2: DOWNLOAD LOOP")
    print("=" * 80)

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n--- Attempt {attempt}/{MAX_RETRIES} ---")
        existing_files = get_existing_files(downloads_dir)
        missing_files = expected_files - existing_files

        print(f"Existing files: {len(existing_files)}")
        print(f"Missing files: {len(missing_files)}")

        if not missing_files:
            print("\n✓ ALL REPORTS DOWNLOADED!")
            break

        print("\nSample missing files:")
        for i, filename in enumerate(sorted(missing_files)[:5]):
            print(f"  - {filename}")
        if len(missing_files) > 5:
            print(f"  ... and {len(missing_files) - 5} more")

        print(f"\nRunning downloader (attempt {attempt})...")
        success = run_downloader()
        if not success:
            print("WARNING: Downloader returned error status")

        time.sleep(5)
    else:
        existing_files = get_existing_files(downloads_dir)
        missing_files = expected_files - existing_files

        print("\n" + "=" * 80)
        print("MAX RETRIES REACHED")
        print("=" * 80)
        print(f"Still missing {len(missing_files)} files after {MAX_RETRIES} attempts")
        print("\nMissing files:")
        for filename in sorted(missing_files):
            print(f"  - {filename}")

        response = input("\nProceed with validation and extractors anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

    print("\n" + "=" * 80)
    print("STEP 3: VALIDATING REPORTS")
    print("=" * 80)

    try:
        cmd = [sys.executable, "validate_reports.py", "--mecid", Config.COMMITTEE_MECID]
        result = subprocess.run(cmd, capture_output=False, text=True)
        if result.returncode != 0:
            print("\n⚠ Validation found issues with report filenames")
            response = input("Continue with extractors anyway? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
    except Exception as e:
        print(f"ERROR running validation: {e}")
        response = input("Continue with extractors anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

    print("\n" + "=" * 80)
    print("STEP 4: RUNNING EXTRACTORS")
    print("=" * 80)
    run_extractors()

    print("\n" + "=" * 80)
    print("ORCHESTRATOR COMPLETE")
    print("=" * 80)
    print(f"MECID: {Config.COMMITTEE_MECID}")
    print(f"Download directory: {downloads_dir}")

    existing_files = get_existing_files(downloads_dir)
    print(f"Final file count: {len(existing_files)}/{len(expected_files)}")

    expenses_csv = Config.get_expenses_csv_path()
    donors_csv = Config.get_donors_csv_path()

    if expenses_csv.exists():
        print(f"✓ Expenses CSV: {expenses_csv}")
    if donors_csv.exists():
        print(f"✓ Donors CSV: {donors_csv}")

    if existing_files == expected_files:
        print("\n✓ All reports downloaded and extracted!")
    else:
        missing_count = len(expected_files - existing_files)
        print(f"\n⚠ {missing_count} reports still missing")


if __name__ == "__main__":
    main()