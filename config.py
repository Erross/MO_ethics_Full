"""
Configuration for MEC Report Processing
Centralized settings for committee name and derived values
"""

import re
from pathlib import Path


class Config:
    """Configuration container for MEC processing"""

    # Default settings
    COMMITTEE_NAME = "Francis Howell Families"
    COMMITTEE_MECID = "C2116"
    CANDIDATE_NAME = None
    SEARCH_TYPE = "committee"  # 'candidate', 'committee', or 'mecid'

    @classmethod
    def set_search(cls, committee: str = None, candidate: str = None, mecid: str = None):
        """
        Set search parameters. Determines search type automatically.

        Args:
            committee: Committee name
            candidate: Candidate name
            mecid: MEC ID
        """
        # Determine search type based on what's provided
        if mecid and not (committee or candidate):
            # MECID-only search
            cls.SEARCH_TYPE = "mecid"
            cls.COMMITTEE_MECID = mecid
            cls.COMMITTEE_NAME = None
            cls.CANDIDATE_NAME = None
        elif candidate:
            # Candidate search (mecid optional for filtering results)
            cls.SEARCH_TYPE = "candidate"
            cls.CANDIDATE_NAME = candidate
            cls.COMMITTEE_NAME = None
            # Clear MECID if not explicitly provided
            cls.COMMITTEE_MECID = mecid if mecid else None
        else:
            # Committee search (default)
            cls.SEARCH_TYPE = "committee"
            cls.COMMITTEE_NAME = committee or cls.COMMITTEE_NAME
            cls.CANDIDATE_NAME = None
            # Clear MECID if not explicitly provided
            cls.COMMITTEE_MECID = mecid if mecid else None

    @classmethod
    def set_committee(cls, committee_name: str, mecid: str = None):
        """
        Legacy method for backward compatibility.

        Args:
            committee_name: Committee name
            mecid: MEC ID (optional)
        """
        cls.set_search(committee=committee_name, mecid=mecid)

    @classmethod
    def get_search_value(cls) -> str:
        """Get the primary search value being used."""
        if cls.SEARCH_TYPE == "candidate":
            return cls.CANDIDATE_NAME
        elif cls.SEARCH_TYPE == "mecid":
            return cls.COMMITTEE_MECID
        else:
            return cls.COMMITTEE_NAME

    @classmethod
    def get_display_name(cls) -> str:
        """Get a display-friendly name for current search."""
        if cls.SEARCH_TYPE == "candidate":
            return f"Candidate: {cls.CANDIDATE_NAME}"
        elif cls.SEARCH_TYPE == "mecid":
            return f"MECID: {cls.COMMITTEE_MECID}"
        else:
            return f"Committee: {cls.COMMITTEE_NAME}"

    @classmethod
    def get_file_prefix(cls) -> str:
        """
        Generate file prefix from search target.

        Examples:
            "Francis Howell Families" → "FHF"
            "John Smith" → "JS"
            "C2116" → "C2116"
        """
        # For MECID searches, just use the MECID
        if cls.SEARCH_TYPE == "mecid":
            return cls.COMMITTEE_MECID

        # For candidate/committee, use initials
        name = cls.CANDIDATE_NAME if cls.SEARCH_TYPE == "candidate" else cls.COMMITTEE_NAME

        if not name:
            return "UNKNOWN"

        words = name.split()

        # Skip common words
        skip_words = {'for', 'to', 'the', 'of', 'and', 'a', 'an', 'elect'}

        initials = []
        for word in words:
            if word.lower() not in skip_words:
                initials.append(word[0].upper())

        prefix = ''.join(initials)

        # If too short, just use first word
        if len(prefix) < 2:
            prefix = re.sub(r'[^A-Za-z0-9]', '', words[0])[:10].upper()

        # If too long, truncate
        if len(prefix) > 10:
            prefix = prefix[:10]

        return prefix

    @classmethod
    def get_mecid_folder(cls, base_dir: str = "PDFs") -> Path:
        """
        Get the MECID-specific folder path.

        Args:
            base_dir: Base directory (default "PDFs")

        Returns:
            Path object for MECID subfolder like "PDFs/C2116"
        """
        if not cls.COMMITTEE_MECID:
            raise ValueError("COMMITTEE_MECID must be set to use MECID folders")

        return Path(base_dir) / cls.COMMITTEE_MECID

    @classmethod
    def ensure_mecid_folder(cls, base_dir: str = "PDFs") -> Path:
        """
        Create MECID folder if it doesn't exist and return path.

        Args:
            base_dir: Base directory (default "PDFs")

        Returns:
            Path object for MECID subfolder
        """
        mecid_folder = cls.get_mecid_folder(base_dir)
        mecid_folder.mkdir(parents=True, exist_ok=True)
        return mecid_folder

    @classmethod
    def get_filename_pattern(cls, year: int, report_id: str) -> str:
        """
        Generate filename for a report.

        Args:
            year: Year of the report
            report_id: MEC report ID

        Returns:
            Filename like "FHF_2024_Step8_217957.pdf"
        """
        prefix = cls.get_file_prefix()
        return f"{prefix}_{year}_Step8_{report_id}.pdf"

    @classmethod
    def get_filename_regex(cls) -> str:
        """
        Get regex pattern to match current search's report filenames.

        Returns:
            Regex pattern like "FHF_(\d{4})_Step8_(\d+)\.pdf"
        """
        prefix = cls.get_file_prefix()
        # Escape special characters in prefix (important for MECID like C2116)
        prefix_escaped = re.escape(prefix)
        return rf"{prefix_escaped}_(\d{{4}})_Step8_(\d+)\.pdf"

    @classmethod
    def get_expenses_csv_path(cls, base_dir: str = "PDFs") -> Path:
        """Get path for expenses CSV in MECID folder."""
        return cls.get_mecid_folder(base_dir) / "expenses_data.csv"

    @classmethod
    def get_donors_csv_path(cls, base_dir: str = "PDFs") -> Path:
        """Get path for donors CSV in MECID folder."""
        return cls.get_mecid_folder(base_dir) / "donors_data.csv"

    @classmethod
    def get_settings(cls) -> dict:
        """Get all current settings as dict."""
        return {
            'search_type': cls.SEARCH_TYPE,
            'committee_name': cls.COMMITTEE_NAME,
            'candidate_name': cls.CANDIDATE_NAME,
            'committee_mecid': cls.COMMITTEE_MECID,
            'file_prefix': cls.get_file_prefix(),
            'display_name': cls.get_display_name(),
            'filename_example': cls.get_filename_pattern(2024, '123456'),
            'mecid_folder': str(cls.get_mecid_folder()) if cls.COMMITTEE_MECID else None
        }


# Example usage:
if __name__ == "__main__":
    # Default (committee)
    print("Default Configuration:")
    print(Config.get_settings())

    # Show folder structure
    print(f"\nMECID Folder: {Config.get_mecid_folder()}")
    print(f"Expenses CSV: {Config.get_expenses_csv_path()}")
    print(f"Donors CSV: {Config.get_donors_csv_path()}")

    # Search by candidate
    Config.set_search(candidate="John Smith", mecid="C9999")
    print("\nCandidate Search:")
    print(Config.get_settings())
    print(f"MECID Folder: {Config.get_mecid_folder()}")

    # Search by MECID only
    Config.set_search(mecid="C1234")
    print("\nMECID Search:")
    print(Config.get_settings())
    print(f"MECID Folder: {Config.get_mecid_folder()}")