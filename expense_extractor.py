import pdfplumber
import re
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
from config import Config

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

            committee_match = re.search(r'Name of Committee\s*\n\s*([^\n]+)', text, re.IGNORECASE)
            if not committee_match:
                committee_match = re.search(r'FULL NAME OF COMMITTEE\s*\n\s*([^\n]+)', text)
            if committee_match:
                metadata['committee_name'] = committee_match.group(1).strip()

            period_match = re.search(r'FROM\s+(\d{1,2}/\d{1,2}/\d{4}).*?THROUGH\s+(\d{1,2}/\d{1,2}/\d{4})', text,
                                     re.DOTALL)
            if period_match:
                metadata['period_start'] = period_match.group(1)
                metadata['period_end'] = period_match.group(2)

            date_match = re.search(r'Report Date\s*\n\s*(\d{1,2}/\d{1,2}/\d{4})', text, re.IGNORECASE)
            if not date_match:
                date_match = re.search(r'DATE OF REPORT.*?(\d{1,2}/\d{1,2}/\d{4})', text, re.DOTALL)
            if date_match:
                metadata['date_filed'] = date_match.group(1)

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


def is_expense_page(text: str) -> tuple:
    """Check if this page contains expense data. Returns (is_expense, page_types_list)."""
    text_upper = text.upper()
    page_types = []

    # Check for detailed itemized expenses page (main or supplemental)
    if ('ITEMIZED EXPENDITURES' in text_upper and 'ALL OVER $100' in text_upper) or \
            ('ITEMIZED EXPENDITURES OVER $100' in text_upper):
        page_types.append('detailed')

    # Check for contributions made page - only add if NOT already processing detailed expenses
    # This prevents double-counting of vendor payments
    if 'CONTRIBUTIONS MADE' in text_upper and 'CANDIDATE OR COMMITTEE' in text_upper:
        if 'detailed' not in page_types:  # Only process if not already parsing as detailed
            page_types.append('contributions')

    # Check for category expenses - can be on supplemental form OR main CD3 form
    if 'EXPENDITURES OF $100 OR LESS BY CATEGORY' in text_upper:
        page_types.append('category')

    # Also check for the main CD3 form that has category section
    if 'EXPENDITURES AND CONTRIBUTIONS MADE' in text_upper and \
            'CATEGORY OF EXPENDITURE' in text_upper:
        if 'category' not in page_types:  # Don't add twice
            page_types.append('category')

    if page_types:
        return (True, page_types)
    return (False, [])


def clean_field_text(text: str) -> str:
    """Remove label prefixes from field text."""
    if not text:
        return text

    # Remove common label prefixes
    text = re.sub(r'^NAME:\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^ADDRESS:\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^CITY\s*/?\s*STATE:\s*', '', text, flags=re.IGNORECASE)

    return text.strip()


def is_form_summary_row(text: str) -> bool:
    """Check if this is a form summary/instruction row."""
    if not text:
        return False

    text_upper = text.upper()

    # Skip numbered form items
    if re.match(r'^\d{1,2}\.\s', text):
        return True

    # Skip common form instruction rows and headers
    form_phrases = [
        'AMOUNT OF LINE',
        'IF COMMITTEE MADE',
        'FUNDS USED FOR PAYING',
        'SUBTOTAL',
        'TOTAL:',
        'SUM COLUMN',
        'CARRY TO ITEM',
        'NAME AND ADDRESS OF RECIPIENT',
        'C. CONTRIBUTIONS MADE',
        'CONTRIBUTIONS MADE (REGARDLESS',
        '20. NAME AND ADDRESS',
        'ITEMIZED EXPENDITURES',
        'AND ALL PAYMENTS TO CAMPAIGN',
        'B. ITEMIZED EXPENDITURES'
    ]

    return any(phrase in text_upper for phrase in form_phrases)


def extract_amount_from_cell(amount_cell: str) -> Optional[str]:
    """Extract monetary amount from cell text, handling checkbox markers."""
    if not amount_cell:
        return None

    # Remove newlines and multiple spaces for easier processing
    cleaned_cell = ' '.join(amount_cell.split())

    # Strategy 1: Look for amounts with "Paid" or "Incurred" keywords
    # This handles: "$ 4 Paid 161.80 Incurred" -> extract 161.80
    paid_amount_match = re.search(r'(?:PAID|Paid)\s+(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', cleaned_cell, re.IGNORECASE)
    if paid_amount_match:
        amount = paid_amount_match.group(1).replace(',', '')
        try:
            if float(amount) >= 0.50:
                return amount
        except ValueError:
            pass

    # Strategy 2: Look for amount immediately after $ with comma formatting
    # This handles: "$4,990.53" or "$ 4,990.53"
    comma_amount_match = re.search(r'\$\s*(\d{1,3}(?:,\d{3})+(?:\.\d{2})?)', amount_cell)
    if comma_amount_match:
        return comma_amount_match.group(1).replace(',', '')

    # Strategy 3: Look for 3+ digit amount after $
    # This handles: "$146.00" or "$ 995.00"
    large_amount_match = re.search(r'\$\s*(\d{3,}(?:\.\d{2})?)', amount_cell)
    if large_amount_match:
        return large_amount_match.group(1).replace(',', '')

    # Strategy 4: Look for 2-digit amount with decimal after $
    # This handles: "$10.75" or "$ 65.07"
    small_amount_match = re.search(r'\$\s*(\d{1,2}\.\d{2})', amount_cell)
    if small_amount_match:
        return small_amount_match.group(1).replace(',', '')

    # Strategy 5: Look for standalone numbers with commas (no $ needed)
    standalone_comma_match = re.search(r'(?<!\d)(\d{1,3}(?:,\d{3})+(?:\.\d{2})?)(?!\d)', amount_cell)
    if standalone_comma_match:
        return standalone_comma_match.group(1).replace(',', '')

    # Strategy 6: Look for 3+ digit standalone numbers
    standalone_large_match = re.search(r'(?<!\d)(\d{3,}(?:\.\d{2})?)(?!\d)', amount_cell)
    if standalone_large_match:
        return standalone_large_match.group(1).replace(',', '')

    # Strategy 7: Look for any decimal numbers (for small amounts like 8.06)
    decimal_match = re.search(r'(?<!\d)(\d{1,2}\.\d{2})(?!\d)', amount_cell)
    if decimal_match:
        return decimal_match.group(1).replace(',', '')

    return None


def is_valid_amount(amount_str: str) -> bool:
    """Check if amount string represents a valid monetary amount."""
    if not amount_str:
        return False

    try:
        amount = float(amount_str)
        # Lowered threshold to $0.50 to capture small service fees
        return amount >= 0.50
    except ValueError:
        return False


def parse_detailed_expense_table(table: List[List[str]], source_report: str, metadata: Dict, debug: bool = False) -> \
List[Dict]:
    """Parse detailed expense data with name/address from table."""
    expenses = []

    if not table or len(table) < 2:
        return expenses

    # Find column indices
    header_row = None
    date_col = None
    purpose_col = None
    amount_col = None

    for i, row in enumerate(table[:10]):
        if not row:
            continue
        row_text = ' '.join([str(cell) or '' for cell in row]).upper()

        if 'DATE' in row_text and 'PURPOSE' in row_text:
            header_row = i
            for j, cell in enumerate(row):
                cell_text = str(cell or '').upper()
                if 'DATE' in cell_text and 'RECEIVED' not in cell_text:
                    date_col = j
                if 'PURPOSE' in cell_text:
                    purpose_col = j
                if 'AMOUNT THIS PERIOD' in cell_text or ('AMOUNT' in cell_text and 'PERIOD' in cell_text):
                    amount_col = j
            break

    if debug and header_row is not None:
        print(f"    Header found at row {header_row}")
        print(f"    Columns - Date: {date_col}, Purpose: {purpose_col}, Amount: {amount_col}")

    start_row = (header_row + 1) if header_row is not None else 0

    # Parse expense entries
    for i in range(start_row, len(table)):
        row = table[i]

        if not row or not any(row):
            continue

        first_col = str(row[0] or '').strip()

        # Skip form summary/instruction rows
        if is_form_summary_row(first_col):
            continue

        # Check if this row has expense data
        if first_col and len(first_col) > 3:
            # Check if amount column has a valid value
            has_valid_amount = False
            if amount_col is not None and amount_col < len(row):
                amount_cell = str(row[amount_col] or '').strip()
                amount_str = extract_amount_from_cell(amount_cell)
                if amount_str and is_valid_amount(amount_str):
                    has_valid_amount = True

            if has_valid_amount:
                expense = parse_detailed_expense_entry(table, i, date_col, purpose_col, amount_col,
                                                       source_report, metadata, debug)
                if expense:
                    expenses.append(expense)
                    if debug:
                        print(
                            f"    ✓ Row {i}: Found expense - {expense.get('payee_name', 'UNKNOWN')} - ${expense.get('amount', '0')}")

    return expenses


def parse_contributions_table(table: List[List[str]], source_report: str, metadata: Dict, debug: bool = False) -> List[
    Dict]:
    """Parse contributions made to other committees."""
    contributions = []

    if not table or len(table) < 2:
        return contributions

    # Find column indices
    header_row = None
    date_col = None
    amount_col = None

    for i, row in enumerate(table[:10]):
        if not row:
            continue
        row_text = ' '.join([str(cell) or '' for cell in row]).upper()

        if 'DATE' in row_text and ('AMOUNT' in row_text or 'CANDIDATE OR COMMITTEE' in row_text):
            header_row = i
            for j, cell in enumerate(row):
                cell_text = str(cell or '').upper()
                if 'DATE' in cell_text:
                    date_col = j
                if 'AMOUNT' in cell_text:
                    amount_col = j
            break

    start_row = (header_row + 1) if header_row is not None else 0

    # Parse contribution entries
    for i in range(start_row, len(table)):
        row = table[i]

        if not row or not any(row):
            continue

        first_col = str(row[0] or '').strip()

        # Skip form summary/instruction rows
        if is_form_summary_row(first_col):
            continue

        if first_col and len(first_col) > 3:
            # Check if amount column has a value
            has_valid_amount = False
            if amount_col is not None and amount_col < len(row):
                amount_cell = str(row[amount_col] or '').strip()
                amount_str = extract_amount_from_cell(amount_cell)
                if amount_str and is_valid_amount(amount_str):
                    has_valid_amount = True

            if has_valid_amount:
                contribution = parse_contribution_entry(table, i, date_col, amount_col,
                                                        source_report, metadata, debug)
                if contribution:
                    contributions.append(contribution)
                    if debug:
                        print(
                            f"    Row {i}: Found contribution - {contribution.get('payee_name', 'UNKNOWN')} - ${contribution.get('amount', '0')}")

    return contributions


def parse_contribution_entry(table: List[List[str]], start_row: int, date_col: Optional[int],
                             amount_col: Optional[int], source_report: str, metadata: Dict,
                             debug: bool = False) -> Optional[Dict]:
    """Parse a single contribution entry."""

    contribution = {
        'source_report': source_report,
        'committee_name': metadata.get('committee_name', ''),
        'report_period': f"{metadata.get('period_start', '')} to {metadata.get('period_end', '')}",
        'payee_name': None,
        'payee_address': None,
        'payee_city_state': None,
        'date': None,
        'purpose': 'Contribution to Committee',
        'amount': None,
        'payment_status': None,
        'expense_type': 'Contribution'
    }

    if start_row >= len(table):
        return None

    row = table[start_row]
    if not row:
        return None

    # Parse the multiline first column for name/address
    first_col = str(row[0] or '').strip()

    if '\n' in first_col:
        # FIXED: Clean FIRST, then filter empty lines
        lines = [clean_field_text(line.strip()) for line in first_col.split('\n')]
        lines = [line for line in lines if line]  # Filter empty after cleaning

        # First line is typically the committee name
        if lines:
            contribution['payee_name'] = lines[0]

        # Second line is typically the address
        if len(lines) > 1:
            contribution['payee_address'] = lines[1]

        # Third line is typically city/state/zip
        if len(lines) > 2:
            contribution['payee_city_state'] = lines[2]
    else:
        contribution['payee_name'] = clean_field_text(first_col)

    # Extract date
    if date_col is not None and date_col < len(row):
        date_cell = str(row[date_col] or '').strip()
        if date_cell:
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_cell)
            if date_match:
                contribution['date'] = date_match.group(1)

    # Extract amount
    if amount_col is not None and amount_col < len(row):
        amount_cell = str(row[amount_col] or '').strip()
        amount_str = extract_amount_from_cell(amount_cell)
        if amount_str and is_valid_amount(amount_str):
            contribution['amount'] = amount_str

    if not contribution['payee_name'] or not contribution['amount']:
        return None

    return contribution


def parse_detailed_expense_entry(table: List[List[str]], start_row: int, date_col: Optional[int],
                                 purpose_col: Optional[int], amount_col: Optional[int],
                                 source_report: str, metadata: Dict, debug: bool = False) -> Optional[Dict]:
    """Parse a single detailed expense entry."""

    expense = {
        'source_report': source_report,
        'committee_name': metadata.get('committee_name', ''),
        'report_period': f"{metadata.get('period_start', '')} to {metadata.get('period_end', '')}",
        'payee_name': None,
        'payee_address': None,
        'payee_city_state': None,
        'date': None,
        'purpose': None,
        'amount': None,
        'payment_status': None,
        'expense_type': 'Expense'
    }

    if start_row >= len(table):
        return None

    row = table[start_row]
    if not row:
        return None

    # Parse the multiline first column for name/address
    first_col = str(row[0] or '').strip()

    if '\n' in first_col:
        # FIXED: Clean FIRST, then filter empty lines
        lines = [clean_field_text(line.strip()) for line in first_col.split('\n')]
        lines = [line for line in lines if line]  # Filter empty after cleaning

        # First line is typically the payee name
        if lines:
            expense['payee_name'] = lines[0]

        # Second line is typically the address
        if len(lines) > 1:
            expense['payee_address'] = lines[1]

        # Third line is typically city/state/zip
        if len(lines) > 2:
            expense['payee_city_state'] = lines[2]
    else:
        expense['payee_name'] = clean_field_text(first_col)

    # Extract date
    if date_col is not None and date_col < len(row):
        date_cell = str(row[date_col] or '').strip()
        if date_cell:
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', date_cell)
            if date_match:
                expense['date'] = date_match.group(1)

    # Extract purpose
    if purpose_col is not None and purpose_col < len(row):
        purpose_cell = str(row[purpose_col] or '').strip()

        # Check if purpose cell contains a date (swapped columns)
        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', purpose_cell)
        if date_match and not expense['date']:
            # Columns are swapped - this is the date
            expense['date'] = date_match.group(1)
        else:
            # Normal purpose field
            purpose_cell = re.sub(r'\$\s*$', '', purpose_cell)
            if purpose_cell:
                expense['purpose'] = purpose_cell

    # Extract amount and payment status
    if amount_col is not None and amount_col < len(row):
        amount_cell = str(row[amount_col] or '').strip()

        # Check for Paid/Incurred status
        if '✔' in amount_cell or '✓' in amount_cell or 'PAID' in amount_cell.upper():
            expense['payment_status'] = 'Paid'
        elif 'INCURRED' in amount_cell.upper():
            expense['payment_status'] = 'Incurred'

        # Extract amount using improved method
        amount_str = extract_amount_from_cell(amount_cell)
        if amount_str and is_valid_amount(amount_str):
            expense['amount'] = amount_str

    if not expense['payee_name'] or not expense['amount']:
        return None

    return expense


def is_valid_category_name(category: str) -> bool:
    """Check if a category name is valid (not a form instruction or junk)."""
    if not category or len(category) < 2:
        return False

    category_upper = category.upper()

    # Skip form instructions/headers
    invalid_patterns = [
        'NAME:',
        'ADDRESS:',
        'CITY',
        'STATE:',
        'SUBTOTAL',
        'TOTAL',
        'SUM COLUMN',
        'CARRY TO',
        'AMOUNT OF LINE',
        'EXPENDITURES AND CONTRIBUTIONS',
        'CATEGORY OF EXPENDITURE',
        'FUNDS USED FOR PAYING',
    ]

    # Allow numbered items that are NOT form instructions (16., 17., etc are usually form fields)
    # But "2nd batch business cards" should be allowed
    if re.match(r'^\d{1,2}\.\s', category) and not any(
            word in category.lower() for word in ['batch', 'card', 'fee', 'service']):
        return False

    if any(pattern in category_upper for pattern in invalid_patterns):
        return False

    # Must contain at least one letter
    if not re.search(r'[a-zA-Z]', category):
        return False

    return True


def parse_category_expense_table(table: List[List[str]], source_report: str, metadata: Dict, debug: bool = False) -> \
List[Dict]:
    """Parse category expenses (aggregated expenses $100 or less)."""
    expenses = []

    if not table or len(table) < 2:
        return expenses

    if debug:
        print(f"    Parsing category table with {len(table)} rows")

    # Find where actual category data starts
    start_row = 0
    for i, row in enumerate(table):
        if not row:
            continue
        row_text = ' '.join([str(cell) or '' for cell in row]).upper()
        if 'CATEGORY OF EXPENDITURE' in row_text:
            start_row = i + 1
            if debug:
                print(f"    Category header found at row {i}, starting data at row {start_row}")
            break

    # Parse each expense category
    for i in range(start_row, len(table)):
        row = table[i]

        if not row or not any(row):
            continue

        category = str(row[0] or '').strip()

        if debug:
            print(f"    Row {i}: category='{category}'")

        # Validate category name
        if not is_valid_category_name(category):
            if debug:
                print(f"      Rejected: invalid category name")
            continue

        # Look for amount in the row
        amount = None
        for j, cell in enumerate(row[1:], start=1):
            cell_text = str(cell or '').strip()
            if cell_text:
                amount = extract_amount_from_cell(cell_text)
                if amount and is_valid_amount(amount):
                    if debug:
                        print(f"      Found amount ${amount} in column {j}")
                    break

        # Skip if no amount found OR if amount is $0.00 (form instructions)
        if not amount or float(amount) == 0.0:
            if debug:
                print(f"      Rejected: no amount or $0.00")
            continue

        expense = {
            'source_report': source_report,
            'committee_name': metadata.get('committee_name', ''),
            'report_period': f"{metadata.get('period_start', '')} to {metadata.get('period_end', '')}",
            'payee_name': None,
            'payee_address': None,
            'payee_city_state': None,
            'date': metadata.get('date_filed'),  # Use filing date for categories
            'purpose': category,
            'amount': amount,
            'payment_status': 'Category',
            'expense_type': 'Expense'
        }
        expenses.append(expense)

        if debug:
            print(f"    ✓ Found category expense: {category} - ${amount}")

    return expenses


def deduplicate_expenses(expenses: List[Dict]) -> List[Dict]:
    """Remove duplicate expenses based on payee, amount, and date."""
    seen = set()
    deduplicated = []

    for expense in expenses:
        # Create a unique key for this expense
        # For category expenses (no payee), use purpose + amount + date
        if expense.get('payment_status') == 'Category':
            key = (
                expense.get('purpose', ''),
                expense.get('amount', ''),
                expense.get('date', ''),
                'Category'
            )
        else:
            # For itemized expenses, use payee + amount + date
            key = (
                expense.get('payee_name', ''),
                expense.get('amount', ''),
                expense.get('date', ''),
                expense.get('expense_type', '')
            )

        if key not in seen:
            seen.add(key)
            deduplicated.append(expense)

    return deduplicated


def extract_expenses_from_pdf(pdf_path: str, debug: bool = False) -> List[Dict]:
    """Extract all expense information from a PDF report."""
    expenses = []
    metadata = extract_report_metadata(pdf_path)

    if metadata is None:
        return expenses

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

                is_expense, page_types = is_expense_page(text)

                if not is_expense:
                    continue

                if debug:
                    print(f"\n--- Page {page_num}: {', '.join(page_types)} page detected ---")

                table_settings = {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_tolerance": 15,
                }

                tables = page.extract_tables(table_settings)

                # Process each page type found on this page
                for page_type in page_types:
                    for table_num, table in enumerate(tables):
                        if debug:
                            print(f"\nTable {table_num + 1} on page {page_num} (parsing as {page_type}):")
                            print(f"  Rows: {len(table)}")

                        if page_type == 'detailed':
                            page_expenses = parse_detailed_expense_table(table, source_report, metadata, debug)
                        elif page_type == 'contributions':
                            page_expenses = parse_contributions_table(table, source_report, metadata, debug)
                        elif page_type == 'category':
                            page_expenses = parse_category_expense_table(table, source_report, metadata, debug)
                        else:
                            page_expenses = []

                        expenses.extend(page_expenses)

                        if debug:
                            print(f"  Extracted {len(page_expenses)} items from this table")

    except Exception as e:
        print(f"Error processing {source_report}: {str(e)}")

    # Deduplicate before returning
    expenses = deduplicate_expenses(expenses)

    return expenses


def process_all_expenses(pdfs_folder: str = "PDFs", output_csv: str = "expenses_data.csv", debug: bool = False) -> None:
    """Main function to process all PDFs and extract expense data."""
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

    all_expenses = []

    for pdf_file in latest_reports:
        try:
            expenses = extract_expenses_from_pdf(str(pdf_file), debug=debug)
            all_expenses.extend(expenses)
            print(f"[OK] {pdf_file.name}: Found {len(expenses)} item(s)")
        except Exception as e:
            print(f"[ERROR] {pdf_file.name}: {str(e)}")

    if all_expenses:
        write_expenses_to_csv(all_expenses, output_csv)
        print(f"\n{'=' * 60}")
        print(f"Extracted {len(all_expenses)} total records")
        print(f"Data exported to '{output_csv}'")
        print(f"{'=' * 60}")
    else:
        print("\nNo expense data extracted")


def write_expenses_to_csv(expenses: List[Dict], output_file: str) -> None:
    """Write expense data to CSV file."""
    fieldnames = [
        'source_report',
        'committee_name',
        'report_period',
        'expense_type',
        'payee_name',
        'payee_address',
        'payee_city_state',
        'date',
        'purpose',
        'amount',
        'payment_status'
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(expenses)


if __name__ == "__main__":
    DEBUG_MODE = False
    process_all_expenses(pdfs_folder="PDFs", output_csv="expenses_data.csv", debug=DEBUG_MODE)