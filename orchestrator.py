"""
MEC Report Orchestrator
Ensures all reports are downloaded, then runs extractors

Process:
1. Check what reports SHOULD exist (from MEC website)
2. Compare to what DOES exist (in /PDFs)
3. If missing files → run downloader
4. Repeat until all files present or max retries hit
5. Validate reports
6. Run extractors once complete

Usage:
    python orchestrator.py                                    # Use default committee
    python orchestrator.py --committee "Committee Name"       # Override committee
    python orchestrator.py --committee "Committee Name" --mecid "C1234"  # With MEC ID
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
    """
    Navigate to MEC website and discover all available report IDs.
    Returns a set of expected filenames.
    """
    print("=" * 80)
    print("CHECKING MEC WEBSITE FOR AVAILABLE REPORTS")
    print("=" * 80)

    expected_files = set()
    driver = None

    try:
        # EXACT same Chrome setup as working downloader
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

        # Navigate to MEC site
        print("Navigating to MEC website...")
        driver.get("https://mec.mo.gov/MEC/Campaign_Finance/CFSearch.aspx#gsc.tab=0")
        time.sleep(3)

        # Search for committee
        wait = WebDriverWait(driver, 15)
        committee_input = wait.until(EC.presence_of_element_located(
            ("name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$txtComm")
        ))
        committee_input.clear()
        committee_input.send_keys(Config.COMMITTEE_NAME)
        time.sleep(2)

        # Click search
        search_button = driver.find_element(
            "name", "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolder1$btnSearch"
        )
        search_button.click()
        time.sleep(3)

        # Click on committee (use MECID if available, otherwise first result)
        results_table = driver.find_element("id", "ContentPlaceHolder_ContentPlaceHolder1_gvResults")
        if Config.COMMITTEE_MECID:
            mecid_links = results_table.find_elements("partial link text", Config.COMMITTEE_MECID)
            if mecid_links:
                mecid_links[0].click()
            else:
                # Fallback to first result
                print(f"WARNING: MECID {Config.COMMITTEE_MECID} not found, using first result")
                first_link = results_table.find_element("tag name", "a")
                first_link.click()
        else:
            # Use first result
            first_link = results_table.find_element("tag name", "a")
            first_link.click()
        time.sleep(3)

        # Go to Reports tab
        reports_link = driver.find_element("link text", "Reports")
        reports_link.click()
        time.sleep(4)

        # Discover all available years
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

        # Process each year to find report IDs
        for year in available_years:
            print(f"\nChecking year {year}...")

            # Find and click expand button for this year
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

                # Find all report links for this year
                all_links = driver.find_elements("tag name", "a")
                report_ids = []

                for link in all_links:
                    try:
                        link_text = link.text.strip()
                        if link_text.isdigit() and len(link_text) >= 5:
                            if link.is_displayed():
                                report_ids.append(link_text)
                    except:
                        continue

                # Generate expected filenames using Config
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
    """Get set of filenames that already exist in PDFs directory."""
    if not downloads_dir.exists():
        return set()

    existing = set()
    for pdf_file in downloads_dir.glob("*.pdf"):
        existing.add(pdf_file.name)

    return existing


def run_downloader() -> bool:
    """Run the download_reports.py script."""
    print("\n" + "=" * 80)
    print("RUNNING DOWNLOADER")
    print("=" * 80)

    try:
        result = subprocess.run(
            [sys.executable, "download_reports.py"],
            capture_output=False,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR running downloader: {e}")
        return False


def run_extractors() -> None:
    """Run all extractor scripts."""
    print("\n" + "=" * 80)
    print("RUNNING EXTRACTORS")
    print("=" * 80)

    extractors = [
        "expense_extractor.py",
        "donor_extractor.py"
    ]

    for extractor in extractors:
        print(f"\n>>> Running {extractor}...")
        try:
            result = subprocess.run(
                [sys.executable, extractor],
                capture_output=False,
                text=True
            )
            if result.returncode == 0:
                print(f"✓ {extractor} completed successfully")
            else:
                print(f"✗ {extractor} failed with code {result.returncode}")
        except Exception as e:
            print(f"ERROR running {extractor}: {e}")


def main():
    """Main orchestrator logic."""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='MEC Report Orchestrator - Download and extract campaign finance reports'
    )
    parser.add_argument(
        '--committee',
        type=str,
        help='Committee name to process (default: Francis Howell Families)'
    )
    parser.add_argument(
        '--mecid',
        type=str,
        help='MEC Committee ID for targeted search (e.g., C2116)'
    )

    args = parser.parse_args()

    # Set committee if provided
    if args.committee:
        Config.set_committee(args.committee, args.mecid)
        print(f"Processing committee: {Config.COMMITTEE_NAME}")
        print(f"File prefix: {Config.get_file_prefix()}")

    downloads_dir = Path.cwd() / "PDFs"
    downloads_dir.mkdir(exist_ok=True)

    MAX_RETRIES = 20

    print("=" * 80)
    print("MEC REPORT ORCHESTRATOR")
    print("=" * 80)
    print(f"Committee: {Config.COMMITTEE_NAME}")
    print(f"File prefix: {Config.get_file_prefix()}")
    print(f"Max retry attempts: {MAX_RETRIES}")
    print(f"Downloads directory: {downloads_dir}")

    # Get expected reports from website
    print("\n" + "=" * 80)
    print("STEP 1: CHECKING WHAT REPORTS SHOULD EXIST")
    print("=" * 80)

    expected_files = get_expected_reports_from_website()

    if not expected_files:
        print("\nERROR: Could not determine expected reports from website")
        print("Cannot proceed without knowing what to download")
        sys.exit(1)

    print(f"\nExpected {len(expected_files)} total reports")

    # Download loop
    print("\n" + "=" * 80)
    print("STEP 2: DOWNLOAD LOOP")
    print("=" * 80)

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n--- Attempt {attempt}/{MAX_RETRIES} ---")

        # Check current status
        existing_files = get_existing_files(downloads_dir)
        missing_files = expected_files - existing_files

        print(f"Existing files: {len(existing_files)}")
        print(f"Missing files: {len(missing_files)}")

        if not missing_files:
            print("\n✓ ALL REPORTS DOWNLOADED!")
            break

        # Show sample of missing files
        print(f"\nSample missing files:")
        for i, filename in enumerate(sorted(missing_files)[:5]):
            print(f"  - {filename}")
        if len(missing_files) > 5:
            print(f"  ... and {len(missing_files) - 5} more")

        # Run downloader
        print(f"\nRunning downloader (attempt {attempt})...")
        success = run_downloader()

        if not success:
            print(f"WARNING: Downloader returned error status")

        # Wait before rechecking
        time.sleep(5)

    else:
        # Max retries reached
        existing_files = get_existing_files(downloads_dir)
        missing_files = expected_files - existing_files

        print("\n" + "=" * 80)
        print("MAX RETRIES REACHED")
        print("=" * 80)
        print(f"Still missing {len(missing_files)} files after {MAX_RETRIES} attempts")
        print("\nMissing files:")
        for filename in sorted(missing_files):
            print(f"  - {filename}")

        # Ask user if they want to proceed with extractors anyway
        response = input("\nProceed with validation and extractors anyway? (y/n): ")
        if response.lower() != 'y':
            print("Exiting without running extractors")
            sys.exit(1)

    # Validate reports
    print("\n" + "=" * 80)
    print("STEP 3: VALIDATING REPORTS")
    print("=" * 80)

    try:
        result = subprocess.run(
            [sys.executable, "validate_reports.py"],
            capture_output=False,
            text=True
        )

        if result.returncode != 0:
            print("\n⚠ Validation found issues with report filenames")
            response = input("Continue with extractors anyway? (y/n): ")
            if response.lower() != 'y':
                print("Exiting - please fix validation issues first")
                sys.exit(1)
    except Exception as e:
        print(f"ERROR running validation: {e}")
        response = input("Continue with extractors anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

    # Run extractors
    print("\n" + "=" * 80)
    print("STEP 4: RUNNING EXTRACTORS")
    print("=" * 80)

    run_extractors()

    # Final summary
    print("\n" + "=" * 80)
    print("ORCHESTRATOR COMPLETE")
    print("=" * 80)

    existing_files = get_existing_files(downloads_dir)
    print(f"Final file count: {len(existing_files)}/{len(expected_files)}")

    if existing_files == expected_files:
        print("✓ All reports downloaded and extracted!")
    else:
        missing_count = len(expected_files - existing_files)
        print(f"⚠ {missing_count} reports still missing")


if __name__ == "__main__":
    main()