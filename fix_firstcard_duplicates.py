#!/usr/bin/env python3
"""Fix FirstCard duplicates by removing overlapping transactions."""

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

from google.cloud import bigquery
from src.budget_updater.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_firstcard_duplicates():
    """Remove FirstCard duplicates with proper backup and validation."""
    try:
        config = Config()
        client = bigquery.Client(project=config.gcp_project_id)
        
        print("🔧 Fixing FirstCard duplicates...")
        print("="*70)
        
        # 1. Create backup before making changes
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_table = f"sheet_transactions_firstcard_backup_{timestamp}"
        
        print(f"\n1️⃣ Creating backup table: {backup_table}")
        backup_query = f"""
        CREATE TABLE `{config.gcp_project_id}.{config.bigquery_dataset_id}.{backup_table}` AS
        SELECT *
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        """
        
        client.query(backup_query).result()
        
        # Count backup rows
        count_query = f"""
        SELECT COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.{backup_table}`
        """
        backup_count = list(client.query(count_query).result())[0].count
        print(f"   ✅ Backed up {backup_count:,} FirstCard transactions")
        
        # 2. Analyze the duplication strategy
        print(f"\n2️⃣ Analyzing duplication patterns...")
        
        # The issue: reverse engineered data overlaps with regular data
        # Strategy: Keep regular data (firstcard.xlsx) and remove reverse engineered overlaps
        # Cutoff date: 2023-05-01 (where regular data starts being reliable)
        
        cutoff_date = "2023-05-01"
        
        # Count what we'll remove vs keep
        remove_query = f"""
        SELECT COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' 
          AND source_file = 'orig_google_sheet_rev_engineered'
          AND date >= '{cutoff_date}'
        """
        
        keep_rev_query = f"""
        SELECT COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' 
          AND source_file = 'orig_google_sheet_rev_engineered'
          AND date < '{cutoff_date}'
        """
        
        keep_regular_query = f"""
        SELECT COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' 
          AND source_file != 'orig_google_sheet_rev_engineered'
        """
        
        remove_count = list(client.query(remove_query).result())[0].count
        keep_rev_count = list(client.query(keep_rev_query).result())[0].count
        keep_regular_count = list(client.query(keep_regular_query).result())[0].count
        
        print(f"   📊 Analysis:")
        print(f"     - Will REMOVE: {remove_count:,} reverse engineered transactions >= {cutoff_date}")
        print(f"     - Will KEEP: {keep_rev_count:,} reverse engineered transactions < {cutoff_date}")
        print(f"     - Will KEEP: {keep_regular_count:,} regular upload transactions")
        print(f"     - New total: {keep_rev_count + keep_regular_count:,} transactions")
        print(f"     - Reduction: {remove_count:,} duplicate transactions")
        
        # 3. Ask for confirmation
        print(f"\n3️⃣ Confirmation required:")
        print(f"   This will remove {remove_count:,} overlapping reverse engineered transactions")
        print(f"   from {cutoff_date} onwards, keeping only the regular uploads for that period.")
        print(f"   The backup table {backup_table} will preserve all original data.")
        
        response = input("\n   Proceed with duplicate removal? (yes/no): ").strip().lower()
        
        if response != 'yes':
            print("   ❌ Operation cancelled by user")
            return
        
        # 4. Remove duplicates
        print(f"\n4️⃣ Removing duplicate transactions...")
        
        delete_query = f"""
        DELETE FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' 
          AND source_file = 'orig_google_sheet_rev_engineered'
          AND date >= '{cutoff_date}'
        """
        
        delete_result = client.query(delete_query).result()
        print(f"   ✅ Removed overlapping transactions")
        
        # 5. Verify results
        print(f"\n5️⃣ Verifying results...")
        
        # Count remaining transactions
        final_count_query = f"""
        SELECT COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        """
        final_count = list(client.query(final_count_query).result())[0].count
        
        # Check for remaining duplicates
        remaining_dups_query = f"""
        SELECT COUNT(*) as duplicate_sets
        FROM (
          SELECT business_key, COUNT(*) as count
          FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
          WHERE account = '💳 First Card'
          GROUP BY business_key
          HAVING COUNT(*) > 1
        )
        """
        remaining_dups = list(client.query(remaining_dups_query).result())[0].duplicate_sets
        
        # Recalculate INFLOW/OUTFLOW balance
        balance_query = f"""
        SELECT 
          SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as total_outflow,
          SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) as total_inflow
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
          AND outflow IS NOT NULL AND outflow != ''
          AND inflow IS NOT NULL AND inflow != ''
        """
        balance_result = list(client.query(balance_query).result())[0]
        
        print(f"   📊 Final Results:")
        print(f"     - Total transactions: {final_count:,}")
        print(f"     - Remaining duplicate business_keys: {remaining_dups}")
        print(f"     - Total OUTFLOW: {balance_result.total_outflow:,.2f} kr")
        print(f"     - Total INFLOW: {balance_result.total_inflow:,.2f} kr")
        print(f"     - Net (INFLOW - OUTFLOW): {balance_result.total_inflow - balance_result.total_outflow:,.2f} kr")
        print(f"     - Backup table: {backup_table}")
        
        if remaining_dups == 0:
            print("   ✅ All duplicates successfully removed!")
        else:
            print(f"   ⚠️  {remaining_dups} duplicate sets still remain - may need manual review")
        
        print(f"\n{'='*70}")
        print("✅ FirstCard duplicate fix completed!")
        print(f"💾 Backup available in table: {backup_table}")
        
    except Exception as e:
        logger.error(f"Duplicate fix failed: {e}")
        print(f"\n❌ Error: {e}")
        print("Check the backup table if any changes were made.")

if __name__ == "__main__":
    fix_firstcard_duplicates() 