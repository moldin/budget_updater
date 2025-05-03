import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Define the target column order for the Google Sheet
TARGET_COLUMNS = ['Date', 'Outflow', 'Inflow', 'Category', 'Account', 'Memo', 'Status']
PLACEHOLDER_CATEGORY = "PENDING_AI" # Placeholder until AI categorization is implemented
DEFAULT_STATUS = "✅"

def transform_transactions(parsed_df: pd.DataFrame, account_name: str) -> pd.DataFrame | None:
    """
    Transforms parsed transaction data into the target Google Sheet format.

    Args:
        parsed_df: DataFrame with columns ['Date', 'Description', 'Amount'].
                     Assumes 'Date' is datetime and 'Amount' is numeric.
        account_name: The validated account name to assign to transactions.

    Returns:
        A DataFrame with columns matching TARGET_COLUMNS, ready for upload, 
        or None if transformation fails.
    """
    if parsed_df is None or parsed_df.empty:
        logger.warning("Transformation skipped: Input DataFrame is None or empty.")
        return pd.DataFrame(columns=TARGET_COLUMNS) # Return empty dataframe with correct columns

    try:
        logger.info(f"Starting transformation for {len(parsed_df)} transactions for account '{account_name}'")
        transformed_data = []

        for index, row in parsed_df.iterrows():
            date_str = row['Date'].strftime('%Y-%m-%d')
            amount = row['Amount']
            description = row['Description']

            outflow = 0.0
            inflow = 0.0

            # SEB Logic: Negative amount is outflow, positive is inflow
            if amount < 0:
                outflow = abs(amount)
            else:
                inflow = amount
                
            # TODO: Add logic for other bank types (First Card, Strawberry) in later iterations
            # where positive amounts might mean outflow.
            
            transformed_row = {
                'Date': date_str,
                'Outflow': outflow,
                'Inflow': inflow,
                'Category': PLACEHOLDER_CATEGORY,
                'Account': account_name, # Use the validated name passed in
                'Memo': description,
                'Status': DEFAULT_STATUS
            }
            transformed_data.append(transformed_row)

        transformed_df = pd.DataFrame(transformed_data)
        
        # Reorder columns to match the target sheet exactly
        transformed_df = transformed_df[TARGET_COLUMNS]
        
        # Convert numeric columns to float, handling potential NaNs
        # Although we calculate outflow/inflow, ensure they are float
        transformed_df['Outflow'] = pd.to_numeric(transformed_df['Outflow'], errors='coerce').fillna(0.0)
        transformed_df['Inflow'] = pd.to_numeric(transformed_df['Inflow'], errors='coerce').fillna(0.0)

        # Optional: Format numeric columns for display (e.g., 2 decimal places)
        # This might be better handled by Google Sheets formatting itself.
        # transformed_df['Outflow'] = transformed_df['Outflow'].round(2)
        # transformed_df['Inflow'] = transformed_df['Inflow'].round(2)

        logger.info(f"Successfully transformed {len(transformed_df)} transactions.")
        return transformed_df

    except KeyError as e:
        logger.error(f"Transformation failed: Missing expected column in parsed data: {e}")
        return None
    except Exception as e:
        logger.exception(f"Transformation failed: An unexpected error occurred: {e}")
        return None

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