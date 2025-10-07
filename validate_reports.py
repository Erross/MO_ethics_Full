"""
Report Validation Script - MECID Subfolder Version
Validates that PDF filenames match their actual filing dates

Usage:
    python validate_reports.py --mecid C2116
"""

import re
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Optional
import pdfplumber

from config import Config


def extract_filename_info(filename: str) -> Optional[Dict]:
    """Extract year and report ID from filename using config pattern."""
    pattern = Config.get_filename_regex()
    match = re.match(pattern, filename)
    if match:
        return {
            'filename_year': int(match.group(1)),
            'report_id': match.group(2),
            'filename': filename
        }
    return None


def extract_filing_date_from_pdf(pdf_path: str) -> Optional[str]:
    """Extract filing date from PDF (reusing extractor logic)."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()

            date_patterns = [
                r'Report Date\s*\n\s*(\d{1,2}/\d{1,2}/\d{4})',
                r'DATE OF REPORT.*?(\d{1,2}/\d{1,2}/\d{4})',
            ]

            for pattern in date_patterns:
                match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                if match:
                    return match.group(1)

            return None

    except Exception as e:
        print(f"  ERROR reading {Path(pdf_path).name}: {e}")
        return None


def get_year_from_date(date_str: str) -> Optional[int]:
    """Extract year from date string (M/D/YYYY format)."""
    if not date_str:
        return None

    try:
        parts = date_str.split('/')
        if len(parts) == 3:
            return int(parts[2])
    except:
        pass

    return None


def validate_reports(mecid: str = None) -> tuple[bool, List[Dict]]:
    """
    Validate all reports in MECID folder.
    Returns (all_valid, issues_list)

    Args:
        mecid: MEC Committee ID (required)
    """
    if not mecid:
        print("ERROR: MECID is required")
        print("Usage: python validate_reports.py --mecid C2116")
        return False, []

    # Set Config MECID
    Config.COMMITTEE_MECID = mecid
    pdfs_folder = Config.get_mecid_folder()

    if not pdfs_folder.exists():
        print(f"ERROR: Folder '{pdfs_folder}' not found")
        return False, []

    pdf_files = list(pdfs_folder.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in '{pdfs_folder}'")
        return True, []

    print("=" * 80)
    print("VALIDATING REPORT FILENAMES")
    print("=" * 80)
    print(f"MECID: {mecid}")
    print(f"Folder: {pdfs_folder}")
    print(f"Checking {len(pdf_files)} files...")

    # Group files by report ID to find duplicates
    by_report_id = defaultdict(list)

    for pdf_file in pdf_files:
        info = extract_filename_info(pdf_file.name)
        if info:
            by_report_id[info['report_id']].append({
                **info,
                'path': pdf_file
            })

    # Identify which report IDs have duplicates with different years
    duplicate_ids = []
    for report_id, files in by_report_id.items():
        if len(files) > 1:
            years = set(f['filename_year'] for f in files)
            if len(years) > 1:
                duplicate_ids.append(report_id)

    if duplicate_ids:
        print(f"\nFound {len(duplicate_ids)} report IDs with multiple year versions:")
        for rid in duplicate_ids:
            print(f"  Report {rid}: {[f['filename_year'] for f in by_report_id[rid]]}")
    else:
        print("\nNo duplicate report IDs with conflicting years found")
        print("Skipping detailed validation (not needed)")
        return True, []

    # Validate only the duplicate report IDs
    print(f"\nValidating {len(duplicate_ids)} report(s) with conflicts...")

    issues = []

    for report_id in duplicate_ids:
        files = by_report_id[report_id]
        print(f"\n--- Report ID: {report_id} ---")

        for file_info in files:
            filename = file_info['filename']
            filename_year = file_info['filename_year']
            pdf_path = file_info['path']

            filing_date = extract_filing_date_from_pdf(str(pdf_path))

            if not filing_date:
                issue = {
                    'filename': filename,
                    'report_id': report_id,
                    'filename_year': filename_year,
                    'filing_date': None,
                    'filing_year': None,
                    'status': 'ERROR',
                    'message': 'Could not extract filing date from PDF'
                }
                issues.append(issue)
                print(f"  ✗ {filename}")
                print(f"    ERROR: Could not read filing date")
                continue

            filing_year = get_year_from_date(filing_date)

            if not filing_year:
                issue = {
                    'filename': filename,
                    'report_id': report_id,
                    'filename_year': filename_year,
                    'filing_date': filing_date,
                    'filing_year': None,
                    'status': 'ERROR',
                    'message': f'Could not parse year from date: {filing_date}'
                }
                issues.append(issue)
                print(f"  ✗ {filename}")
                print(f"    ERROR: Could not parse year from {filing_date}")
                continue

            # Check if years match
            if filename_year == filing_year:
                print(f"  ✓ {filename}")
                print(f"    Filing date: {filing_date} (year matches)")
            else:
                issue = {
                    'filename': filename,
                    'report_id': report_id,
                    'filename_year': filename_year,
                    'filing_date': filing_date,
                    'filing_year': filing_year,
                    'status': 'MISMATCH',
                    'message': f'Filename year {filename_year} != filing year {filing_year}'
                }
                issues.append(issue)
                print(f"  ✗ {filename}")
                print(f"    MISMATCH: Filename says {filename_year}, but filed {filing_date} ({filing_year})")

    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    if not issues:
        print("✓ All reports validated successfully!")
        print("  No mismatches found")
        return True, []
    else:
        mismatches = [i for i in issues if i['status'] == 'MISMATCH']
        errors = [i for i in issues if i['status'] == 'ERROR']

        print(f"✗ Found {len(issues)} issue(s):")
        print(f"  - {len(mismatches)} year mismatches")
        print(f"  - {len(errors)} read errors")

        if mismatches:
            print("\nYear Mismatches:")
            for issue in mismatches:
                print(f"  {issue['filename']}")
                prefix = Config.get_file_prefix()
                print(f"    Should be: {prefix}_{issue['filing_year']}_Step8_{issue['report_id']}.pdf")

        if errors:
            print("\nRead Errors:")
            for issue in errors:
                print(f"  {issue['filename']}: {issue['message']}")

        return False, issues


def main():
    """Run validation and exit with appropriate code."""
    parser = argparse.ArgumentParser(description='Validate MEC report filenames')
    parser.add_argument('--mecid', type=str, required=True, help='MEC Committee ID (e.g., C2116)')

    args = parser.parse_args()

    all_valid, issues = validate_reports(mecid=args.mecid)

    if all_valid:
        print("\n✓ Validation complete - all reports OK")
        return 0
    else:
        print("\n✗ Validation found issues - review needed")
        print("\nRecommended action:")
        print("1. Review mismatched files")
        print("2. Re-download affected reports")
        print("3. Or manually rename files to match filing dates")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())