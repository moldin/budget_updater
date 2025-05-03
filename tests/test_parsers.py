import sys
import os
import pandas as pd
from pathlib import Path
import pytest
import logging

# Add src directory to sys.path to allow importing budget_updater
# This assumes tests are run from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from budget_updater.parsers import parse_seb

# Configure logging for tests (optional, but can be helpful)
# logging.basicConfig(level=logging.DEBUG)

@pytest.fixture
def seb_test_file(tmp_path: Path) -> Path:
    """Creates a dummy SEB Excel file for testing."""
    # Use consistent column names as expected by the parser
    data = {
        "Bokföringsdatum": ["2024-01-15", "2024-01-16", pd.NaT, "2024-01-18"],
        "Text": ["Expense 1", "Income 1", "Missing Date", "Expense 2"],
        "Belopp": [-100.50, 2000.00, -50.0, pd.NA] # Use pd.NA for missing amount
    }
    df = pd.DataFrame(data)
    # Create an .xlsx file instead of .csv
    file_path = tmp_path / "test_seb.xlsx"
    # Write to 'Sheet1' as expected by the parser
    df.to_excel(file_path, index=False, sheet_name='Sheet1')
    return file_path

def test_parse_seb_success(seb_test_file: Path):
    """Tests successful parsing of a valid SEB file."""
    df = parse_seb(seb_test_file)

    assert df is not None
    # Previous logic dropped rows with NaT dates or NaN amounts
    # Assert based on the rows expected AFTER cleaning
    assert len(df) == 2 # Rows with NaT date and NaN amount should be dropped
    assert list(df.columns) == ["Date", "Description", "Amount"] # Check renamed columns
    # Check dtypes after parsing and cleaning
    assert pd.api.types.is_datetime64_any_dtype(df['Date'])
    assert pd.api.types.is_object_dtype(df['Description']) # String type
    assert pd.api.types.is_numeric_dtype(df['Amount'])

def test_parse_seb_file_not_excel(tmp_path: Path):
    """Tests handling of a file that is not a valid Excel file."""
    file_path = tmp_path / "not_excel.txt"
    file_path.write_text("This is not an excel file")
    df = parse_seb(file_path)
    assert df is None # Expecting None for non-Excel files

@pytest.fixture
def seb_missing_cols_file(tmp_path: Path) -> Path:
    """Creates a dummy SEB Excel file missing the 'Belopp' column."""
    data = {
        "Bokföringsdatum": ["2024-01-15", "2024-01-16"],
        "Text": ["Expense 1", "Income 1"]
        # Missing "Belopp" column
    }
    df = pd.DataFrame(data)
    file_path = tmp_path / "test_seb_missing_cols.xlsx"
    df.to_excel(file_path, index=False, sheet_name='Sheet1')
    return file_path

def test_parse_seb_missing_columns(seb_missing_cols_file: Path):
    """Tests handling of a file missing required columns."""
    df = parse_seb(seb_missing_cols_file)
    assert df is None # Expecting None when required columns are missing

@pytest.fixture
def seb_empty_file(tmp_path: Path) -> Path:
    """Creates an empty SEB Excel file (only headers)."""
    data = {
        "Bokföringsdatum": [],
        "Text": [],
        "Belopp": []
    }
    df = pd.DataFrame(data)
    file_path = tmp_path / "test_seb_empty.xlsx"
    df.to_excel(file_path, index=False, sheet_name='Sheet1')
    return file_path

def test_parse_seb_empty_file(seb_empty_file: Path):
    """Tests handling of an empty file."""
    df = parse_seb(seb_empty_file)
    assert df is not None
    assert df.empty # Expecting an empty DataFrame

# Add more tests for edge cases: different encodings, different separators if needed, etc. 