import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from . import config # Import config

logger = logging.getLogger(__name__)

# Constants now defined in config
# TARGET_COLUMNS = config.TARGET_COLUMNS
# PLACEHOLDER_CATEGORY = config.PLACEHOLDER_CATEGORY
# DEFAULT_STATUS = config.DEFAULT_STATUS

def format_currency(value: float) -> str:
    """Formats a float to a string with comma decimal separator, empty for zero."""
    if pd.isna(value) or value == 0:
        return ''
    # Format to 2 decimal places, replace dot with comma
    return f"{value:.2f}".replace('.', ',')

def transform_transactions(parsed_df: Optional[pd.DataFrame], account_name: str) -> List[Dict[str, Any]]:
    """
    Transforms parsed transaction data into the structure required by the Google Sheet.

    Args:
        parsed_df: DataFrame with columns 'Date', 'Description', 'Amount'.
                   Assumes Date is datetime, Description is string, Amount is numeric.
        account_name: The target account name for the 'Account' column.

    Returns:
        A list of dictionaries, where each dictionary represents a transaction row
        ready for upload, or an empty list if input is invalid or empty.
    """
    if parsed_df is None or parsed_df.empty:
        logger.warning("Transformation skipped: Input DataFrame is None or empty.")
        return [] # Return empty list

    # Verify necessary columns exist (using standardized names)
    required_cols = ['ParsedDate', 'ParsedDescription', 'ParsedAmount']
    if not all(col in parsed_df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in parsed_df.columns]
        logger.error(f"Transformation failed: Missing expected column(s) in parsed data: {missing}")
        return [] # Return empty list

    transformed_data = []
    for _, row in parsed_df.iterrows():
        try:
            amount = row['ParsedAmount']
            outflow = amount * -1 if amount < 0 else 0.0
            inflow = amount if amount >= 0 else 0.0 # Includes 0 as inflow initially

            # Handle potential NaN in Description - already handled by parser, but keep check
            memo = str(row['ParsedDescription']) if pd.notna(row['ParsedDescription']) else ''

            transaction_dict = {
                'Date': row['ParsedDate'].strftime('%Y-%m-%d'), # Format date as YYYY-MM-DD string
                'Outflow': format_currency(outflow),
                'Inflow': format_currency(inflow),
                'Category': config.PLACEHOLDER_CATEGORY, # Use config constant
                'Account': account_name,
                'Memo': memo,
                'Status': config.DEFAULT_STATUS # Use config constant
            }
            transformed_data.append(transaction_dict)

        except Exception as e:
            logger.error(f"Error transforming row: {row}. Error: {e}", exc_info=True)
            # Optionally skip the row or handle differently
            continue # Skip rows that cause errors during transformation

    logger.info(f"Successfully transformed {len(transformed_data)} rows into list of dicts.")
    return transformed_data

# Example usage (requires a parsed DataFrame):
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO)
#     # Assume parse_seb() was run and returned a df called 'parsed_seb_data'
#     # Example parsed data:
#     example_data = {
#         'Date': pd.to_datetime(['2023-01-15', '2023-01-16', '2023-01-17']),
#         'Description': ['ICA SUPERMARKET', 'SWISH PAYMENT RECEIVED', 'ATM WITHDRAWAL'],
#         'Amount': [-125.50, 500.00, -1000.00]
#     }
#     parsed_seb_data = pd.DataFrame(example_data)
# 
#     account = '💰 SEB' # Example validated account name
#     transformed = transform_transactions(parsed_seb_data, account)
# 
#     if transformed is not None:
#         print("\nTransformed Data:")
#         print(transformed)
#         print(transformed.dtypes) 