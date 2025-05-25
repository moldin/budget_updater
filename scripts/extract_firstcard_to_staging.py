#!/usr/bin/env python3
"""
Extract FirstCard transactions from Google Sheet to local staging file.

This script reads the Google Sheet Transactions tab, filters for FirstCard transactions
before a cutoff date, and saves them to a local JSON staging file for review and validation.
"""

import logging
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.budget_updater.config import Config
from src.budget_updater.sheets_api import SheetAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FirstCardStaging:
    """Extract FirstCard data from Google Sheet to staging file."""
    
    def __init__(self, config: Config):
        self.config = config
        self.sheets_api = SheetAPI()
        self.staging_dir = Path("staging")
        self.staging_dir.mkdir(exist_ok=True)
    
    def read_google_sheet_transactions(self) -> List[List]:
        """Read transactions from Google Sheet Transactions tab."""
        try:
            logger.info("📖 Connecting to Google Sheet...")
            spreadsheet_id = self.config.spreadsheet_id
            range_name = f"{self.config.transactions_sheet}!A:H"  # Columns A-H (including empty first column)
            
            result = self.sheets_api.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.warning("No data found in Transactions sheet")
                return []
            
            logger.info(f"📋 Found {len(values)} total rows in Google Sheet")
            
            # Find the header row (should be row 8: ['', 'DATE', 'OUTFLOW', 'INFLOW', 'CATEGORY', 'ACCOUNT', 'MEMO', 'STATUS'])
            header_row_index = None
            for i, row in enumerate(values):
                if len(row) > 1 and row[1] == 'DATE':  # Column B should be 'DATE'
                    header_row_index = i
                    logger.info(f"Found header at row {i+1}: {row}")
                    break
            
            if header_row_index is None:
                logger.error("Could not find header row with 'DATE' in column B")
                return []
            
            # Return data rows (everything after header)
            data_rows = values[header_row_index + 1:]
            logger.info(f"Returning {len(data_rows)} data rows")
            return data_rows
            
        except Exception as e:
            logger.error(f"Failed to read Google Sheet: {e}")
            return []
    
    def extract_firstcard_transactions(self, sheet_data: List[List], 
                                     cutoff_date: str = "2023-05-01") -> List[Dict]:
        """
        Extract and convert FirstCard transactions from sheet data.
        
        Args:
            sheet_data: Raw sheet data (after header row)
            cutoff_date: Only process transactions before this date
            
        Sheet structure (columns are 0-indexed, but sheet has empty first column):
        Col 0: '' (empty)
        Col 1: DATE 
        Col 2: OUTFLOW
        Col 3: INFLOW  
        Col 4: CATEGORY
        Col 5: ACCOUNT
        Col 6: MEMO
        Col 7: STATUS
        """
        firstcard_transactions = []
        skipped_reasons = {
            'not_firstcard': 0,
            'after_cutoff': 0,
            'no_date': 0,
            'no_amount': 0,
            'parse_error': 0,
            'empty_row': 0
        }
        
        logger.info(f"🔍 Filtering FirstCard transactions before {cutoff_date}...")
        
        for i, row in enumerate(sheet_data):
            try:
                # Ensure row has enough columns (pad with empty strings if needed)
                while len(row) < 8:
                    row.append("")
                
                # Extract fields according to actual sheet structure
                empty_col, date, outflow, inflow, category, account, memo, status = row[:8]
                
                # Skip completely empty rows
                if not any([date, outflow, inflow, category, account, memo]):
                    skipped_reasons['empty_row'] += 1
                    continue
                
                # Filter for FirstCard only
                if account != "💳 First Card":
                    skipped_reasons['not_firstcard'] += 1
                    continue
                
                # Skip if no date
                if not date:
                    skipped_reasons['no_date'] += 1
                    logger.debug(f"Row {i+2}: No date found")
                    continue
                
                # Filter by date (only before cutoff_date)
                if date >= cutoff_date:
                    skipped_reasons['after_cutoff'] += 1
                    continue
                
                # Convert amounts according to rules:
                # FirstCard: Outflow -> positive belopp, Inflow -> negative belopp
                belopp = 0.0
                amount_source = ""
                
                if outflow and outflow.strip():
                    # Outflow -> positive belopp
                    amount_str = outflow.replace(" ", "").replace(",", ".").replace("kr", "").replace("\xa0", "").strip()
                    try:
                        belopp = float(amount_str)
                        amount_source = "outflow"
                    except ValueError:
                        logger.warning(f"Row {i+2}: Could not parse outflow '{outflow}'")
                        skipped_reasons['parse_error'] += 1
                        continue
                        
                elif inflow and inflow.strip():
                    # Inflow -> negative belopp
                    amount_str = inflow.replace(" ", "").replace(",", ".").replace("kr", "").replace("\xa0", "").strip()
                    try:
                        belopp = -float(amount_str)  # Negative for inflow
                        amount_source = "inflow"
                    except ValueError:
                        logger.warning(f"Row {i+2}: Could not parse inflow '{inflow}'")
                        skipped_reasons['parse_error'] += 1
                        continue
                else:
                    skipped_reasons['no_amount'] += 1
                    logger.debug(f"Row {i+2}: No amount found")
                    continue
                
                # Combine category and memo for reseinformation_inkopsplats
                reseinformation = f"{category} - {memo}".strip(" -")
                if not reseinformation or reseinformation == " - ":
                    reseinformation = "Historical Transaction"
                
                # Create business key
                business_key = self.create_business_key(date, belopp, reseinformation, i + 2)
                
                # Create raw transaction record matching firstcard_transactions_raw schema
                raw_transaction = {
                    # Metadata fields
                    'file_hash': 'google_sheet_reverse_engineered',
                    'source_file': 'orig_google_sheet_rev_engineered',
                    'upload_timestamp': datetime.now(timezone.utc).isoformat(),
                    'row_number': i + 2,  # Sheet row number (1-based + header)
                    
                    # FirstCard specific fields
                    'datum': date,
                    'ytterligare_information': memo.strip() if memo else "",
                    'reseinformation_inkopsplats': reseinformation,
                    'valuta': 'SEK',
                    'vaxlingskurs': None,
                    'utlandskt_belopp': None,
                    'belopp': belopp,
                    'moms': None,
                    'kort': 'unknown',
                    
                    # Deduplication
                    'business_key': business_key,
                    
                    # Debug info (will be removed before upload)
                    '_debug_original_outflow': outflow,
                    '_debug_original_inflow': inflow,
                    '_debug_category': category,
                    '_debug_amount_source': amount_source,
                    '_debug_sheet_row': i + 2
                }
                
                firstcard_transactions.append(raw_transaction)
                
            except Exception as e:
                logger.error(f"Error processing row {i+2}: {e}")
                skipped_reasons['parse_error'] += 1
                continue
        
        # Log summary
        logger.info(f"📊 Extraction Summary:")
        logger.info(f"   ✅ FirstCard transactions found: {len(firstcard_transactions)}")
        logger.info(f"   ⏭️  Skipped - Not FirstCard: {skipped_reasons['not_firstcard']}")
        logger.info(f"   ⏭️  Skipped - After cutoff ({cutoff_date}): {skipped_reasons['after_cutoff']}")
        logger.info(f"   ⏭️  Skipped - No date: {skipped_reasons['no_date']}")
        logger.info(f"   ⏭️  Skipped - No amount: {skipped_reasons['no_amount']}")
        logger.info(f"   ⏭️  Skipped - Empty rows: {skipped_reasons['empty_row']}")
        logger.info(f"   ❌ Skipped - Parse errors: {skipped_reasons['parse_error']}")
        
        return firstcard_transactions
    
    def create_business_key(self, date: str, belopp: float, description: str, row_number: int) -> str:
        """Create unique business key for reverse engineered transaction."""
        # Normalize components
        date_str = str(date)[:10] if date else "unknown"
        amount_str = f"{belopp:.2f}"
        desc_normalized = description.strip().lower()[:50] if description else ""
        
        # Create business key including row number for uniqueness
        key_components = f"firstcard|{date_str}|{amount_str}|{desc_normalized}|row_{row_number}"
        business_key = hashlib.md5(key_components.encode('utf-8')).hexdigest()
        
        return f"firstcard_rev_{business_key}"
    
    def save_staging_file(self, transactions: List[Dict], cutoff_date: str) -> Path:
        """Save transactions to staging file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"firstcard_staging_{cutoff_date.replace('-', '')}_{timestamp}.json"
        staging_file = self.staging_dir / filename
        
        # Create metadata
        metadata = {
            'extraction_timestamp': datetime.now(timezone.utc).isoformat(),
            'cutoff_date': cutoff_date,
            'total_transactions': len(transactions),
            'date_range': {
                'min_date': min(t['datum'] for t in transactions) if transactions else None,
                'max_date': max(t['datum'] for t in transactions) if transactions else None
            },
            'source': 'Google Sheet Transactions tab',
            'target_table': 'firstcard_transactions_raw'
        }
        
        # Save to file
        staging_data = {
            'metadata': metadata,
            'transactions': transactions
        }
        
        try:
            with open(staging_file, 'w', encoding='utf-8') as f:
                json.dump(staging_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Staging file saved: {staging_file}")
            logger.info(f"   📏 File size: {staging_file.stat().st_size:,} bytes")
            return staging_file
            
        except Exception as e:
            logger.error(f"Failed to save staging file: {e}")
            raise
    
    def extract_to_staging(self, cutoff_date: str = "2023-05-01") -> Optional[Path]:
        """
        Main function to extract FirstCard data to staging file.
        
        Args:
            cutoff_date: Only process transactions before this date
            
        Returns:
            Path to staging file if successful, None otherwise
        """
        logger.info("🚀 Starting FirstCard staging extraction")
        
        # Step 1: Read Google Sheet
        sheet_data = self.read_google_sheet_transactions()
        if not sheet_data:
            logger.error("❌ No data found in Google Sheet")
            return None
        
        # Step 2: Extract and convert FirstCard transactions
        firstcard_transactions = self.extract_firstcard_transactions(sheet_data, cutoff_date)
        
        if not firstcard_transactions:
            logger.info("ℹ️  No FirstCard transactions found to extract")
            return None
        
        # Step 3: Save to staging file
        staging_file = self.save_staging_file(firstcard_transactions, cutoff_date)
        
        logger.info("✅ Staging extraction complete!")
        logger.info(f"📄 Next step: Validate the staging file with:")
        logger.info(f"   python scripts/validate_firstcard_staging.py {staging_file}")
        
        return staging_file


def main():
    """Run the FirstCard staging extraction."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract FirstCard data from Google Sheet to staging file")
    parser.add_argument("--cutoff-date", default="2023-05-01", 
                       help="Only extract transactions before this date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    try:
        config = Config()
        extractor = FirstCardStaging(config)
        
        staging_file = extractor.extract_to_staging(args.cutoff_date)
        
        if staging_file:
            print(f"\n🎉 SUCCESS! Staging file created: {staging_file}")
            print(f"\n📋 Review the file and run validation:")
            print(f"   python scripts/validate_firstcard_staging.py {staging_file}")
        else:
            print("❌ No staging file created")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"❌ Staging extraction failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 