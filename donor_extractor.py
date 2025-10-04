import pdfplumber
import re
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict


def extract_report_metadata(pdf_path: str) -> Dict:
    """Extract basic report info to identify and deduplicate reports."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()

            metadata = {
                'filename': Path(pdf_path).name,
                'committee_name': None,
                'period_start': None,
                'period_end': None,
                'date_filed': None,
                'is_amendment': False
            }

            committee_match = re.search(r'FULL NAME OF COMMITTEE\s*\n\s*([^\n]+)', text)
            if committee_match:
                metadata['committee_name'] = committee_match.group(1).strip()

            period_match = re.search(r'FROM\s+(\d{1,2}/\d{1,2}/\d{4}).*?THROUGH\s+(\d{1,2}/\d{1,2}/\d{4})', text,
                                     re.DOTALL)
            if period_match:
                metadata['period_start'] = period_match.group(1)
                metadata['period_end'] = period_match.group(2)

            date_match = re.search(r'DATE OF REPORT.*?(\d{1,2}/\d{1,2}/\d{4})', text, re.DOTALL)
            if date_match:
                metadata['date_filed'] = date_match.group(1)

            lines = text.split('\n')
            for i, line in enumerate(lines):
                if 'AMENDING PREVIOUS REPORT' in line:
                    if (i > 0 and lines[i - 1].strip() == '4') or (i < len(lines) - 1 and lines[i + 1].strip() == '4'):
                        metadata['is_amendment'] = True

            return metadata
    except Exception as e:
        print(f"WARNING: Could not read {Path(pdf_path).name} - {str(e)}")
        return None


def filter_latest_reports(pdf_files: List[Path]) -> List[Path]:
    """Filter to keep only the most recent version of each report period."""
    reports_by_period = defaultdict(list)
    corrupted_files = []

    for pdf_file in pdf_files:
        metadata = extract_report_metadata(str(pdf_file))

        if metadata is None:
            corrupted_files.append(pdf_file.name)
            continue

        if metadata['committee_name'] and metadata['period_end']:
            key = (metadata['committee_name'], metadata['period_end'])
            reports_by_period[key].append((pdf_file, metadata))

    if corrupted_files:
        print(f"\nSkipped {len(corrupted_files)} corrupted/invalid PDF(s):")
        for filename in corrupted_files:
            print(f"  - {filename}")

    latest_reports = []
    for key, reports in reports_by_period.items():
        reports.sort(
            key=lambda x: datetime.strptime(x[1]['date_filed'], '%m/%d/%Y') if x[1]['date_filed'] else datetime.min,
            reverse=True)
        latest_reports.append(reports[0][0])

        if len(reports) > 1:
            print(f"\nFound {len(reports)} versions for {key[0]} ending {key[1]}:")
            print(f"  Keeping: {reports[0][0].name} (filed {reports[0][1]['date_filed']})")
            for report in reports[1:]:
                print(f"  Skipping: {report[0].name} (filed {report[1]['date_filed']})")

    return latest_reports


def is_contributions_page(text: str) -> bool:
    """Check if this page contains contribution data."""
    text_upper = text.upper()
    return ('CONTRIBUTIONS' in text_upper and
            ('ITEMIZED' in text_upper or 'SUPPLEMENTAL' in text_upper) and
            'RECEIVED' in text_upper)


def clean_donor_record(donor: Dict) -> Optional[Dict]:
    """Post-process a donor record to properly parse the name/address/city fields."""

    if donor.get('donor_name') and '\n' in donor['donor_name']:
        full_text = donor['donor_name']
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]

        name = None
        address = None
        city_state = None
        employer = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Pattern 1: "NAME:" alone, name is on NEXT line
            if line == 'NAME:' or (line.startswith('NAME:') and line.replace('NAME:', '').strip() == ''):
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # If next line is "ADDRESS: [name]", extract name from there
                    if next_line.startswith('ADDRESS:'):
                        name_text = next_line.replace('ADDRESS:', '').strip()
                        if name_text and not name_text.startswith(('CITY', 'EMPLOYER:', 'COMMITTEE:')):
                            name = name_text
                            # Address is on the line after that
                            if i + 2 < len(lines):
                                addr_line = lines[i + 2]
                                if not addr_line.startswith(('CITY', 'EMPLOYER:', 'COMMITTEE:', 'ADDRESS:', 'NAME:')):
                                    address = addr_line
                            # Skip the ADDRESS: line we just processed
                            i += 1
                    # Otherwise, next line is the name itself
                    elif not next_line.startswith(('ADDRESS:', 'CITY', 'EMPLOYER:', 'COMMITTEE:')):
                        name = next_line

            # Pattern 2: "ADDRESS: Name" - name is after ADDRESS: on same line (only if we don't have name yet)
            elif line.startswith('ADDRESS:') and not name:
                name_text = line.replace('ADDRESS:', '').strip()
                if name_text and not name_text.startswith(('CITY', 'EMPLOYER:', 'COMMITTEE:')):
                    name = name_text
                    # Next line should be street address
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if not next_line.startswith(('CITY', 'EMPLOYER:', 'COMMITTEE:', 'ADDRESS:', 'NAME:')):
                            address = next_line

            # Pattern 3: "ADDRESS:" alone with address on next line (only if we already have a name)
            elif line.startswith('ADDRESS:') and name and not address:
                addr_text = line.replace('ADDRESS:', '').strip()
                if not addr_text:  # ADDRESS: is empty, address is on next line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1]
                        if not next_line.startswith(('CITY', 'EMPLOYER:', 'COMMITTEE:', 'ADDRESS:', 'NAME:')):
                            address = next_line

            # Pattern for CITY / STATE
            elif 'CITY' in line and 'STATE' in line:
                city_line_text = re.sub(r'CITY\s*/?\s*STATE:\s*', '', line, flags=re.IGNORECASE).strip()

                if city_line_text and not city_line_text.startswith(('EMPLOYER:', 'COMMITTEE:')):
                    if not address:
                        address = city_line_text
                    elif not city_state:
                        city_state = city_line_text

                # Next line after CITY / STATE: could be city/state or street address
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if not next_line.startswith(('EMPLOYER:', 'COMMITTEE:', 'ADDRESS:', 'NAME:')):
                        if address and not city_state:
                            city_state = next_line
                        elif not address:
                            address = next_line

            # Pattern for EMPLOYER
            elif line.startswith('EMPLOYER:'):
                employer_text = line.replace('EMPLOYER:', '').strip()
                if employer_text:
                    employer = employer_text
                elif i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if not next_line.startswith(('COMMITTEE:', 'ADDRESS:', 'CITY', 'NAME:')):
                        employer = next_line

            i += 1

        if not name or name in ['ADDRESS:', 'CITY', 'STATE', 'EMPLOYER:', 'COMMITTEE:', 'NAME:']:
            return None

        # If city_state is blank but employer looks like a city/state/zip, use it
        if not city_state and employer:
            if re.search(r'\s+\d{5}(-\d{4})?$', employer):
                city_state = employer
                employer = None

        donor['donor_name'] = name
        donor['donor_address'] = address
        donor['donor_city_state'] = city_state

    if donor.get('donor_name') and all(label in donor['donor_name'] for label in ['ADDRESS:', 'CITY']):
        return None

    return donor


def extract_donors_from_pdf(pdf_path: str, debug: bool = False) -> List[Dict]:
    """Extract all donor information from a PDF report."""
    donors = []
    metadata = extract_report_metadata(pdf_path)

    if metadata is None:
        return donors

    source_report = Path(pdf_path).name

    if debug:
        print(f"\n{'=' * 60}")
        print(f"Processing: {source_report}")
        print(f"Committee: {metadata['committee_name']}")
        print(f"Period: {metadata['period_start']} to {metadata['period_end']}")
        print(f"{'=' * 60}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()

                if not is_contributions_page(text):
                    continue

                if debug:
                    print(f"\n--- Page {page_num}: Contributions page detected ---")

                table_settings = {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_tolerance": 15,
                }

                tables = page.extract_tables(table_settings)

                for table_num, table in enumerate(tables):
                    if debug:
                        print(f"\nTable {table_num + 1} on page {page_num}:")
                        print(f"  Rows: {len(table)}")

                    page_donors = parse_contribution_table(table, source_report, metadata, debug)

                    cleaned_donors = []
                    for donor in page_donors:
                        cleaned = clean_donor_record(donor)
                        if cleaned:
                            cleaned_donors.append(cleaned)

                    donors.extend(cleaned_donors)

                    if debug:
                        print(f"  Extracted {len(cleaned_donors)} donors from this table")
    except Exception as e:
        print(f"Error processing {source_report}: {str(e)}")

    return donors


def parse_contribution_table(table: List[List[str]], source_report: str, metadata: Dict, debug: bool = False) -> List[
    Dict]:
    """Parse donor data from extracted table."""
    donors = []

    if not table or len(table) < 2:
        return donors

    header_row = None
    date_col = None
    amount_col = None
    type_col = None

    for i, row in enumerate(table[:5]):
        if not row:
            continue
        row_text = ' '.join([str(cell) or '' for cell in row]).upper()

        if 'DATE' in row_text and 'RECEIVED' in row_text:
            header_row = i
            for j, cell in enumerate(row):
                if cell and 'DATE' in str(cell).upper():
                    date_col = j
                if cell and 'AMOUNT' in str(cell).upper():
                    amount_col = j
                if cell and ('MONETARY' in str(cell).upper() or 'IN-KIND' in str(cell).upper()):
                    type_col = j
            break

    if debug and header_row is not None:
        print(f"    Header found at row {header_row}")
        print(f"    Columns - Date: {date_col}, Amount: {amount_col}, Type: {type_col}")

    start_row = (header_row + 1) if header_row is not None else 0

    i = start_row
    while i < len(table):
        row = table[i]

        if not row or not any(row):
            i += 1
            continue

        first_col = str(row[0] or '').strip()

        if first_col.startswith('ADDRESS:') or first_col.startswith('NAME:'):
            donor = parse_donor_entry(table, i, date_col, amount_col, type_col, source_report, metadata, debug)
            if donor and donor.get('donor_name'):
                donors.append(donor)
                if debug:
                    print(f"    Row {i}: Found donor - {donor.get('donor_name', 'UNKNOWN')}")

        i += 1

    return donors


def parse_donor_entry(table: List[List[str]], start_row: int, date_col: Optional[int],
                      amount_col: Optional[int], type_col: Optional[int],
                      source_report: str, metadata: Dict, debug: bool = False) -> Optional[Dict]:
    """Parse a single donor entry from a table cell that contains multi-line text."""
    donor = {
        'source_report': source_report,
        'committee_name': metadata.get('committee_name', ''),
        'report_period': f"{metadata.get('period_start', '')} to {metadata.get('period_end', '')}",
        'donor_name': None,
        'donor_address': None,
        'donor_city_state': None,
        'date_received': None,
        'amount': None,
        'contribution_type': None
    }

    if start_row >= len(table):
        return None

    row = table[start_row]
    if not row:
        return None

    first_col = str(row[0] or '').strip()

    garbage_patterns = [
        'SUBTOTAL', 'TOTAL:', 'SUM COLUMN', 'ITEMIZED CONTRIBUTIONS',
        'NON-ITEMIZED', 'FUND-RAISERS', 'LOANS', 'FORM CD',
        'MISSOURI ETHICS', 'SUPPLEMENTAL', 'Amendment Detail',
        'B. NON-ITEMIZED', 'Added-Wolf'
    ]

    if any(pattern in first_col for pattern in garbage_patterns):
        return None

    if first_col.isdigit() or len(first_col) < 3:
        return None

    donor['donor_name'] = first_col

    if date_col is not None and date_col < len(row):
        date_cell = str(row[date_col] or '').strip()
        if date_cell:
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_cell)
            if date_match:
                donor['date_received'] = date_match.group(1)

    if amount_col is not None and amount_col < len(row):
        amount_cell = str(row[amount_col] or '').strip()
        if amount_cell:
            amount_match = re.search(r'\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)', amount_cell)
            if amount_match:
                donor['amount'] = amount_match.group(1).replace(',', '')

    if type_col is not None and type_col < len(row):
        type_cell = str(row[type_col] or '').strip()
        if type_cell:
            type_cell_upper = type_cell.upper()

            if 'MONETARY' in type_cell_upper:
                monetary_pos = type_cell_upper.find('MONETARY')
                inkind_pos = type_cell_upper.find('IN-KIND') if 'IN-KIND' in type_cell_upper else len(type_cell_upper)

                before_monetary = type_cell[:monetary_pos]
                if '4' in before_monetary or 'X' in before_monetary.upper() or '☑' in before_monetary:
                    donor['contribution_type'] = 'Monetary'
                elif inkind_pos < len(type_cell_upper):
                    before_inkind = type_cell[monetary_pos:inkind_pos]
                    if '4' in before_inkind or 'X' in before_inkind.upper():
                        donor['contribution_type'] = 'In-Kind'

            elif 'IN-KIND' in type_cell_upper or 'IN KIND' in type_cell_upper:
                donor['contribution_type'] = 'In-Kind'

    if not donor['donor_name'] or len(donor['donor_name']) < 2:
        return None

    return donor


def process_all_donors(pdfs_folder: str = "PDFs", output_csv: str = "donors_data.csv", debug: bool = False) -> None:
    """Main function to process all PDFs and extract donor data."""
    pdfs_path = Path(pdfs_folder)

    if not pdfs_path.exists():
        print(f"Error: Folder '{pdfs_folder}' not found")
        return

    pdf_files = list(pdfs_path.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in '{pdfs_folder}' folder")
        return

    print(f"Found {len(pdf_files)} PDF file(s)")
    print("=" * 60)

    print("\nFiltering for latest report versions...")
    latest_reports = filter_latest_reports(pdf_files)
    print(f"\n{'=' * 60}")
    print(f"Processing {len(latest_reports)} report(s) after filtering")
    print("=" * 60)

    all_donors = []

    for pdf_file in latest_reports:
        try:
            donors = extract_donors_from_pdf(str(pdf_file), debug=debug)
            all_donors.extend(donors)
            print(f"[OK] {pdf_file.name}: Found {len(donors)} donor(s)")
        except Exception as e:
            print(f"[ERROR] {pdf_file.name}: {str(e)}")

    if all_donors:
        write_donors_to_csv(all_donors, output_csv)
        print(f"\n{'=' * 60}")
        print(f"Extracted {len(all_donors)} total donor records")
        print(f"Data exported to '{output_csv}'")
        print(f"{'=' * 60}")
    else:
        print("\nNo donor data extracted")


def write_donors_to_csv(donors: List[Dict], output_file: str) -> None:
    """Write donor data to CSV file."""
    fieldnames = [
        'source_report',
        'committee_name',
        'report_period',
        'donor_name',
        'donor_address',
        'donor_city_state',
        'date_received',
        'amount',
        'contribution_type'
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(donors)


if __name__ == "__main__":
    DEBUG_MODE = False
    process_all_donors(pdfs_folder="PDFs", output_csv="donors_data.csv", debug=DEBUG_MODE)