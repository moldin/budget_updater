#!/usr/bin/env python3
"""
Create merged Revolut file combining Excel data with Google Sheet historical data.

This script:
1. Reads recent Revolut data from revolut_init.xlsx (2022-01-03 onwards)
2. Reads historical Revolut data from Google Sheet (2021-10-11 to 2022-01-02)
3. Reverse engineers Google Sheet data to Revolut Excel format
4. Merges both datasets into revolut_all_merged.xlsx

Mapping rules from Google Sheet to Revolut Excel format:
- DATE -> Started Date AND Completed Date (with 0:00 time)
- OUTFLOW -> Amount (negative, 300 -> -300)
- INFLOW -> Amount (positive)
- CATEGORY: MEMO -> Description

Additional column rules:
- Type -> CARD_PAYMENT (if OUTFLOW has data)
- Type -> TOPUP (if INFLOW has data AND Category is '↕️ Account Transfer')
- Type -> FEE (if Category is 'Bankavgifter')
- Type -> REFUND (if INFLOW has data and Category is not '↕️ Account Transfer')
- Product -> Current
- Fee -> 0.00
- Currency -> SEK
- State -> COMPLETED
- Balance -> empty
"""

import logging
import pandas as pd
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
import sys

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent / "src"))

from budget_updater.sheets_api import SheetAPI
from budget_updater.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class RevolutMerger:
    """Merge Revolut Excel data with Google Sheet historical data in Excel format."""
    
    def __init__(self):
        self.config = Config()
        self.sheets_api = SheetAPI()
        self.data_dir = Path("data")
        self.excel_file = self.data_dir / "revolut_init.xlsx"
        self.merged_file = self.data_dir / "revolut_all_merged.xlsx"
        
    def read_excel_data(self) -> pd.DataFrame:
        """Read recent Revolut data from Excel file."""
        logger.info(f"📖 Reading Excel data from {self.excel_file}")
        
        try:
            df = pd.read_excel(self.excel_file, engine='openpyxl')
            logger.info(f"✅ Read {len(df)} rows from Excel file")
            
            # Show date range
            if 'Completed Date' in df.columns:
                dates = pd.to_datetime(df['Completed Date'], errors='coerce')
                logger.info(f"📅 Excel date range: {dates.min()} to {dates.max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Failed to read Excel file: {e}")
            raise
    
    def read_google_sheet_revolut(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Read Revolut transactions from Google Sheet for specified date range."""
        logger.info(f"📖 Reading Revolut data from Google Sheet ({start_date} to {end_date})")
        
        try:
            # Read all data from Transactions sheet
            range_name = "Transactions!A:H"  # Columns A-H (including empty first column)
            
            result = self.sheets_api.service.spreadsheets().values().get(
                spreadsheetId=self.config.spreadsheet_id,
                range=range_name
            ).execute()
            
            sheet_data = result.get('values', [])
            
            if not sheet_data:
                logger.error("❌ No data found in Google Sheet")
                return pd.DataFrame()
            
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
                return pd.DataFrame()
            
            # Get headers and data rows
            headers = sheet_data[header_row_index]
            data_rows = sheet_data[header_row_index + 1:]
            
            # Normalize data rows to have same number of columns as headers
            max_cols = len(headers)
            normalized_rows = []
            
            for row in data_rows:
                # Pad row with empty strings if it's shorter than headers
                normalized_row = row + [''] * (max_cols - len(row))
                # Truncate if longer than headers
                normalized_row = normalized_row[:max_cols]
                normalized_rows.append(normalized_row)
            
            df = pd.DataFrame(normalized_rows, columns=headers)
            logger.info(f"✅ Read {len(df)} total rows from Google Sheet")
            
            # Filter for Revolut transactions
            revolut_df = df[df['ACCOUNT'] == '💳 Revolut'].copy()
            logger.info(f"💳 Revolut transactions found: {len(revolut_df)}")
            
            if len(revolut_df) == 0:
                logger.warning("No Revolut transactions found in Google Sheet")
                return pd.DataFrame()
            
            # Convert Date column to datetime and filter by date range
            revolut_df['Date_parsed'] = pd.to_datetime(revolut_df['DATE'], errors='coerce')
            valid_dates = revolut_df['Date_parsed'].notna()
            revolut_df = revolut_df[valid_dates].copy()
            
            # Filter by date range
            start_dt = pd.to_datetime(start_date).date()
            end_dt = pd.to_datetime(end_date).date()
            
            date_mask = (revolut_df['Date_parsed'].dt.date >= start_dt) & (revolut_df['Date_parsed'].dt.date <= end_dt)
            filtered_df = revolut_df[date_mask].copy()
            
            logger.info(f"📅 Filtered to date range {start_date} to {end_date}: {len(filtered_df)} transactions")
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"Failed to read Google Sheet data: {e}")
            raise
    
    def clean_swedish_amount(self, amount_str: str) -> float:
        """Convert Swedish amount format '1 234,56 kr' to float 1234.56"""
        if not amount_str or pd.isna(amount_str):
            return 0.0
        
        # Remove 'kr' suffix and various whitespace characters
        amount_clean = str(amount_str).replace(' kr', '').replace('kr', '')
        amount_clean = amount_clean.replace(' ', '').replace('\xa0', '')  # Remove regular and non-breaking spaces
        
        # Replace comma with period for decimal separator
        amount_clean = amount_clean.replace(',', '.')
        
        try:
            return float(amount_clean)
        except ValueError:
            logger.warning(f"Could not parse amount: '{amount_str}' -> '{amount_clean}'")
            return 0.0
    
    def determine_transaction_type(self, outflow: str, inflow: str, category: str) -> str:
        """Determine Revolut transaction type based on Google Sheet data."""
        # Clean category
        category = str(category).strip()
        
        # Check if we have outflow or inflow
        has_outflow = outflow and str(outflow).strip()
        has_inflow = inflow and str(inflow).strip()
        
        if has_outflow:
            # OUTFLOW -> CARD_PAYMENT
            return "CARD_PAYMENT"
        elif has_inflow:
            if category == "↕️ Account Transfer":
                # INFLOW + Account Transfer -> TOPUP
                return "TOPUP"
            elif category == "Bankavgifter":
                # Bankavgifter -> FEE
                return "FEE"
            else:
                # Other INFLOW -> REFUND
                return "REFUND"
        else:
            # Default fallback
            return "CARD_PAYMENT"
    
    def reverse_engineer_to_excel_format(self, sheet_df: pd.DataFrame) -> pd.DataFrame:
        """Convert Google Sheet Revolut data to Excel format."""
        logger.info(f"🔄 Reverse engineering {len(sheet_df)} Google Sheet transactions to Excel format")
        
        excel_rows = []
        
        for _, row in sheet_df.iterrows():
            try:
                # Parse amounts from Swedish format
                outflow = self.clean_swedish_amount(row.get('OUTFLOW', ''))
                inflow = self.clean_swedish_amount(row.get('INFLOW', ''))
                
                # Calculate amount: OUTFLOW -> negative, INFLOW -> positive
                if outflow > 0:
                    amount = -outflow  # Negative for outflow
                elif inflow > 0:
                    amount = inflow   # Positive for inflow
                else:
                    amount = 0.0
                
                # Create description from category and memo
                category = str(row.get('CATEGORY', '')).strip()
                memo = str(row.get('MEMO', '')).strip()
                description = f"{category}: {memo}" if category and memo else category or memo
                
                # Determine transaction type
                transaction_type = self.determine_transaction_type(
                    row.get('OUTFLOW', ''), 
                    row.get('INFLOW', ''), 
                    category
                )
                
                # Create date with 0:00 time
                date_obj = pd.to_datetime(row['DATE']).date()
                date_with_time = f"{date_obj} 0:00:00"
                
                # Create Excel row according to Revolut format
                excel_row = {
                    'Type': transaction_type,
                    'Product': 'Current',
                    'Started Date': date_with_time,
                    'Completed Date': date_with_time,
                    'Description': description,
                    'Amount': amount,
                    'Fee': 0.00,
                    'Currency': 'SEK',
                    'State': 'COMPLETED',
                    'Balance': ''  # Leave empty as requested
                }
                
                excel_rows.append(excel_row)
                
            except Exception as e:
                logger.error(f"Error processing row: {e}")
                continue
        
        result_df = pd.DataFrame(excel_rows)
        logger.info(f"✅ Successfully reverse engineered {len(result_df)} transactions")
        
        # Show sample of reverse engineered data
        if len(result_df) > 0:
            logger.info("📋 Sample reverse engineered transactions:")
            for i, row in result_df.head(3).iterrows():
                logger.info(f"  {row['Completed Date']} | {row['Type']} | {row['Amount']} | {row['Description']}")
        
        return result_df
    
    def merge_data(self, excel_df: pd.DataFrame, sheet_excel_df: pd.DataFrame) -> pd.DataFrame:
        """Merge Excel data with reverse engineered Google Sheet data."""
        logger.info("🔗 Merging Excel and Google Sheet data")
        
        # Ensure both DataFrames have the same columns
        excel_columns = set(excel_df.columns)
        sheet_columns = set(sheet_excel_df.columns)
        
        if excel_columns != sheet_columns:
            logger.warning(f"Column mismatch - Excel: {excel_columns}, Sheet: {sheet_columns}")
            # Use Excel columns as the standard
            sheet_excel_df = sheet_excel_df.reindex(columns=excel_df.columns, fill_value='')
        
        # Combine the DataFrames
        merged_df = pd.concat([sheet_excel_df, excel_df], ignore_index=True)
        
        # Sort by Completed Date
        merged_df['Completed_Date_parsed'] = pd.to_datetime(merged_df['Completed Date'], errors='coerce')
        merged_df = merged_df.sort_values('Completed_Date_parsed').drop('Completed_Date_parsed', axis=1)
        
        logger.info(f"✅ Merged data: {len(sheet_excel_df)} Google Sheet + {len(excel_df)} Excel = {len(merged_df)} total")
        
        return merged_df
    
    def save_merged_file(self, merged_df: pd.DataFrame) -> str:
        """Save merged data to Excel file."""
        logger.info(f"💾 Saving merged data to {self.merged_file}")
        
        try:
            merged_df.to_excel(self.merged_file, index=False, engine='openpyxl')
            
            # Verify the saved file
            verification_df = pd.read_excel(self.merged_file, engine='openpyxl')
            logger.info(f"✅ Successfully saved {len(verification_df)} transactions to {self.merged_file}")
            
            # Show date range of merged file
            if 'Completed Date' in verification_df.columns:
                dates = pd.to_datetime(verification_df['Completed Date'], errors='coerce')
                logger.info(f"📅 Merged file date range: {dates.min()} to {dates.max()}")
            
            # Show statistics
            logger.info("📊 Merged file statistics:")
            if 'Type' in verification_df.columns:
                type_counts = verification_df['Type'].value_counts()
                for type_name, count in type_counts.items():
                    logger.info(f"  {type_name}: {count} transactions")
            
            return str(self.merged_file)
            
        except Exception as e:
            logger.error(f"❌ Failed to save merged file: {e}")
            raise
    
    def create_merged_file(self) -> str:
        """Main method to create the merged Revolut file."""
        logger.info("🚀 Starting Revolut merge process")
        
        try:
            # Step 1: Read Excel data (recent period)
            excel_df = self.read_excel_data()
            
            # Step 2: Read Google Sheet data (historical period)
            # Use cutoff date based on earliest Excel date
            cutoff_date = "2022-01-03"
            sheet_df = self.read_google_sheet_revolut("2021-10-11", "2022-01-02")
            
            if len(sheet_df) == 0:
                logger.warning("No historical Google Sheet data found, using only Excel data")
                merged_df = excel_df
            else:
                # Step 3: Reverse engineer Google Sheet data to Excel format
                sheet_excel_df = self.reverse_engineer_to_excel_format(sheet_df)
                
                # Step 4: Merge the data
                merged_df = self.merge_data(excel_df, sheet_excel_df)
            
            # Step 5: Save merged file
            merged_file_path = self.save_merged_file(merged_df)
            
            logger.info(f"🎉 Revolut merge completed successfully!")
            logger.info(f"📁 Merged file: {merged_file_path}")
            
            return merged_file_path
            
        except Exception as e:
            logger.error(f"❌ Revolut merge failed: {e}")
            raise

def main():
    """Main function to run the Revolut merger."""
    try:
        merger = RevolutMerger()
        merged_file = merger.create_merged_file()
        print(f"\n✅ Success! Merged file created: {merged_file}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 