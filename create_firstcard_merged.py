#!/usr/bin/env python3
"""
Create merged FirstCard file in Excel format from Excel data + Google Sheet historical data.

This script:
1. Reads data/firstcard_250523.xlsx (clean Excel data)
2. Reads Google Sheet Transactions for FirstCard 2021-10-11 to 2023-04-30
3. Reverse engineers Google Sheet data to FirstCard Excel format
4. Merges them into firstcard_all_merged.xlsx in FirstCard Excel format
"""

import logging
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

from src.budget_updater.sheets_api import SheetAPI
from src.budget_updater.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FirstCardMerger:
    """Merge FirstCard Excel data with Google Sheet historical data in Excel format."""
    
    def __init__(self):
        self.config = Config()
        self.sheets_client = SheetAPI()
        
    def read_excel_data(self, excel_path: Path) -> pd.DataFrame:
        """Read FirstCard Excel file."""
        logger.info(f"📖 Reading Excel file: {excel_path}")
        
        if not excel_path.exists():
            raise FileNotFoundError(f"Excel file not found: {excel_path}")
        
        # Read Excel file
        df = pd.read_excel(excel_path)
        
        logger.info(f"✅ Read {len(df)} rows from Excel")
        logger.info(f"   Columns: {list(df.columns)}")
        
        # Show date range
        if 'Datum' in df.columns:
            df['Datum'] = pd.to_datetime(df['Datum'])
            min_date = df['Datum'].min()
            max_date = df['Datum'].max()
            logger.info(f"   Date range: {min_date.date()} to {max_date.date()}")
        
        return df
    
    def read_google_sheet_firstcard(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Read FirstCard transactions from Google Sheet for specified date range."""
        logger.info(f"📖 Reading Google Sheet FirstCard data from {start_date} to {end_date}")
        
        try:
            # Get all data from Transactions sheet
            sheet_data = self.sheets_client.get_all_sheet_data(
                self.config.transactions_sheet
            )
            
            if not sheet_data:
                logger.warning("No data found in Google Sheet")
                return pd.DataFrame()
            
            # Find the header row (contains 'DATE', 'OUTFLOW', etc.)
            header_row_index = None
            for i, row in enumerate(sheet_data):
                if len(row) > 1 and 'DATE' in row:
                    header_row_index = i
                    break
            
            if header_row_index is None:
                logger.error("Could not find header row in Google Sheet")
                return pd.DataFrame()
            
            logger.info(f"   Found headers at row {header_row_index}")
            
            # Extract headers and data
            headers = sheet_data[header_row_index]
            data_rows = sheet_data[header_row_index + 1:]
            
            # Remove empty rows and ensure all rows have same number of columns
            clean_data_rows = []
            for row in data_rows:
                if len(row) > 1 and any(cell.strip() for cell in row if cell):  # Has non-empty content
                    # Pad row to match header length
                    while len(row) < len(headers):
                        row.append('')
                    clean_data_rows.append(row)
            
            logger.info(f"   Clean data rows: {len(clean_data_rows)}")
            
            if not clean_data_rows:
                logger.warning("No data rows found after cleaning")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(clean_data_rows, columns=headers)
            logger.info(f"✅ Read {len(df)} total rows from Google Sheet")
            
            # Filter for FirstCard account
            firstcard_df = df[df['ACCOUNT'] == '💳 First Card'].copy()
            logger.info(f"   FirstCard rows: {len(firstcard_df)}")
            
            if len(firstcard_df) == 0:
                logger.warning("No FirstCard transactions found in Google Sheet")
                return pd.DataFrame()
            
            # Convert Date column and filter date range
            firstcard_df['DATE'] = pd.to_datetime(firstcard_df['DATE'], errors='coerce')
            
            # Filter date range
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            filtered_df = firstcard_df[
                (firstcard_df['DATE'] >= start_dt) & 
                (firstcard_df['DATE'] <= end_dt)
            ].copy()
            
            logger.info(f"   Filtered to date range: {len(filtered_df)} rows")
            
            if len(filtered_df) > 0:
                min_date = filtered_df['DATE'].min()
                max_date = filtered_df['DATE'].max()
                logger.info(f"   Date range: {min_date.date()} to {max_date.date()}")
            
            return filtered_df
            
        except Exception as e:
            logger.error(f"Failed to read Google Sheet data: {e}")
            raise
    
    def reverse_engineer_to_excel_format(self, sheet_df: pd.DataFrame) -> pd.DataFrame:
        """Convert Google Sheet data to FirstCard Excel format."""
        logger.info("🔧 Reverse engineering Google Sheet data to Excel format...")
        
        if len(sheet_df) == 0:
            logger.warning("No data to reverse engineer")
            return pd.DataFrame()
        
        # Create DataFrame with FirstCard Excel columns
        excel_format_df = pd.DataFrame()
        
        # Map DATE -> Datum
        excel_format_df['Datum'] = sheet_df['DATE']
        
        # Initialize other columns as empty
        excel_format_df['Ytterligare information'] = ''
        excel_format_df['Reseinformation / Inköpsplats'] = ''
        excel_format_df['Valuta'] = 'SEK'
        excel_format_df['växlingskurs'] = ''
        excel_format_df['Utländskt belopp'] = ''
        excel_format_df['Belopp'] = 0.0
        excel_format_df['Moms'] = ''
        excel_format_df['Kort'] = 'unknown'
        
        # Process each row to handle OUTFLOW/INFLOW -> Belopp mapping
        errors = []
        
        def clean_swedish_amount(amount_str):
            """Clean Swedish amount format: '1 234,56 kr' -> 1234.56"""
            if not amount_str or amount_str == 'nan' or pd.isna(amount_str):
                return None
            
            # Convert to string and clean
            amount_clean = str(amount_str).strip()
            
            # Remove 'kr' suffix
            amount_clean = amount_clean.replace(' kr', '').replace('kr', '')
            
            # Remove spaces (thousand separators)
            amount_clean = amount_clean.replace(' ', '')
            
            # Replace Swedish decimal comma with dot
            amount_clean = amount_clean.replace(',', '.')
            
            # Check if empty after cleaning
            if not amount_clean or amount_clean == '0' or amount_clean == '0.0':
                return 0.0
            
            try:
                return float(amount_clean)
            except ValueError:
                return None
        
        for idx, row in sheet_df.iterrows():
            outflow = row.get('OUTFLOW', '')
            inflow = row.get('INFLOW', '')
            category = str(row.get('CATEGORY', '')).strip()
            memo = str(row.get('MEMO', '')).strip()
            
            # Clean outflow/inflow values
            outflow_clean = clean_swedish_amount(outflow)
            inflow_clean = clean_swedish_amount(inflow)
            
            # Check for both OUTFLOW and INFLOW on same row (error condition)
            has_outflow = outflow_clean is not None and outflow_clean != 0
            has_inflow = inflow_clean is not None and inflow_clean != 0
            
            if has_outflow and has_inflow:
                error_msg = f"Row {idx}: Both OUTFLOW ({outflow}) and INFLOW ({inflow}) present on same row"
                errors.append(error_msg)
                logger.error(error_msg)
                continue
            
            # Map to Belopp
            if has_outflow:
                excel_format_df.loc[idx, 'Belopp'] = outflow_clean
            elif has_inflow:
                # INFLOW becomes negative Belopp
                excel_format_df.loc[idx, 'Belopp'] = -inflow_clean
            else:
                # No amount - this might be valid for some transaction types
                excel_format_df.loc[idx, 'Belopp'] = 0.0
            
            # Create "Category: Memo" for Reseinformation / Inköpsplats
            if category and memo:
                excel_format_df.loc[idx, 'Reseinformation / Inköpsplats'] = f"{category}: {memo}"
            elif category:
                excel_format_df.loc[idx, 'Reseinformation / Inköpsplats'] = category
            elif memo:
                excel_format_df.loc[idx, 'Reseinformation / Inköpsplats'] = memo
            else:
                excel_format_df.loc[idx, 'Reseinformation / Inköpsplats'] = ''
        
        # Report errors
        if errors:
            logger.error(f"❌ Found {len(errors)} errors during reverse engineering:")
            for error in errors[:5]:  # Show first 5 errors
                logger.error(f"   {error}")
            if len(errors) > 5:
                logger.error(f"   ... and {len(errors) - 5} more errors")
        
        logger.info(f"✅ Reverse engineered {len(excel_format_df)} rows to Excel format")
        logger.info(f"   Errors encountered: {len(errors)}")
        
        return excel_format_df
    
    def check_overlaps(self, excel_df: pd.DataFrame, sheet_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Check for date overlaps between Excel and Sheet data."""
        logger.info("🔍 Checking for date overlaps...")
        
        if len(excel_df) == 0 or len(sheet_df) == 0:
            logger.info("   No overlap possible - one dataset is empty")
            return pd.DataFrame(), pd.DataFrame()
        
        excel_dates = set(excel_df['Datum'].dt.date)
        sheet_dates = set(sheet_df['Datum'].dt.date)
        
        overlap_dates = excel_dates.intersection(sheet_dates)
        
        if overlap_dates:
            logger.warning(f"   Found {len(overlap_dates)} overlapping dates!")
            logger.warning(f"   Overlap dates: {sorted(list(overlap_dates))[:10]}...")  # Show first 10
            
            # Get overlapping transactions
            excel_overlaps = excel_df[excel_df['Datum'].dt.date.isin(overlap_dates)]
            sheet_overlaps = sheet_df[sheet_df['Datum'].dt.date.isin(overlap_dates)]
            
            return excel_overlaps, sheet_overlaps
        else:
            logger.info("   ✅ No date overlaps found")
            return pd.DataFrame(), pd.DataFrame()
    
    def merge_data(self, excel_df: pd.DataFrame, sheet_df: pd.DataFrame) -> pd.DataFrame:
        """Merge Excel and reverse engineered Sheet data."""
        logger.info("🔗 Merging Excel and reverse engineered Sheet data...")
        
        # Combine dataframes
        merged_df = pd.concat([sheet_df, excel_df], ignore_index=True)
        
        # Sort by date
        merged_df = merged_df.sort_values('Datum').reset_index(drop=True)
        
        logger.info(f"✅ Merged data:")
        logger.info(f"   Reverse engineered data: {len(sheet_df)} rows")
        logger.info(f"   Excel data: {len(excel_df)} rows")
        logger.info(f"   Total merged: {len(merged_df)} rows")
        
        if len(merged_df) > 0:
            min_date = merged_df['Datum'].min()
            max_date = merged_df['Datum'].max()
            logger.info(f"   Date range: {min_date.date()} to {max_date.date()}")
        
        return merged_df
    
    def save_merged_file(self, df: pd.DataFrame, output_path: Path) -> None:
        """Save merged data to Excel file."""
        logger.info(f"💾 Saving merged data to: {output_path}")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Format Date column to match FirstCard Excel format (YYYY-MM-DD without timestamp)
        df_copy = df.copy()
        if 'Datum' in df_copy.columns:
            df_copy['Datum'] = pd.to_datetime(df_copy['Datum']).dt.date
        
        # Save to Excel
        df_copy.to_excel(output_path, index=False)
        
        logger.info(f"✅ Saved {len(df)} rows to {output_path}")
        
        # Show summary
        file_size = output_path.stat().st_size
        logger.info(f"   File size: {file_size:,} bytes")
        
        # Show sample of data
        logger.info("   Sample rows:")
        for i, row in df.head(3).iterrows():
            date_str = row['Datum'].strftime('%Y-%m-%d') if hasattr(row['Datum'], 'strftime') else str(row['Datum'])
            logger.info(f"     {date_str} | {row['Belopp']} | {row['Reseinformation / Inköpsplats'][:30]}")
    
    def create_merged_file(self) -> Path:
        """Main method to create merged FirstCard file in Excel format."""
        logger.info("🚀 Creating merged FirstCard file in Excel format...")
        
        # Paths
        excel_path = Path("data/firstcard_250523.xlsx")
        output_path = Path("data/firstcard_all_merged.xlsx")
        
        # 1. Read Excel data
        excel_df = self.read_excel_data(excel_path)
        
        # 2. Read Google Sheet data (historical period only)
        sheet_df = self.read_google_sheet_firstcard("2021-10-11", "2023-04-30")
        
        # 3. Reverse engineer Google Sheet data to Excel format
        sheet_excel_format = self.reverse_engineer_to_excel_format(sheet_df)
        
        # 4. Check for overlaps
        excel_overlaps, sheet_overlaps = self.check_overlaps(excel_df, sheet_excel_format)
        
        if len(excel_overlaps) > 0:
            logger.warning("⚠️  Found overlapping dates - manual review recommended")
            logger.info("   Excel overlaps:")
            for _, row in excel_overlaps.head().iterrows():
                logger.info(f"     {row['Datum'].date()} | {row['Belopp']} | {row['Reseinformation / Inköpsplats'][:30]}")
            logger.info("   Reverse engineered overlaps:")
            for _, row in sheet_overlaps.head().iterrows():
                logger.info(f"     {row['Datum'].date()} | {row['Belopp']} | {row['Reseinformation / Inköpsplats'][:30]}")
        
        # 5. Merge data
        merged_df = self.merge_data(excel_df, sheet_excel_format)
        
        # 6. Save merged file
        self.save_merged_file(merged_df, output_path)
        
        logger.info("🎉 Merged file creation completed!")
        return output_path


def main():
    """Main function."""
    try:
        merger = FirstCardMerger()
        output_file = merger.create_merged_file()
        
        print(f"\n✅ Success! Created merged file: {output_file}")
        print("📋 File format: FirstCard Excel format")
        print("📋 Next steps:")
        print("   1. Review the merged file for any issues")
        print("   2. Check for unexpected duplicates or overlaps")
        print("   3. When satisfied, use this file for a clean BigQuery import")
        
    except Exception as e:
        logger.error(f"Failed to create merged file: {e}")
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main() 