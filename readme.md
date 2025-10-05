# MEC Report Processing Pipeline

Automated system for downloading and extracting campaign finance data from Missouri Ethics Commission (MEC) reports.

## Overview

This pipeline automates the complete workflow of:
1. **Downloading** PDF reports from the MEC website
2. **Validating** report filenames match their actual filing dates
3. **Extracting** structured data on expenses and donors
4. **Exporting** to CSV for analysis

The system intelligently handles report amendments, deduplicates data, and works with any Missouri political committee.

## Features

- **Committee-Agnostic**: Process any MEC committee by name or ID
- **Smart Deduplication**: Automatically keeps only the latest version of amended reports
- **Retry Logic**: Robust download retry mechanism (up to 20 attempts)
- **Validation**: Verifies filename years match PDF filing dates
- **Captcha Avoidance**: Human-like browsing behavior to avoid detection
- **Complete Extraction**: Parses expenses, contributions, and donor data from complex PDF tables

## Installation

### Prerequisites
- Python 3.11+
- Chrome browser installed
- Virtual environment (recommended)

### Setup

```bash
# Clone repository
git clone <repository-url>
cd MEC_Reporting_Full_Project

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Requirements

```
selenium==4.15.2
webdriver-manager==4.0.1
pyautogui==0.9.54
pdfplumber==0.11.0
```

## Usage

### Quick Start (Default Committee)

Process Francis Howell Families (default):
```bash
python orchestrator.py
```

### Custom Committee

Process any committee by name:
```bash
python orchestrator.py --committee "Citizens for Better Schools" --mecid "C5678"
```

Without MEC ID (uses first search result):
```bash
python orchestrator.py --committee "Some Committee Name"
```

### Individual Scripts

Run components separately if needed:

```bash
# Download PDFs only
python download_reports.py

# Validate reports
python validate_reports.py

# Extract expenses
python expense_extractor.py

# Extract donors
python donor_extractor.py
```

## Architecture

### Pipeline Workflow

```
┌─────────────────────────────────────────────────┐
│  STEP 1: Website Discovery                      │
│  - Navigate to MEC website                      │
│  - Search for committee                         │
│  - Discover all available report years          │
│  - Extract report IDs                           │
│  - Generate expected filenames                  │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  STEP 2: Download Loop (max 20 retries)         │
│  - Compare expected vs actual files             │
│  - Download missing reports                     │
│  - Retry until complete                         │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  STEP 3: Validation                             │
│  - Check for duplicate report IDs               │
│  - Verify filename years match filing dates     │
│  - Flag mismatches                              │
└─────────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────┐
│  STEP 4: Data Extraction                        │
│  - Filter to latest report versions            │
│  - Extract expense data → expenses_data.csv     │
│  - Extract donor data → donors_data.csv         │
└─────────────────────────────────────────────────┘
```

### File Structure

```
MEC_Reporting_Full_Project/
├── config.py                 # Committee configuration
├── orchestrator.py           # Main pipeline controller
├── download_reports.py       # PDF downloader
├── validate_reports.py       # Filename validator
├── expense_extractor.py      # Expense data extractor
├── donor_extractor.py        # Donor data extractor
├── requirements.txt          # Dependencies
├── PDFs/                     # Downloaded reports (auto-created)
├── expenses_data.csv         # Extracted expense data
└── donors_data.csv           # Extracted donor data
```

### Configuration System

The `config.py` file manages committee-specific settings:

```python
from config import Config

# Default committee
Config.COMMITTEE_NAME  # "Francis Howell Families"
Config.COMMITTEE_MECID # "C2116"

# Override programmatically
Config.set_committee("New Committee", "C9999")

# Auto-generated file prefix
Config.get_file_prefix()  # "FHF" → "NC"

# Dynamic filename generation
Config.get_filename_pattern(2024, "12345")
# → "FHF_2024_Step8_12345.pdf"
```

## Output Data

### Expenses CSV (`expenses_data.csv`)

| Field | Description |
|-------|-------------|
| `source_report` | PDF filename |
| `committee_name` | Committee name |
| `report_period` | Reporting period |
| `expense_type` | Expense or Contribution |
| `payee_name` | Vendor/recipient name |
| `payee_address` | Street address |
| `payee_city_state` | City, state, ZIP |
| `date` | Transaction date |
| `purpose` | Purpose description |
| `amount` | Dollar amount |
| `payment_status` | Paid/Incurred/Category |

### Donors CSV (`donors_data.csv`)

| Field | Description |
|-------|-------------|
| `source_report` | PDF filename |
| `committee_name` | Committee name |
| `report_period` | Reporting period |
| `donor_name` | Contributor name |
| `donor_address` | Street address |
| `donor_city_state` | City, state, ZIP |
| `date_received` | Contribution date |
| `amount` | Dollar amount |
| `contribution_type` | Monetary/In-Kind |

## How It Works

### Download Process

The downloader uses Selenium to:
1. Navigate to the MEC website
2. Search for the specified committee
3. Access the Reports tab
4. Expand each year section
5. Click report links to generate PDFs
6. Save with standardized naming: `{PREFIX}_{YEAR}_Step8_{REPORT_ID}.pdf`

**Captcha Avoidance Features:**
- Random delays (2-15 seconds)
- Human-like mouse movements
- Gradual typing simulation
- Reading time simulation

### Extraction Process

**PDF Parsing Strategy:**
1. Identify page type (expenses, donors, contributions made)
2. Extract tables using `pdfplumber`
3. Parse multi-line cells (name, address, city/state)
4. Handle various amount formats ($1,234.56, 1234.56, etc.)
5. Clean and validate data

**Deduplication Logic:**
- Groups reports by committee name + period end date
- Keeps report with latest filing date
- Handles amendments automatically

### Validation Process

Only validates when duplicate report IDs exist with different years:
1. Extracts filing date from PDF content
2. Compares to year in filename
3. Flags mismatches for review

## Troubleshooting

### Chrome Driver Issues

If you get WinError 193 or driver errors:
```bash
# The "nuclear option" is already enabled - Selenium auto-manages ChromeDriver
# Ensure Chrome browser is up to date
```

### Missing Reports

If validation shows missing reports:
1. Check `PDFs/` folder contents
2. Re-run orchestrator (auto-retries up to 20 times)
3. Check MEC website for report availability

### Extraction Errors

If data extraction fails:
1. Enable debug mode in extractor scripts: `DEBUG_MODE = True`
2. Check PDF format compatibility
3. Review console output for specific errors

### Empty Reports

Some reports legitimately have 0 donors or 0 expenses:
- Termination reports
- Amendment reports with no new activity
- Off-cycle reports

This is normal and indicates extraction is working correctly.

## Development

### Adding Support for New Report Types

To add extraction for new sections:

1. Add page detection in `is_expense_page()` or `is_contributions_page()`
2. Create parsing function following pattern of existing extractors
3. Add to processing pipeline in main extraction loop

### Customizing File Naming

Modify `config.py` to change prefix generation logic:

```python
@classmethod
def get_file_prefix(cls) -> str:
    # Custom logic here
    return "CUSTOM_PREFIX"
```

## Known Limitations

- **Browser Automation**: Requires visible Chrome window for PDF downloads (pyautogui limitation)
- **Report Format**: Designed for Missouri Ethics Commission CD-2/CD-3 forms
- **PDF Variability**: Complex tables may occasionally parse incorrectly
- **Rate Limiting**: Long delays between requests to avoid captcha

## Contributing

When contributing:
1. Test with multiple committees
2. Verify both old and new report formats
3. Update validation rules if adding new fields
4. Document any new configuration options

## License

[Specify license here]

## Acknowledgments

Built for analyzing Missouri campaign finance data from the [Missouri Ethics Commission](https://mec.mo.gov/).