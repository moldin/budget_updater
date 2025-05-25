#!/usr/bin/env python3
"""
Create merged Strawberry file in Excel format from Excel data + Google Sheet historical data.

Process:
1. Reads existing strawberry.xls (2024-08-06 to 2025-04-30)
2. Reads Google Sheet Transactions for Strawberry 2023-09-24 to 2024-08-05
3. Reverse engineers Google Sheet data to Strawberry Excel format
4. Merges and creates strawberry_all_merged.xlsx

Mapping from Google Sheet to Strawberry Excel:
- Date -> Datum (date only, no time)
- Date -> Bokfört (date only, no time)
- OUTFLOW -> Belopp (positive amount)
- INFLOW -> Belopp (negative amount, e.g. 300 -> -300)
- CATEGORY: MEMO -> Specifikation (concatenated with colon separator)
- Ort: Empty
- Valuta: Empty
- Utl.belopp: Empty
"""

import logging
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import hashlib
from src.budget_updater.sheets_api import SheetAPI
from src.budget_updater import config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StrawberryMerger:
    """Merge Strawberry Excel data with Google Sheet historical data in Excel format."""
    
    def __init__(self):
        """Initialize the merger."""
        self.sheet_api = SheetAPI()
        self.excel_file = Path("data/strawberry.xls")
        self.output_file = Path("data/strawberry_all_merged.xlsx")
        
    def read_excel_data(self) -> pd.DataFrame:
        """Read existing Strawberry Excel data."""
        logger.info(f"📖 Reading Excel data from {self.excel_file}")
        
        try:
            df = pd.read_excel(self.excel_file)
            logger.info(f"📋 Read {len(df)} total rows from Excel")
            
            # Filter out currency exchange rate rows
            valid_df = df[pd.to_datetime(df['Datum'], errors='coerce').notna()].copy()
            logger.info(f"📋 Valid transactions after filtering: {len(valid_df)}")
            
            # Convert Datum and Bokfört to date only (no time) for consistency
            valid_df['Datum'] = pd.to_datetime(valid_df['Datum']).dt.date
            valid_df['Bokfört'] = pd.to_datetime(valid_df['Bokfört']).dt.date
            
            if len(valid_df) > 0:
                earliest = valid_df['Datum'].min()
                latest = valid_df['Datum'].max()
                logger.info(f"📅 Excel date range: {earliest} to {latest}")
            
            return valid_df
            
        except Exception as e:
            logger.error(f"❌ Failed to read Excel data: {e}")
            raise
    
    def read_google_sheet_strawberry(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Read Strawberry transactions from Google Sheet for specified date range."""
        logger.info(f"📖 Reading Google Sheet Strawberry data from {start_date} to {end_date}")
        
        try:
            # Read all data from Transactions sheet using proper range
            range_name = "Transactions!A:H"  # Columns A-H (including empty first column)
            
            result = self.sheet_api.service.spreadsheets().values().get(
                spreadsheetId=config.SPREADSHEET_ID,
                range=range_name
            ).execute()
            
            sheet_data = result.get('values', [])
            
            if not sheet_data:
                logger.warning("No data found in Google Sheet")
                return pd.DataFrame()
                
            # Find the header row (should be row with 'DATE' in column B)
            header_row_index = None
            for i, row in enumerate(sheet_data):
                if len(row) > 1 and row[1] == 'DATE':  # Column B should be 'DATE'
                    header_row_index = i
                    break
            
            if header_row_index is None:
                logger.error("Could not find header row in Google Sheet")
                return pd.DataFrame()
            
            # Get headers and data rows
            headers = sheet_data[header_row_index]
            data_rows = sheet_data[header_row_index + 1:]
            
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
            logger.info(f"✅ Read {len(df)} total rows from Google Sheet")
            
            # Filter for Strawberry transactions
            strawberry_df = df[df['ACCOUNT'] == '💳 Strawberry'].copy()
            logger.info(f"🍓 Strawberry transactions found: {len(strawberry_df)}")
            
            if len(strawberry_df) == 0:
                logger.warning("No Strawberry transactions found in Google Sheet")
                return pd.DataFrame()
            
            # Convert Date column to datetime and filter by date range
            strawberry_df['Date_parsed'] = pd.to_datetime(strawberry_df['DATE'], errors='coerce')
            valid_dates = strawberry_df['Date_parsed'].notna()
            strawberry_df = strawberry_df[valid_dates].copy()
            
            # Filter by date range
            start_dt = pd.to_datetime(start_date).date()
            end_dt = pd.to_datetime(end_date).date()
            
            date_mask = (strawberry_df['Date_parsed'].dt.date >= start_dt) & (strawberry_df['Date_parsed'].dt.date <= end_dt)
            filtered_df = strawberry_df[date_mask].copy()
            
            logger.info(f"📅 Filtered to date range {start_date} to {end_date}: {len(filtered_df)} transactions")
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"Failed to read Google Sheet data: {e}")
            raise
    
    def reverse_engineer_to_excel_format(self, sheet_df: pd.DataFrame) -> pd.DataFrame:
        """Convert Google Sheet data to Strawberry Excel format."""
        logger.info("🔧 Reverse engineering Google Sheet data to Excel format...")
        
        if len(sheet_df) == 0:
            logger.warning("No data to reverse engineer")
            return pd.DataFrame()
        
        excel_rows = []
        
        for _, row in sheet_df.iterrows():
            try:
                # Extract fields from Google Sheet
                date_str = row['DATE']
                outflow = row.get('OUTFLOW', '')
                inflow = row.get('INFLOW', '')
                category = row.get('CATEGORY', '')
                memo = row.get('MEMO', '')
                
                # Parse date and convert to date only (no time)
                date_parsed = pd.to_datetime(date_str).date()
                
                # Calculate amount according to mapping:
                # OUTFLOW -> positive belopp
                # INFLOW -> negative belopp (e.g. 300 -> -300)
                belopp = 0.0
                
                if outflow and str(outflow).strip():
                    # Parse outflow as positive amount
                    amount_str = str(outflow).replace(" ", "").replace(",", ".").replace("kr", "").replace("\xa0", "").strip()
                    try:
                        belopp = float(amount_str)
                    except ValueError:
                        logger.warning(f"Could not parse outflow '{outflow}', using 0")
                        belopp = 0.0
                        
                elif inflow and str(inflow).strip():
                    # Parse inflow as negative amount
                    amount_str = str(inflow).replace(" ", "").replace(",", ".").replace("kr", "").replace("\xa0", "").strip()
                    try:
                        belopp = -float(amount_str)  # Negative for inflow
                    except ValueError:
                        logger.warning(f"Could not parse inflow '{inflow}', using 0")
                        belopp = 0.0
                
                # Create specifikation by concatenating category and memo
                specifikation_parts = []
                if category and str(category).strip():
                    specifikation_parts.append(str(category).strip())
                if memo and str(memo).strip():
                    specifikation_parts.append(str(memo).strip())
                
                specifikation = ": ".join(specifikation_parts) if specifikation_parts else "Historical Transaction"
                
                # Create Excel row according to strawberry.xls format
                excel_row = {
                    'Datum': date_parsed,
                    'Bokfört': date_parsed,  # Same as Datum
                    'Specifikation': specifikation,
                    'Ort': '',  # Empty as specified
                    'Valuta': '',  # Empty as specified
                    'Utl.belopp/moms': '',  # Empty as specified
                    'Belopp': belopp
                }
                
                excel_rows.append(excel_row)
                
            except Exception as e:
                logger.error(f"Error processing row: {e}")
                continue
        
        if excel_rows:
            result_df = pd.DataFrame(excel_rows)
            logger.info(f"✅ Reverse engineered {len(result_df)} transactions")
            return result_df
        else:
            logger.warning("No valid transactions after reverse engineering")
            return pd.DataFrame()
    
    def merge_data(self, excel_df: pd.DataFrame, sheet_df: pd.DataFrame) -> pd.DataFrame:
        """Merge Excel and Google Sheet data."""
        logger.info("🔗 Merging Excel and Google Sheet data...")
        
        # Combine dataframes
        if len(sheet_df) == 0:
            logger.info("No Google Sheet data to merge, using only Excel data")
            merged_df = excel_df.copy()
        elif len(excel_df) == 0:
            logger.info("No Excel data, using only Google Sheet data")
            merged_df = sheet_df.copy()
        else:
            # Concatenate dataframes
            merged_df = pd.concat([sheet_df, excel_df], ignore_index=True)
        
        # Sort by date (newest first, like original Excel file)
        merged_df = merged_df.sort_values('Datum', ascending=False).reset_index(drop=True)
        
        logger.info(f"✅ Merged data: {len(merged_df)} total transactions")
        
        if len(merged_df) > 0:
            earliest = merged_df['Datum'].min()
            latest = merged_df['Datum'].max()
            logger.info(f"📅 Final date range: {earliest} to {latest}")
        
        return merged_df
    
    def save_merged_file(self, merged_df: pd.DataFrame) -> Path:
        """Save merged data to Excel file."""
        logger.info(f"💾 Saving merged data to {self.output_file}")
        
        try:
            # Ensure output directory exists
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to Excel
            merged_df.to_excel(self.output_file, index=False, engine='openpyxl')
            
            logger.info(f"✅ Successfully saved {len(merged_df)} transactions to {self.output_file}")
            logger.info(f"📁 File size: {self.output_file.stat().st_size / 1024:.1f} KB")
            
            return self.output_file
            
        except Exception as e:
            logger.error(f"❌ Failed to save merged file: {e}")
            raise
    
    def create_merged_file(self) -> Optional[Path]:
        """Main method to create merged Strawberry file."""
        logger.info("🍓 Starting Strawberry data merge process...")
        
        try:
            # Step 1: Read Excel data (recent period)
            excel_df = self.read_excel_data()
            
            # Step 2: Read Google Sheet data (historical period only)
            sheet_df = self.read_google_sheet_strawberry("2023-09-24", "2024-08-05")
            
            # Step 3: Reverse engineer Google Sheet data to Excel format
            if len(sheet_df) > 0:
                sheet_excel_df = self.reverse_engineer_to_excel_format(sheet_df)
            else:
                sheet_excel_df = pd.DataFrame()
            
            # Step 4: Merge data
            merged_df = self.merge_data(excel_df, sheet_excel_df)
            
            # Step 5: Save merged file
            output_path = self.save_merged_file(merged_df)
            
            logger.info("🎉 Strawberry merge process completed successfully!")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Merge process failed: {e}")
            return None

def main():
    """Main function."""
    merger = StrawberryMerger()
    result = merger.create_merged_file()
    
    if result:
        print(f"\n✅ Success! Merged file created: {result}")
        print(f"📊 You can now use this file for analysis or upload to BigQuery")
    else:
        print("\n❌ Failed to create merged file")
        exit(1)

if __name__ == "__main__":
    main() 