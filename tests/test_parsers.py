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
    """Creates a temporary dummy SEB CSV file for testing."""
    file_path = tmp_path / "test_seb.csv"
    # Simulate typical SEB data with comma decimal, potential spaces, and header
    # Using semicolon separator as sometimes seen
    data = (
        "Bokföringsdatum;Text;Belopp\n"
        "2024-01-15;ICA KVANTUM;\"-123,45\"\n"
        "2024-01-16;LÖN FRÅN JOBBET;\"30 000,00\"\n"
        "2024-01-17;SWISH PAYMENT TO FRIEND;-500,00\n"
        "INVALID_DATE;SHOULD BE DROPPED;-10,00\n"
        "2024-01-18;RESTAURANG BESÖK; \"-456,78\" \n" # Extra spaces
        "2024-01-19;MISSING AMOUNT;\n"
        "2024-01-20;OKQ8 BENSIN; -1 234,56\n" # Leading space, space thousand sep
    )
    file_path.write_text(data.strip(), encoding='utf-8')
    return file_path

def test_parse_seb_success(seb_test_file: Path):
    """Tests successful parsing of a valid SEB file."""
    df = parse_seb(seb_test_file)
    
    assert df is not None
    assert not df.empty
    assert list(df.columns) == ['Date', 'Description', 'Amount']
    
    # Check number of rows (should drop invalid date and missing amount)
    assert len(df) == 5 
    
    # Check data types
    assert pd.api.types.is_datetime64_any_dtype(df['Date'])
    assert pd.api.types.is_numeric_dtype(df['Amount'])
    assert pd.api.types.is_string_dtype(df['Description'])
    
    # Check specific values (ensure amounts are parsed correctly)
    assert df.iloc[0]['Amount'] == -123.45
    assert df.iloc[1]['Amount'] == 30000.00
    assert df.iloc[2]['Amount'] == -500.00
    assert df.iloc[3]['Amount'] == -456.78
    assert df.iloc[4]['Amount'] == -1234.56
    
    # Check date parsing
    assert df.iloc[0]['Date'] == pd.Timestamp('2024-01-15')

def test_parse_seb_file_not_found():
    """Tests parsing when the file does not exist."""
    df = parse_seb(Path("non_existent_file.csv"))
    assert df is None

def test_parse_seb_empty_file(tmp_path: Path):
    """Tests parsing an empty file."""
    file_path = tmp_path / "empty.csv"
    file_path.touch()
    df = parse_seb(file_path)
    assert df is None # pandas read_csv raises EmptyDataError, caught by parser

def test_parse_seb_missing_columns(tmp_path: Path):
    """Tests parsing a file with missing required columns."""
    file_path = tmp_path / "missing_cols.csv"
    data = "Date;Description\n2024-01-01;Test Data"
    file_path.write_text(data, encoding='utf-8')
    df = parse_seb(file_path)
    assert df is None

# Add more tests for edge cases: different encodings, different separators if needed, etc. 