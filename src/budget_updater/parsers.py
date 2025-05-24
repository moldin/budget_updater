import logging
from pathlib import Path
import pandas as pd
from typing import Optional, Dict, Callable, Any, List

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

def parse_excel_generic(
    file_path: str | Path,
    *,
    engine: str = None,
    sheet_name: str = None,
    column_map: Dict[str, List[str]],
    date_type: str = 'string',  # 'string' or 'excel_serial'
    date_origin: str = '1899-12-30',
    required_columns: List[str] = None,
) -> pd.DataFrame | None:
    """
    Generic Excel parser for bank/card exports.
    Args:
        file_path: Path to the Excel file.
        engine: pandas read_excel engine (optional)
        sheet_name: Sheet name (optional)
        column_map: Dict mapping logical names ('date', 'desc', 'amount') to possible Excel column names
        date_type: 'string' for normal date parsing, 'excel_serial' for Excel serial dates
        date_origin: Origin for Excel serial dates
        required_columns: List of logical names that must be present (default: ['date', 'desc', 'amount'])
    Returns:
        DataFrame with columns: ParsedDate, ParsedDescription, ParsedAmount, or None on error.
    """
    try:
        file_path = Path(file_path)
        logger.info(f"Parsing Excel file: {file_path}")
        read_excel_kwargs = {}
        if engine:
            read_excel_kwargs['engine'] = engine
        if sheet_name:
            read_excel_kwargs['sheet_name'] = sheet_name
        try:
            df = pd.read_excel(file_path, **read_excel_kwargs)
        except Exception as e:
            logger.error(f"read_excel failed for {file_path} with args {read_excel_kwargs}: {e}")
            return None
        logger.debug(f"Loaded dataframe with columns: {df.columns.tolist()}")
        # Find columns
        found_cols = {}
        for logical, possible_names in column_map.items():
            for col in df.columns:
                normalized_col = str(col).strip().replace('\ufeff', '').lower()
                for name in possible_names:
                    if normalized_col == name.lower():
                        found_cols[logical] = col
                        break
                if logical in found_cols:
                    break
        # Fallback for description: substring match if not found
        if 'desc' in column_map and 'desc' not in found_cols:
            for col in df.columns:
                normalized_col = str(col).strip().lower()
                if any(part in normalized_col for part in ['desc', 'spec', 'text', 'reseinformation', 'inköpsplats']):
                    found_cols['desc'] = col
                    logger.info(f"Found description column '{col}' using substring match.")
                    break
        # Check required columns
        req = required_columns or ['date', 'desc', 'amount']
        missing = [logical for logical in req if logical not in found_cols]
        if missing:
            logger.error(f"Could not find required columns in {file_path}. Missing: {missing}. Found: {found_cols}")
            return None
        # Select and rename
        parsed_df = df[[found_cols['date'], found_cols['desc'], found_cols['amount']]].copy()
        parsed_df.rename(columns={
            found_cols['date']: 'ParsedDate',
            found_cols['desc']: 'ParsedDescription',
            found_cols['amount']: 'ParsedAmount',
        }, inplace=True)
        # Date conversion
        try:
            if date_type == 'excel_serial':
                parsed_df['ParsedDate'] = pd.to_datetime(parsed_df['ParsedDate'], unit='D', origin=date_origin, errors='coerce')
            else:
                parsed_df['ParsedDate'] = pd.to_datetime(parsed_df['ParsedDate'], errors='coerce')
            if parsed_df['ParsedDate'].isnull().any():
                logger.warning(f"{parsed_df['ParsedDate'].isnull().sum()} date(s) could not be parsed in {file_path}.")
        except Exception as e:
            logger.error(f"Error converting Date column in {file_path}: {e}")
            return None
        # Amount conversion
        try:
            parsed_df['ParsedAmount'] = parsed_df['ParsedAmount'].astype(str).str.replace(r'[\s\xa0]+', '', regex=True).str.replace(',', '.', regex=False)
            parsed_df['ParsedAmount'] = pd.to_numeric(parsed_df['ParsedAmount'], errors='coerce')
            if parsed_df['ParsedAmount'].isnull().any():
                logger.warning(f"{parsed_df['ParsedAmount'].isnull().sum()} amount(s) could not be parsed to numeric in {file_path}.")
        except Exception as e:
            logger.error(f"Error converting Amount column to numeric in {file_path}: {e}")
            return None
        parsed_df['ParsedDescription'] = parsed_df['ParsedDescription'].fillna('').astype(str)
        # Drop rows with missing essentials
        original_count = len(parsed_df)
        parsed_df.dropna(subset=['ParsedDate', 'ParsedAmount'], inplace=True)
        dropped_count = original_count - len(parsed_df)
        if dropped_count > 0:
            logger.info(f"Dropped {dropped_count} rows due to parsing errors (Date or Amount).")
        logger.info(f"Successfully parsed {len(parsed_df)} transactions from {file_path}")
        return parsed_df
    except FileNotFoundError:
        logger.error(f"File not found at {file_path}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error while parsing {file_path}: {e}")
        return None

def parse_seb(file_path: str | Path) -> pd.DataFrame | None:
    return parse_excel_generic(
        file_path,
        engine='openpyxl',
        sheet_name='Sheet1',
        column_map={
            'date': ['Bokföringsdatum'],
            'desc': ['Text'],
            'amount': ['Belopp'],
        },
        date_type='string',
    )

def parse_strawberry(file_path: str | Path) -> pd.DataFrame | None:
    return parse_excel_generic(
        file_path,
        engine=None,  # Let pandas/xlrd decide
        column_map={
            'date': ['Bokfört'],
            'desc': ['Specifikation'],
            'amount': ['Belopp'],
        },
        date_type='excel_serial',
        date_origin='1899-12-30',
    )

def parse_firstcard(file_path: str | Path) -> pd.DataFrame | None:
    return parse_excel_generic(
        file_path,
        engine=None,  # Let pandas decide
        column_map={
            'date': ['Datum'],
            'desc': ['Reseinformation / Inköpsplats', 'Reseinformation/Inköpsplats'],
            'amount': ['Belopp'],
        },
        date_type='string',
    )

def parse_revolut(file_path: str | Path) -> pd.DataFrame | None:
    """
    Parses a Revolut export file (.xlsx assumed).
    Expected columns: 'Completed Date', 'Description', 'Amount', 'Fee'.
    Date format: YYYY-MM-DD HH:MM:SS (extract date part).
    Fee should be added to OUTFLOW if present and non-zero.
    """
    try:
        # First, get the basic parsed data using the generic parser
        parsed_df = parse_excel_generic(
            file_path,
            engine='openpyxl',
            column_map={
                'date': ['Completed Date'],
                'desc': ['Description'],
                'amount': ['Amount'],
            },
            date_type='string',
            required_columns=['date', 'desc', 'amount']
        )
        
        if parsed_df is None:
            return None
            
        # Now we need to handle the Fee column separately since it's not in the basic mapping
        file_path = Path(file_path)
        logger.info(f"Processing Revolut-specific Fee column for {file_path}")
        
        # Re-read the file to get the Fee column
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # Find the Fee column
        fee_col = None
        for col in df.columns:
            normalized_col = str(col).strip().replace('\ufeff', '').lower()
            if normalized_col == 'fee':
                fee_col = col
                break
                
        if fee_col is not None:
            # Add fee to the parsed dataframe
            parsed_df['Fee'] = df[fee_col].fillna(0)
            
            # Convert Fee to numeric
            try:
                parsed_df['Fee'] = pd.to_numeric(parsed_df['Fee'], errors='coerce').fillna(0)
            except Exception as e:
                logger.warning(f"Could not convert Fee column to numeric in {file_path}: {e}. Setting fees to 0.")
                parsed_df['Fee'] = 0
                
            # Add fee to amount for outflows (fees are always additional costs)
            # Fees should be subtracted from the amount (made more negative for outflows)
            fee_adjustment = parsed_df['Fee']
            parsed_df['ParsedAmount'] = parsed_df['ParsedAmount'] - fee_adjustment
            
            # Log fee processing
            total_fees = parsed_df['Fee'].sum()
            if total_fees > 0:
                logger.info(f"Applied {total_fees} total fees to transactions in {file_path}")
                
        else:
            logger.warning(f"Fee column not found in {file_path}")
            
        # Drop the temporary Fee column as we've incorporated it into ParsedAmount
        if 'Fee' in parsed_df.columns:
            parsed_df.drop('Fee', axis=1, inplace=True)
            
        return parsed_df
        
    except Exception as e:
        logger.exception(f"Revolut Parser: An unexpected error occurred while parsing {file_path}: {e}")
        return None

# ---vvv--- ADD PARSER REGISTRY HERE (AT THE END) ---vvv---
# Type hint for parser functions
ParserFunction = Callable[[Path | str], Optional[pd.DataFrame]]

PARSER_REGISTRY: Dict[str, ParserFunction] = {
    'seb': parse_seb,
    'strawberry': parse_strawberry,
    'revolut': parse_revolut,
    'firstcard': parse_firstcard,
}
# ---^^^--- END ADD PARSER REGISTRY HERE ---^^^---
