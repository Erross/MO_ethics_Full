"""
Configuration for MEC Report Processing
Centralized settings for committee name and derived values
"""

import re


class Config:
    """Configuration container for MEC processing"""

    # Default committee (can be overridden)
    COMMITTEE_NAME = "Francis Howell Families"
    COMMITTEE_MECID = "C2116"  # MEC ID for search

    @classmethod
    def set_committee(cls, committee_name: str, mecid: str = None):
        """
        Set the committee to process.

        Args:
            committee_name: Full committee name
            mecid: MEC ID (optional, for targeted search)
        """
        cls.COMMITTEE_NAME = committee_name
        if mecid:
            cls.COMMITTEE_MECID = mecid

    @classmethod
    def get_file_prefix(cls) -> str:
        """
        Generate file prefix from committee name.

        Examples:
            "Francis Howell Families" → "FHF"
            "Citizens for Better Schools" → "CBS"
            "Committee to Elect John Smith" → "CTEJS"
        """
        # Extract capital letters and first letters of words
        words = cls.COMMITTEE_NAME.split()

        # Strategy 1: Use initials of each significant word
        # Skip common words like "for", "to", "the", "of"
        skip_words = {'for', 'to', 'the', 'of', 'and', 'a', 'an'}

        initials = []
        for word in words:
            if word.lower() not in skip_words:
                # Take first letter
                initials.append(word[0].upper())

        prefix = ''.join(initials)

        # If too short, just use first word
        if len(prefix) < 2:
            prefix = re.sub(r'[^A-Za-z0-9]', '', words[0])[:10].upper()

        # If too long, truncate to 10 chars
        if len(prefix) > 10:
            prefix = prefix[:10]

        return prefix

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
        Get regex pattern to match committee's report filenames.

        Returns:
            Regex pattern like "FHF_(\d{4})_Step8_(\d+)\.pdf"
        """
        prefix = cls.get_file_prefix()
        return rf"{prefix}_(\d{{4}})_Step8_(\d+)\.pdf"

    @classmethod
    def get_settings(cls) -> dict:
        """Get all current settings as dict."""
        return {
            'committee_name': cls.COMMITTEE_NAME,
            'committee_mecid': cls.COMMITTEE_MECID,
            'file_prefix': cls.get_file_prefix(),
            'filename_example': cls.get_filename_pattern(2024, '123456')
        }


# Example usage:
if __name__ == "__main__":
    # Default
    print("Default Configuration:")
    print(Config.get_settings())

    # Override
    Config.set_committee("Citizens for Better Schools", "C9999")
    print("\nOverridden Configuration:")
    print(Config.get_settings())