#!/usr/bin/env python3
"""
Read Strawberry transactions from Google Sheet to understand historical data.
"""

import logging
import pandas as pd
from datetime import datetime
from src.budget_updater.sheets_api import SheetAPI
from src.budget_updater import config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def read_strawberry_sheet_data():
    """Read Strawberry transactions from Google Sheet Transactions tab."""
    logger.info("🍓 Reading Strawberry data from Google Sheet...")
    
    try:
        # Initialize Google Sheets API
        sheet_api = SheetAPI()
        
        # Read all data from Transactions sheet using proper range
        logger.info("📖 Reading Transactions sheet...")
        range_name = "Transactions!A:H"  # Columns A-H (including empty first column)
        
        result = sheet_api.service.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        sheet_data = result.get('values', [])
        
        if not sheet_data:
            logger.error("❌ No data found in Google Sheet")
            return None
            
        logger.info(f"📋 Found {len(sheet_data)} total rows in Google Sheet")
        
        # Find the header row (should be row with 'DATE' in column B)
        header_row_index = None
        for i, row in enumerate(sheet_data):
            if len(row) > 1 and row[1] == 'DATE':  # Column B should be 'DATE'
                header_row_index = i
                logger.info(f"Found header at row {i+1}: {row}")
                break
        
        if header_row_index is None:
            logger.error("Could not find header row with 'DATE' in column B")
            return None
        
        # Get headers and data rows
        headers = sheet_data[header_row_index]
        data_rows = sheet_data[header_row_index + 1:]
        
        logger.info(f"📊 Headers: {headers}")
        logger.info(f"📊 Data rows: {len(data_rows)}")
        
        # Ensure all rows have the same number of columns as headers
        max_cols = len(headers)
        normalized_rows = []
        for row in data_rows:
            # Pad row with empty strings if it's shorter than headers
            normalized_row = row + [''] * (max_cols - len(row))
            # Truncate if longer than headers
            normalized_row = normalized_row[:max_cols]
            normalized_rows.append(normalized_row)
        
        df = pd.DataFrame(normalized_rows, columns=headers)
        logger.info(f"📋 Total rows in sheet: {len(df)}")
        
        # Filter for Strawberry transactions
        # Column structure: ['', 'DATE', 'OUTFLOW', 'INFLOW', 'CATEGORY', 'ACCOUNT', 'MEMO', 'STATUS']
        account_col = 'ACCOUNT' if 'ACCOUNT' in df.columns else headers[5] if len(headers) > 5 else None
        if account_col is None:
            logger.error("❌ Could not find ACCOUNT column")
            return None
            
        # Debug: Show unique accounts
        unique_accounts = df[account_col].unique()
        logger.info(f"📊 Unique accounts found: {unique_accounts}")
        
        strawberry_df = df[df[account_col] == '💳 Strawberry'].copy()
        logger.info(f"🍓 Strawberry transactions found: {len(strawberry_df)}")
        
        if len(strawberry_df) == 0:
            # Try alternative account names
            strawberry_alternatives = ['🍓 Strawberry', 'Strawberry', '🍓Strawberry', 'strawberry', '🍓 strawberry']
            for alt_name in strawberry_alternatives:
                alt_df = df[df[account_col] == alt_name].copy()
                if len(alt_df) > 0:
                    logger.info(f"Found {len(alt_df)} transactions with account name: '{alt_name}'")
                    strawberry_df = alt_df
                    break
            
            if len(strawberry_df) == 0:
                logger.warning("⚠️ No Strawberry transactions found with any variant")
                return None
            
        # Convert Date column to datetime for analysis
        date_col = 'DATE' if 'DATE' in df.columns else headers[1] if len(headers) > 1 else None
        if date_col is None:
            logger.error("❌ Could not find DATE column")
            return None
            
        strawberry_df['Date_parsed'] = pd.to_datetime(strawberry_df[date_col], errors='coerce')
        
        # Remove rows with invalid dates
        valid_dates = strawberry_df['Date_parsed'].notna()
        strawberry_df = strawberry_df[valid_dates].copy()
        
        logger.info(f"📅 Valid date transactions: {len(strawberry_df)}")
        
        if len(strawberry_df) > 0:
            earliest = strawberry_df['Date_parsed'].min()
            latest = strawberry_df['Date_parsed'].max()
            logger.info(f"📅 Date range: {earliest.date()} to {latest.date()}")
            
            # Show sample data
            logger.info("📋 Sample Strawberry transactions:")
            sample_cols = [date_col, 'OUTFLOW', 'INFLOW', 'CATEGORY', 'MEMO']
            available_cols = [col for col in sample_cols if col in strawberry_df.columns]
            print(strawberry_df[available_cols].head(10).to_string(index=False))
            
            # Show column structure
            logger.info(f"📊 Columns in sheet: {list(strawberry_df.columns)}")
            
            # Analyze amount patterns
            logger.info("\n💰 Amount analysis:")
            outflow_count = strawberry_df['OUTFLOW'].notna().sum() if 'OUTFLOW' in strawberry_df.columns else 0
            inflow_count = strawberry_df['INFLOW'].notna().sum() if 'INFLOW' in strawberry_df.columns else 0
            logger.info(f"Outflow entries: {outflow_count}")
            logger.info(f"Inflow entries: {inflow_count}")
            
            return strawberry_df
        else:
            logger.warning("⚠️ No valid transactions after date parsing")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error reading Google Sheet: {e}")
        return None

if __name__ == "__main__":
    df = read_strawberry_sheet_data()
    if df is not None:
        logger.info(f"✅ Successfully read {len(df)} Strawberry transactions")
    else:
        logger.error("❌ Failed to read Strawberry data") 