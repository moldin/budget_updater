#!/usr/bin/env python3
"""
Read Revolut transactions from Google Sheet to understand historical data.
"""

import logging
import pandas as pd
from datetime import datetime
from src.budget_updater.sheets_api import SheetAPI
from src.budget_updater.config import Config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def read_revolut_sheet_data():
    """Read Revolut transactions from Google Sheet Transactions tab."""
    logger.info("💳 Reading Revolut data from Google Sheet...")
    
    try:
        # Initialize Google Sheets API
        config = Config()
        sheet_api = SheetAPI()
        
        # Read all data from Transactions sheet using proper range
        logger.info("📖 Reading Transactions sheet...")
        range_name = "Transactions!A:H"  # Columns A-H (including empty first column)
        
        result = sheet_api.service.spreadsheets().values().get(
            spreadsheetId=config.spreadsheet_id,
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
        
        logger.info(f"📊 Processing {len(data_rows)} data rows...")
        
        # Filter for Revolut transactions
        revolut_transactions = []
        for i, row in enumerate(data_rows):
            # Ensure row has enough columns
            while len(row) < 8:
                row.append("")
            
            empty_col, date, outflow, inflow, category, account, memo, status = row[:8]
            
            # Filter for Revolut only
            if account == "💳 Revolut":
                revolut_transactions.append({
                    'row_number': i + header_row_index + 2,  # Sheet row number
                    'date': date,
                    'outflow': outflow,
                    'inflow': inflow,
                    'category': category,
                    'account': account,
                    'memo': memo,
                    'status': status
                })
        
        logger.info(f"💳 Found {len(revolut_transactions)} Revolut transactions")
        
        if len(revolut_transactions) == 0:
            logger.warning("No Revolut transactions found in Google Sheet")
            return None
        
        # Analyze date range
        dates = [t['date'] for t in revolut_transactions if t['date']]
        if dates:
            earliest_date = min(dates)
            latest_date = max(dates)
            logger.info(f"📅 Date range: {earliest_date} to {latest_date}")
        
        # Show sample transactions
        logger.info("📋 Sample Revolut transactions:")
        for i, transaction in enumerate(revolut_transactions[:10]):
            logger.info(f"  {transaction['date']} | OUT: {transaction['outflow']} | IN: {transaction['inflow']} | {transaction['category']} | {transaction['memo']}")
        
        # Analyze categories
        categories = {}
        for t in revolut_transactions:
            cat = t['category']
            if cat:
                categories[cat] = categories.get(cat, 0) + 1
        
        logger.info("📊 Categories found:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  {cat}: {count} transactions")
        
        return revolut_transactions
        
    except Exception as e:
        logger.error(f"❌ Failed to read Google Sheet data: {e}")
        return None

if __name__ == "__main__":
    read_revolut_sheet_data() 