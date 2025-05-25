#!/usr/bin/env python3
"""
Reverse engineer FirstCard transactions from Google Sheet back to raw format.

This script safely extracts FirstCard transactions from the Google Sheet
and converts them back to firstcard_transactions_raw format for historical data.
"""

import logging
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from google.cloud import bigquery
from src.budget_updater.config import Config
from src.budget_updater.sheets_api import SheetAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FirstCardReverseEngineer:
    """Reverse engineer FirstCard data from Google Sheet to raw format."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
        self.sheets_api = SheetAPI()
    
    def get_existing_firstcard_date_range(self) -> tuple:
        """Get the date range of existing FirstCard raw data."""
        query = f"""
        SELECT 
            MIN(PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10))) as min_date,
            MAX(PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10))) as max_date,
            COUNT(*) as count
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.firstcard_transactions_raw`
        """
        
        try:
            result = list(self.client.query(query).result())
            if result:
                row = result[0]
                return row.min_date, row.max_date, row.count
            return None, None, 0
        except Exception as e:
            logger.error(f"Failed to get existing date range: {e}")
            return None, None, 0
    
    def read_google_sheet_transactions(self) -> List[List]:
        """Read transactions from Google Sheet Transactions tab."""
        try:
            # Read the entire Transactions sheet
            spreadsheet_id = self.config.spreadsheet_id
            range_name = f"{self.config.transactions_sheet}!A:G"  # Assuming columns A-G
            
            result = self.sheets_api.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.warning("No data found in Transactions sheet")
                return []
            
            # Skip header row
            return values[1:] if len(values) > 1 else []
            
        except Exception as e:
            logger.error(f"Failed to read Google Sheet: {e}")
            return []
    
    def filter_firstcard_transactions(self, sheet_data: List[List], 
                                    cutoff_date: str = "2023-05-01") -> List[Dict]:
        """
        Filter and convert FirstCard transactions from sheet data.
        
        Args:
            sheet_data: Raw sheet data
            cutoff_date: Only process transactions before this date
        """
        firstcard_transactions = []
        
        for i, row in enumerate(sheet_data):
            try:
                # Ensure row has enough columns (pad with empty strings if needed)
                while len(row) < 7:
                    row.append("")
                
                date, outflow, inflow, category, account, memo, status = row[:7]
                
                # Filter for FirstCard only
                if account != "💳 First Card":
                    continue
                
                # Filter by date (only before cutoff_date)
                if date and date >= cutoff_date:
                    continue
                
                # Skip if no date
                if not date:
                    continue
                
                # Convert amounts
                belopp = 0.0
                if outflow and outflow.strip():
                    # Outflow -> positive belopp
                    amount_str = outflow.replace(" ", "").replace(",", ".")
                    try:
                        belopp = float(amount_str)
                    except ValueError:
                        logger.warning(f"Could not parse outflow: {outflow}")
                        continue
                elif inflow and inflow.strip():
                    # Inflow -> negative belopp
                    amount_str = inflow.replace(" ", "").replace(",", ".")
                    try:
                        belopp = -float(amount_str)  # Negative for inflow
                    except ValueError:
                        logger.warning(f"Could not parse inflow: {inflow}")
                        continue
                else:
                    logger.warning(f"No amount found for row {i+2}")
                    continue
                
                # Combine category and memo
                reseinformation = f"{category} - {memo}".strip(" -")
                if not reseinformation:
                    reseinformation = "Historical Transaction"
                
                # Create business key
                business_key = self.create_business_key(date, belopp, reseinformation)
                
                # Create raw transaction record
                raw_transaction = {
                    'file_hash': 'google_sheet_reverse_engineered',
                    'source_file': 'orig_google_sheet_rev_engineered',
                    'upload_timestamp': datetime.now(timezone.utc).isoformat(),
                    'row_number': i + 2,  # Sheet row number
                    'datum': date,
                    'ytterligare_information': memo or "",
                    'reseinformation_inkopsplats': reseinformation,
                    'valuta': 'SEK',
                    'vaxlingskurs': None,
                    'utlandskt_belopp': None,
                    'belopp': belopp,
                    'moms': None,
                    'kort': 'unknown',
                    'business_key': business_key
                }
                
                firstcard_transactions.append(raw_transaction)
                
            except Exception as e:
                logger.error(f"Error processing row {i+2}: {e}")
                continue
        
        return firstcard_transactions
    
    def create_business_key(self, date: str, belopp: float, description: str) -> str:
        """Create unique business key for reverse engineered transaction."""
        # Normalize components
        date_str = str(date)[:10] if date else "unknown"
        amount_str = f"{belopp:.2f}"
        desc_normalized = description.strip().lower()[:50] if description else ""
        
        # Create business key
        key_components = f"firstcard|{date_str}|{amount_str}|{desc_normalized}"
        business_key = hashlib.md5(key_components.encode('utf-8')).hexdigest()
        
        return f"firstcard_rev_{business_key}"
    
    def check_for_duplicates(self, transactions: List[Dict]) -> List[Dict]:
        """Check for existing business keys to avoid duplicates."""
        if not transactions:
            return []
        
        business_keys = [t['business_key'] for t in transactions]
        
        # Check existing keys
        placeholders = ', '.join([f"'{key}'" for key in business_keys])
        query = f"""
        SELECT DISTINCT business_key
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.firstcard_transactions_raw`
        WHERE business_key IN ({placeholders})
        """
        
        try:
            result = self.client.query(query).result()
            existing_keys = set(row.business_key for row in result)
            
            # Filter out duplicates
            new_transactions = [t for t in transactions if t['business_key'] not in existing_keys]
            
            duplicate_count = len(transactions) - len(new_transactions)
            if duplicate_count > 0:
                logger.info(f"Skipping {duplicate_count} duplicate transactions")
            
            return new_transactions
            
        except Exception as e:
            logger.warning(f"Could not check for duplicates: {e}")
            return transactions
    
    def insert_raw_transactions(self, transactions: List[Dict]) -> int:
        """Insert transactions into firstcard_transactions_raw table."""
        if not transactions:
            logger.info("No transactions to insert")
            return 0
        
        table_ref = self.client.dataset(self.dataset_id).table('firstcard_transactions_raw')
        
        try:
            errors = self.client.insert_rows_json(table_ref, transactions)
            if errors:
                logger.error(f"Failed to insert rows: {errors}")
                return 0
            
            logger.info(f"✅ Successfully inserted {len(transactions)} reverse engineered transactions")
            return len(transactions)
            
        except Exception as e:
            logger.error(f"Failed to insert transactions: {e}")
            raise
    
    def create_backup(self) -> bool:
        """Create backup of existing firstcard_transactions_raw table."""
        backup_table = f"firstcard_transactions_raw_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        query = f"""
        CREATE TABLE `{self.config.gcp_project_id}.{self.dataset_id}.{backup_table}` AS
        SELECT * FROM `{self.config.gcp_project_id}.{self.dataset_id}.firstcard_transactions_raw`
        """
        
        try:
            job = self.client.query(query)
            job.result()  # Wait for completion
            logger.info(f"✅ Created backup table: {backup_table}")
            return True
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False
    
    def reverse_engineer_firstcard_data(self, cutoff_date: str = "2023-05-01", 
                                      create_backup: bool = True) -> int:
        """
        Main function to reverse engineer FirstCard data.
        
        Args:
            cutoff_date: Only process transactions before this date
            create_backup: Whether to create backup before inserting
            
        Returns:
            Number of transactions inserted
        """
        logger.info("🚀 Starting FirstCard reverse engineering process")
        
        # Step 1: Check existing data
        min_date, max_date, count = self.get_existing_firstcard_date_range()
        logger.info(f"📊 Existing FirstCard raw data: {count} transactions")
        if min_date and max_date:
            logger.info(f"   Date range: {min_date} to {max_date}")
        
        # Step 2: Create backup if requested
        if create_backup and count > 0:
            if not self.create_backup():
                logger.error("❌ Backup failed, aborting")
                return 0
        
        # Step 3: Read Google Sheet
        logger.info("📖 Reading Google Sheet Transactions...")
        sheet_data = self.read_google_sheet_transactions()
        if not sheet_data:
            logger.error("❌ No data found in Google Sheet")
            return 0
        
        logger.info(f"📋 Found {len(sheet_data)} total rows in sheet")
        
        # Step 4: Filter and convert FirstCard transactions
        logger.info(f"🔍 Filtering FirstCard transactions before {cutoff_date}...")
        firstcard_transactions = self.filter_firstcard_transactions(sheet_data, cutoff_date)
        
        if not firstcard_transactions:
            logger.info("ℹ️  No FirstCard transactions found to reverse engineer")
            return 0
        
        logger.info(f"🎯 Found {len(firstcard_transactions)} FirstCard transactions to reverse engineer")
        
        # Step 5: Check for duplicates
        logger.info("🔍 Checking for duplicates...")
        new_transactions = self.check_for_duplicates(firstcard_transactions)
        
        if not new_transactions:
            logger.info("ℹ️  All transactions already exist, nothing to insert")
            return 0
        
        # Step 6: Insert new transactions
        logger.info(f"📥 Inserting {len(new_transactions)} new transactions...")
        inserted_count = self.insert_raw_transactions(new_transactions)
        
        logger.info(f"🎉 Reverse engineering complete! Inserted {inserted_count} transactions")
        return inserted_count


def main():
    """Run the FirstCard reverse engineering process."""
    try:
        config = Config()
        engineer = FirstCardReverseEngineer(config)
        
        # Run with default cutoff date (2023-05-01)
        # This will only process transactions BEFORE this date
        inserted_count = engineer.reverse_engineer_firstcard_data(
            cutoff_date="2023-05-01",
            create_backup=True
        )
        
        if inserted_count > 0:
            logger.info("\n✅ Next steps:")
            logger.info("1. Verify the data looks correct")
            logger.info("2. Run the sheet_transactions transformation again")
            logger.info("3. Check your BigQuery data")
        
    except Exception as e:
        logger.error(f"❌ Reverse engineering failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 