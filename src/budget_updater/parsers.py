import logging
from pathlib import Path
import pandas as pd
from typing import Optional, Dict, Callable, Any

# ---vvv--- REMOVE PARSER REGISTRY FROM HERE ---vvv---
# from .parsers import parse_seb # Ensure parse_seb is available for the registry

# # Type hint for parser functions
# ParserFunction = Callable[[Path], Optional[pd.DataFrame]]
# 
# PARSER_REGISTRY: Dict[str, ParserFunction] = {
#     'seb': parse_seb,
#     # Add other parsers here later, e.g.:
#     # 'revolut': parse_revolut,
#     # 'firstcard': parse_firstcard,
#     # 'strawberry': parse_strawberry,
# }
# ---^^^--- END REMOVE PARSER REGISTRY FROM HERE ---^^^---

logger = logging.getLogger(__name__)

def parse_seb(file_path: str | Path) -> pd.DataFrame | None:
    """
    Parses an SEB export file (xslx assumed).

    Args:
        file_path: Path to the SEB export file.

    Returns:
        A pandas DataFrame containing the relevant columns ('Date', 'Description', 'Amount') 
        or None if parsing fails.
    """
    try:
        file_path = Path(file_path) # Ensure it's a Path object
        logger.info(f"Attempting to parse SEB Excel file: {file_path}")
        
        # Use pandas read_excel for .xlsx files
        # Specify the sheet name as per PRD ('Sheet1')
        # Use openpyxl engine explicitly
        df = pd.read_excel(file_path, sheet_name='Sheet1', engine='openpyxl')
        
        logger.debug(f"Loaded dataframe from Sheet1 with columns: {df.columns.tolist()}")
        
        # --- Column Name Identification ---
        # SEB columns according to PRD: 'Bokföringsdatum', 'Text', 'Belopp'
        # We need to be robust against slight variations or encoding issues in headers
        
        date_col = None
        desc_col = None
        amount_col = None
        
        # Attempt to find columns, being flexible with potential BOM or extra spaces
        for col in df.columns:
            normalized_col = str(col).strip().replace('\ufeff', '') # Ensure col is string before stripping
            if normalized_col == 'Bokföringsdatum':
                date_col = col
            elif normalized_col == 'Text':
                desc_col = col
            elif normalized_col == 'Belopp':
                amount_col = col

        if not all([date_col, desc_col, amount_col]):
            missing = []
            if not date_col: missing.append('Bokföringsdatum')
            if not desc_col: missing.append('Text')
            if not amount_col: missing.append('Belopp')
            logger.error(f"Could not find required columns in {file_path}, Sheet1. Missing: {missing}. Found columns: {df.columns.tolist()}")
            return None
            
        logger.info(f"Found required columns: Date='{date_col}', Description='{desc_col}', Amount='{amount_col}'")

        # --- Data Extraction and Basic Cleaning ---
        # Select and rename columns for consistency
        parsed_df = df[[date_col, desc_col, amount_col]].copy()
        parsed_df.rename(columns={
            date_col: 'ParsedDate',
            desc_col: 'ParsedDescription',
            amount_col: 'ParsedAmount'
        }, inplace=True)

        # --- Type Conversion and Validation ---
        # Convert Date column to datetime objects (YYYY-MM-DD format assumed)
        try:
            parsed_df['ParsedDate'] = pd.to_datetime(parsed_df['ParsedDate'], errors='coerce')
            if parsed_df['ParsedDate'].isnull().any():
                null_dates_count = parsed_df['ParsedDate'].isnull().sum()
                logger.warning(f"{null_dates_count} date(s) could not be parsed in {file_path}. Review file format. These rows will be dropped.")
        except Exception as e:
            logger.error(f"Error converting Date column to datetime in {file_path}: {e}")
            return None

        # Convert Amount column to numeric, handling potential thousand separators (like spaces) and decimal commas
        try:
            parsed_df['ParsedAmount'] = parsed_df['ParsedAmount'].astype(str).str.replace(r'[\s\xa0]+', '', regex=True).str.replace(',', '.', regex=False)
            parsed_df['ParsedAmount'] = pd.to_numeric(parsed_df['ParsedAmount'], errors='coerce')
            if parsed_df['ParsedAmount'].isnull().any():
                null_amounts_count = parsed_df['ParsedAmount'].isnull().sum()
                logger.warning(f"{null_amounts_count} amount(s) could not be parsed to numeric in {file_path}. Review file format. These rows will be dropped.")
        except Exception as e:
            logger.error(f"Error converting Amount column to numeric in {file_path}: {e}")
            return None
            
        # Ensure Description is string and handle potential NaN values if any rows had only NaN description
        parsed_df['ParsedDescription'] = parsed_df['ParsedDescription'].fillna('').astype(str)

        # Drop rows where essential data might be missing after conversion (Date or Amount)
        original_count = len(parsed_df)
        parsed_df.dropna(subset=['ParsedDate', 'ParsedAmount'], inplace=True)
        dropped_count = original_count - len(parsed_df)
        if dropped_count > 0:
             logger.info(f"Dropped {dropped_count} rows due to parsing errors (Date or Amount).")

        logger.info(f"Successfully parsed {len(parsed_df)} transactions from {file_path}")
        return parsed_df

    except FileNotFoundError:
        logger.error(f"SEB Parser: File not found at {file_path}")
        return None
    # Catch specific error if sheet name is wrong
    except ValueError as e:
        if "Worksheet named 'Sheet1' not found" in str(e):
            logger.error(f"SEB Parser: Worksheet named 'Sheet1' not found in {file_path}. Please ensure the sheet name is correct.")
        else:
             logger.exception(f"SEB Parser: An unexpected ValueError occurred while parsing {file_path}: {e}")
        return None
    # Catch potential openpyxl/excel format errors
    except Exception as e:
        # Check for common excel-related errors if possible (e.g. BadZipFile)
        if "zip file" in str(e).lower(): # Example check
             logger.error(f"SEB Parser: File {file_path} might be corrupted or not a valid Excel file. Error: {e}")
        else:
             logger.exception(f"SEB Parser: An unexpected error occurred while parsing {file_path}: {e}")
        return None

# ---vvv--- ADD PARSER REGISTRY HERE (AT THE END) ---vvv---
# Type hint for parser functions
ParserFunction = Callable[[Path], Optional[pd.DataFrame]]

PARSER_REGISTRY: Dict[str, ParserFunction] = {
    'seb': parse_seb,
    # Add other parsers here as they are defined, e.g.:
    # 'revolut': parse_revolut,
    # 'firstcard': parse_firstcard,
    # 'strawberry': parse_strawberry,
}
# ---^^^--- END ADD PARSER REGISTRY HERE ---^^^---

# Example usage (for testing purposes):
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO)
#     # Create a dummy SEB CSV file for testing
#     dummy_data = {
#         'Bokföringsdatum': ['2023-01-15', '2023-01-16', 'Invalid Date', '2023-01-17'],
#         'Text': ['ICA SUPERMARKET', 'SWISH PAYMENT RECEIVED', 'Test', 'ATM WITHDRAWAL'],
#         'Belopp': ['-125,50', '500,00', '100,00', '-1 000,00'] # Note comma decimal and space thousand sep
#     }
#     dummy_path = Path('dummy_seb.csv')
#     pd.DataFrame(dummy_data).to_csv(dummy_path, index=False, encoding='utf-8', sep=';') # Use semicolon for dummy
# 
#     parsed = parse_seb(dummy_path)
#     if parsed is not None:
#         print("Parsed SEB Data:")
#         print(parsed)
#         print(parsed.dtypes)
# 
#     # Clean up dummy file
#     # dummy_path.unlink() 