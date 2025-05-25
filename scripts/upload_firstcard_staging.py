#!/usr/bin/env python3
"""
Upload validated FirstCard staging file to BigQuery.

This script takes a validated staging file and safely uploads the transactions
to the firstcard_transactions_raw BigQuery table with backup and safety features.
"""

import logging
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from google.cloud import bigquery
from src.budget_updater.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FirstCardUploader:
    """Upload validated FirstCard staging file to BigQuery."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
        self.table_id = 'firstcard_transactions_raw'
    
    def load_staging_file(self, staging_file: Path) -> Dict:
        """Load and parse staging file."""
        try:
            logger.info(f"📖 Loading staging file: {staging_file}")
            
            if not staging_file.exists():
                raise FileNotFoundError(f"Staging file not found: {staging_file}")
            
            with open(staging_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"✅ Loaded staging file ({staging_file.stat().st_size:,} bytes)")
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in staging file: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load staging file: {e}")
    
    def check_validation_report(self, staging_file: Path) -> bool:
        """Check if there's a validation report and if it passed."""
        report_file = staging_file.with_suffix('.validation_report.json')
        
        if not report_file.exists():
            logger.warning("⚠️  No validation report found - recommend running validation first")
            return self.prompt_continue("Continue without validation report?")
        
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                report = json.load(f)
            
            is_valid = report.get('validation_results', {}).get('is_valid', False)
            error_count = report.get('validation_results', {}).get('error_count', 0)
            warning_count = report.get('validation_results', {}).get('warning_count', 0)
            duplicate_count = report.get('validation_results', {}).get('duplicate_count', 0)
            
            logger.info(f"📄 Validation Report Summary:")
            logger.info(f"   Valid: {'✅' if is_valid else '❌'}")
            logger.info(f"   Errors: {error_count}")
            logger.info(f"   Warnings: {warning_count}")
            logger.info(f"   Duplicates: {duplicate_count}")
            
            if not is_valid:
                logger.error("❌ Validation report shows errors - cannot upload")
                return False
            
            if duplicate_count > 0:
                logger.warning(f"⚠️  Validation report shows {duplicate_count} duplicates")
                return self.prompt_continue(f"Continue upload with {duplicate_count} duplicates?")
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️  Could not read validation report: {e}")
            return self.prompt_continue("Continue without readable validation report?")
    
    def prompt_continue(self, message: str) -> bool:
        """Prompt user to continue (for interactive mode)."""
        try:
            response = input(f"{message} (y/N): ").strip().lower()
            return response in ['y', 'yes']
        except (EOFError, KeyboardInterrupt):
            return False
    
    def create_backup(self) -> Optional[str]:
        """Create backup of existing firstcard_transactions_raw table."""
        backup_table = f"firstcard_transactions_raw_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # First check if source table exists and has data
        check_query = f"""
        SELECT COUNT(*) as count
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.{self.table_id}`
        """
        
        try:
            result = list(self.client.query(check_query).result())
            row_count = result[0].count if result else 0
            
            if row_count == 0:
                logger.info("ℹ️  No existing data to backup")
                return None
            
            logger.info(f"📦 Creating backup of {row_count:,} existing rows...")
            
            backup_query = f"""
            CREATE TABLE `{self.config.gcp_project_id}.{self.dataset_id}.{backup_table}` AS
            SELECT * FROM `{self.config.gcp_project_id}.{self.dataset_id}.{self.table_id}`
            """
            
            job = self.client.query(backup_query)
            job.result()  # Wait for completion
            
            logger.info(f"✅ Created backup table: {backup_table}")
            return backup_table
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise
    
    def prepare_transactions_for_upload(self, transactions: List[Dict]) -> List[Dict]:
        """Prepare transactions for BigQuery upload by cleaning debug fields."""
        clean_transactions = []
        
        for transaction in transactions:
            # Remove debug fields and update timestamp
            clean_transaction = {k: v for k, v in transaction.items() 
                               if not k.startswith('_debug')}
            
            # Update upload timestamp to current time
            clean_transaction['upload_timestamp'] = datetime.now(timezone.utc).isoformat()
            
            clean_transactions.append(clean_transaction)
        
        return clean_transactions
    
    def check_for_existing_duplicates(self, transactions: List[Dict]) -> List[str]:
        """Check for existing duplicates in BigQuery."""
        business_keys = [t.get('business_key') for t in transactions if t.get('business_key')]
        
        if not business_keys:
            return []
        
        try:
            placeholders = ', '.join([f"'{key}'" for key in business_keys])
            query = f"""
            SELECT business_key
            FROM `{self.config.gcp_project_id}.{self.dataset_id}.{self.table_id}`
            WHERE business_key IN ({placeholders})
            """
            
            result = self.client.query(query).result()
            existing_keys = [row.business_key for row in result]
            
            return existing_keys
            
        except Exception as e:
            logger.warning(f"Could not check for duplicates: {e}")
            return []
    
    def filter_out_duplicates(self, transactions: List[Dict], 
                            existing_keys: List[str]) -> List[Dict]:
        """Filter out transactions that already exist."""
        if not existing_keys:
            return transactions
        
        existing_set = set(existing_keys)
        new_transactions = [t for t in transactions 
                          if t.get('business_key') not in existing_set]
        
        duplicate_count = len(transactions) - len(new_transactions)
        if duplicate_count > 0:
            logger.info(f"🔍 Filtered out {duplicate_count} existing duplicates")
        
        return new_transactions
    
    def upload_transactions(self, transactions: List[Dict]) -> int:
        """Upload transactions to BigQuery table."""
        if not transactions:
            logger.info("ℹ️  No transactions to upload")
            return 0
        
        table_ref = self.client.dataset(self.dataset_id).table(self.table_id)
        
        try:
            logger.info(f"📤 Uploading {len(transactions)} transactions to BigQuery...")
            
            errors = self.client.insert_rows_json(table_ref, transactions)
            
            if errors:
                logger.error(f"❌ Failed to insert rows:")
                for error in errors:
                    logger.error(f"   {error}")
                return 0
            
            logger.info(f"✅ Successfully uploaded {len(transactions)} transactions")
            return len(transactions)
            
        except Exception as e:
            logger.error(f"❌ Failed to upload transactions: {e}")
            raise
    
    def create_upload_summary(self, staging_file: Path, uploaded_count: int, 
                            backup_table: Optional[str]) -> Dict:
        """Create upload summary report."""
        summary = {
            'upload_timestamp': datetime.now(timezone.utc).isoformat(),
            'staging_file': str(staging_file),
            'uploaded_transactions': uploaded_count,
            'backup_table': backup_table,
            'target_table': f"{self.config.gcp_project_id}.{self.dataset_id}.{self.table_id}"
        }
        
        return summary
    
    def save_upload_summary(self, staging_file: Path, summary: Dict) -> Path:
        """Save upload summary to file."""
        summary_file = staging_file.with_suffix('.upload_summary.json')
        
        try:
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📄 Upload summary saved: {summary_file}")
            return summary_file
            
        except Exception as e:
            logger.error(f"Failed to save upload summary: {e}")
            raise
    
    def upload_staging_file(self, staging_file: Path, 
                          create_backup: bool = True,
                          skip_duplicates: bool = True,
                          dry_run: bool = False) -> int:
        """
        Main function to upload staging file to BigQuery.
        
        Args:
            staging_file: Path to staging file
            create_backup: Whether to create backup before upload
            skip_duplicates: Whether to filter out existing duplicates
            dry_run: If True, don't actually upload (just validate and prepare)
            
        Returns:
            Number of transactions uploaded
        """
        logger.info("🚀 Starting FirstCard staging file upload")
        
        # Step 1: Check validation report
        if not self.check_validation_report(staging_file):
            logger.error("❌ Validation check failed, aborting upload")
            return 0
        
        # Step 2: Load staging file
        data = self.load_staging_file(staging_file)
        transactions = data.get('transactions', [])
        metadata = data.get('metadata', {})
        
        if not transactions:
            logger.info("ℹ️  No transactions to upload")
            return 0
        
        logger.info(f"📋 Found {len(transactions)} transactions in staging file")
        
        # Step 3: Create backup if requested
        backup_table = None
        if create_backup and not dry_run:
            backup_table = self.create_backup()
        
        # Step 4: Prepare transactions
        clean_transactions = self.prepare_transactions_for_upload(transactions)
        
        # Step 5: Check for duplicates
        if skip_duplicates:
            logger.info("🔍 Checking for existing duplicates...")
            existing_keys = self.check_for_existing_duplicates(clean_transactions)
            clean_transactions = self.filter_out_duplicates(clean_transactions, existing_keys)
        
        if not clean_transactions:
            logger.info("ℹ️  No new transactions to upload after duplicate filtering")
            return 0
        
        # Step 6: Upload (or simulate for dry run)
        if dry_run:
            logger.info(f"🧪 DRY RUN: Would upload {len(clean_transactions)} transactions")
            uploaded_count = len(clean_transactions)
        else:
            uploaded_count = self.upload_transactions(clean_transactions)
        
        # Step 7: Create summary
        if uploaded_count > 0:
            summary = self.create_upload_summary(staging_file, uploaded_count, backup_table)
            if not dry_run:
                self.save_upload_summary(staging_file, summary)
        
        if dry_run:
            logger.info("🧪 DRY RUN completed successfully")
        else:
            logger.info("✅ Upload completed successfully")
            logger.info("\n📋 Next steps:")
            logger.info("1. Verify data in BigQuery")
            logger.info("2. Run sheet_transactions transformation")
            logger.info("3. Check your budget analysis")
        
        return uploaded_count


def main():
    """Run the FirstCard staging file upload."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload validated FirstCard staging file to BigQuery")
    parser.add_argument("staging_file", help="Path to validated staging file")
    parser.add_argument("--no-backup", action="store_true", 
                       help="Skip creating backup table")
    parser.add_argument("--allow-duplicates", action="store_true",
                       help="Don't filter out existing duplicates")
    parser.add_argument("--dry-run", action="store_true",
                       help="Simulate upload without actually inserting data")
    parser.add_argument("--force", action="store_true",
                       help="Skip interactive prompts (for automated runs)")
    
    args = parser.parse_args()
    
    try:
        staging_file = Path(args.staging_file)
        
        if not staging_file.exists():
            logger.error(f"❌ Staging file not found: {staging_file}")
            sys.exit(1)
        
        config = Config()
        uploader = FirstCardUploader(config)
        
        # For automated runs, override prompt behavior
        if args.force:
            uploader.prompt_continue = lambda msg: True
        
        uploaded_count = uploader.upload_staging_file(
            staging_file=staging_file,
            create_backup=not args.no_backup,
            skip_duplicates=not args.allow_duplicates,
            dry_run=args.dry_run
        )
        
        if uploaded_count > 0:
            print(f"\n🎉 SUCCESS! Uploaded {uploaded_count} transactions")
            
            if not args.dry_run:
                print(f"\n📋 Check your data:")
                print(f"   BigQuery table: {config.gcp_project_id}.{config.bigquery_dataset_id}.firstcard_transactions_raw")
                print(f"\n📋 Next step - update sheet_transactions:")
                print(f"   python scripts/transform_to_sheet_transactions.py")
        else:
            print("ℹ️  No transactions uploaded")
        
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 