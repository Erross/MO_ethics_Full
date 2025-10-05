import pdfplumber
import re
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from config import Config

def extract_mo_ethics_report_data(pdf_path: str, debug: bool = False) -> Dict[str, Optional[str]]:
    """
    Extract key information from Missouri Ethics Commission Committee Disclosure Reports.

    Args:
        pdf_path: Path to the PDF file
        debug: If True, print detailed extraction information

    Returns:
        Dictionary with extracted data
    """

    extracted_data = {
        'date_of_report': None,
        'committee_name': None,
        'period_start': None,
        'period_end': None,
        'report_type': None
    }

    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]
        text = first_page.extract_text()

        if debug:
            print("\n" + "=" * 80)
            print("DEBUG MODE - RAW TEXT FROM PDF")
            print("=" * 80)
            print(text)
            print("=" * 80 + "\n")

        # Extract Date of Report
        date_pattern = r'DATE OF REPORT.*?(\d{1,2}/\d{1,2}/\d{4})'
        date_match = re.search(date_pattern, text, re.DOTALL)
        if date_match:
            extracted_data['date_of_report'] = date_match.group(1)

        # Extract Committee Name
        committee_pattern = r'FULL NAME OF COMMITTEE\s*\n\s*([^\n]+?)(?=\s*\n\s*\d+\.|$)'
        committee_match = re.search(committee_pattern, text)
        if committee_match:
            extracted_data['committee_name'] = committee_match.group(1).strip()

        # Extract Time Period
        period_pattern = r'FROM\s+(\d{1,2}/\d{1,2}/\d{4}).*?THROUGH\s+(\d{1,2}/\d{1,2}/\d{4})'
        period_match = re.search(period_pattern, text, re.DOTALL)
        if period_match:
            extracted_data['period_start'] = period_match.group(1)
            extracted_data['period_end'] = period_match.group(2)

        # Extract Report Type
        report_types = []
        lines = text.split('\n')

        # Find report type section
        in_report_section = False
        report_section_lines = []

        for line in lines:
            if 'TYPE OF REPORT' in line or ('15.' in line and 'TYPE' in line):
                in_report_section = True
                continue
            if in_report_section:
                if 'TREASURER' in line and 'SIGNATURE' in line:
                    break
                if 'COMMITTEE TREASURER' in line:
                    break
                report_section_lines.append(line)

        report_section_text = '\n'.join(report_section_lines)

        if debug:
            print("REPORT SECTION TEXT:")
            print("-" * 80)
            print(report_section_text)
            print("-" * 80 + "\n")

        # Define report type patterns
        report_type_patterns = {
            'COMMITTEE QUARTERLY REPORT': r'COMMITTEE\s+QUARTERLY\s+REPORT',
            'AMENDING PREVIOUS REPORT': r'AMENDING\s+PREVIOUS\s+REPORT',
            '15 DAYS AFTER CAUCUS NOMINATION': r'15\s+DAYS\s+AFTER\s+CAUCUS',
            '8 DAYS BEFORE': r'8\s+DAYS\s+BEFORE',
            '30 DAYS AFTER ELECTION': r'30\s+DAYS\s+AFTER\s+ELECTION',
            'TERMINATION': r'TERMINATION',
            'SEMIANNUAL DEBT REPORT': r'SEMIANNUAL\s+DEBT\s+REPORT',
            'ANNUAL SUPPLEMENTAL': r'ANNUAL\s+SUPPLEMENTAL',
            '15 DAYS AFTER PETITION DEADLINE': r'15\s+DAYS\s+AFTER\s+PETITION'
        }

        # Check each report type
        lines_list = report_section_text.split('\n')

        for report_name, pattern in report_type_patterns.items():
            match = re.search(pattern, report_section_text, re.IGNORECASE)
            if match:
                match_position = report_section_text[:match.start()].count('\n')

                prev_line = lines_list[match_position - 1] if match_position > 0 else ''
                next_line = lines_list[match_position + 1] if match_position + 1 < len(lines_list) else ''

                # Check for standalone '4' which indicates a checkmark
                has_check = re.match(r'^\s*4\s*$', prev_line) or re.match(r'^\s*4\s*$', next_line)

                if debug:
                    print(f"Checking '{report_name}':")
                    print(f"  Previous line: '{prev_line}'")
                    print(f"  Next line: '{next_line}'")
                    print(f"  Has checkmark: {has_check}\n")

                if has_check and report_name not in report_types:
                    report_types.append(report_name)

                    # Handle quarterly quarter detection
                    if 'QUARTERLY' in report_name and extracted_data['period_end']:
                        try:
                            end_date = datetime.strptime(extracted_data['period_end'], '%m/%d/%Y')
                            month = end_date.month
                            if month <= 1:
                                detected_quarter = 'Jan 15'
                            elif month <= 4:
                                detected_quarter = 'Apr 15'
                            elif month <= 7:
                                detected_quarter = 'Jul 15'
                            else:
                                detected_quarter = 'Oct 15'
                            report_types.append(f'Quarter: {detected_quarter}')
                        except:
                            pass

                    # Handle amending date extraction
                    if 'AMENDING' in report_name:
                        # The date is on a line after "DATED" that contains "REPUBLICAN DEMOCRAT"
                        # Format: "REPUBLICAN DEMOCRAT _____ J _ u _ l _ y _________________ __ 3 __________, 20 _ 2 _ 3 ___"
                        amend_search = report_section_text[match.start():match.start() + 500]

                        if debug:
                            print(f"  Amending search text:\n{amend_search[:200]}")

                        # Find the line with DEMOCRAT
                        amend_lines = amend_search.split('\n')
                        for i, line in enumerate(amend_lines):
                            if 'DEMOCRAT' in line and ('_' in line or any(
                                    c.isalpha() for c in line.replace('DEMOCRAT', '').replace('REPUBLICAN', ''))):
                                if debug:
                                    print(f"  Found DEMOCRAT line: {line}")

                                # Extract the date portion after DEMOCRAT
                                # Split on DEMOCRAT and take what comes after
                                parts = line.split('DEMOCRAT', 1)
                                if len(parts) > 1:
                                    date_portion = parts[1]

                                    if debug:
                                        print(f"  Date portion: {date_portion}")

                                    # Remove underscores and extra spaces, keeping letters and numbers
                                    # This converts "_____ J _ u _ l _ y _________________ __ 3 __________, 20 _ 2 _ 3 ___"
                                    # to something like "J u l y 3 20 2 3"
                                    cleaned = re.sub(r'[_,]+', ' ', date_portion)
                                    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

                                    if debug:
                                        print(f"  Cleaned: {cleaned}")

                                    # Now extract: letters (month), digit(s) (day), digits (year)
                                    # Pattern: one or more letter groups, then digits
                                    tokens = cleaned.split()

                                    # Collect letters for month
                                    month_parts = []
                                    day = None
                                    year_parts = []

                                    for token in tokens:
                                        if token.isalpha():
                                            month_parts.append(token)
                                        elif token.isdigit():
                                            if day is None and len(token) <= 2:
                                                day = token
                                            else:
                                                year_parts.append(token)

                                    if month_parts and day:
                                        month = ''.join(month_parts)
                                        year = ''.join(year_parts) if year_parts else ''

                                        if year:
                                            cleaned_date = f"{month} {day} {year}"
                                        else:
                                            cleaned_date = f"{month} {day}"

                                        report_types.append(f'Amending: {cleaned_date}')
                                        if debug:
                                            print(f"  Final date: {cleaned_date}")
                                        break

        extracted_data['report_type'] = ' | '.join(report_types) if report_types else 'Unknown'

    return extracted_data


def print_extracted_data(data: Dict[str, Optional[str]]) -> None:
    """Pretty print the extracted data."""
    print("=" * 60)
    print("EXTRACTED REPORT INFORMATION")
    print("=" * 60)
    print(f"Date of Report:     {data['date_of_report']}")
    print(f"Committee Name:     {data['committee_name']}")
    print(f"Period Start:       {data['period_start']}")
    print(f"Period End:         {data['period_end']}")
    print(f"Report Type:        {data['report_type']}")
    print("=" * 60)


def process_pdfs_folder(pdfs_folder: str = "PDFs", output_csv: str = "extracted_data.csv", debug: bool = False) -> None:
    """
    Process all PDF files in the specified folder and write results to CSV.
    """
    pdfs_path = Path(pdfs_folder)

    if not pdfs_path.exists():
        print(f"Error: Folder '{pdfs_folder}' not found")
        return

    pdf_files = list(pdfs_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in '{pdfs_folder}' folder")
        return

    print(f"Found {len(pdf_files)} PDF file(s) to process")
    print("=" * 60)

    all_data = []

    for pdf_file in pdf_files:
        print(f"\nProcessing: {pdf_file.name}")
        try:
            data = extract_mo_ethics_report_data(str(pdf_file), debug=debug)
            data['filename'] = pdf_file.name
            all_data.append(data)
            print(f"✓ Successfully extracted data from {pdf_file.name}")
        except Exception as e:
            print(f"✗ Error processing {pdf_file.name}: {str(e)}")
            all_data.append({
                'filename': pdf_file.name,
                'date_of_report': 'ERROR',
                'committee_name': 'ERROR',
                'period_start': 'ERROR',
                'period_end': 'ERROR',
                'report_type': str(e)
            })

    if all_data:
        write_to_csv(all_data, output_csv)
        print(f"\n{'=' * 60}")
        print(f"✓ Data exported to '{output_csv}'")
        print(f"{'=' * 60}")
    else:
        print("No data to export")


def write_to_csv(data: List[Dict], output_file: str) -> None:
    """Write extracted data to CSV file."""
    fieldnames = ['filename', 'date_of_report', 'committee_name', 'period_start', 'period_end', 'report_type']

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)


if __name__ == "__main__":
    DEBUG_MODE = False  # Set to True to see detailed extraction
    process_pdfs_folder(pdfs_folder="PDFs", output_csv="extracted_data.csv", debug=DEBUG_MODE)