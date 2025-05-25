#!/usr/bin/env python3
"""Analyze FirstCard duplicates - read-only version that shows removal plan."""

import logging
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

from google.cloud import bigquery
from src.budget_updater.config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_firstcard_duplicates_readonly():
    """Analyze FirstCard duplicates and show removal plan without making changes."""
    try:
        config = Config()
        client = bigquery.Client(project=config.gcp_project_id)
        
        print("🔍 Analyzing FirstCard duplicates and showing removal plan...")
        print("="*70)
        
        # 1. Current status
        print("\n1️⃣ Current FirstCard transaction status:")
        
        total_query = f"""
        SELECT COUNT(*) as total_count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        """
        
        total_count = list(client.query(total_query).result())[0].total_count
        print(f"   Total FirstCard transactions: {total_count:,}")
        
        # 2. Source breakdown
        print("\n2️⃣ Source breakdown:")
        source_query = f"""
        SELECT 
          source_file,
          COUNT(*) as count,
          MIN(date) as min_date,
          MAX(date) as max_date
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        GROUP BY source_file
        ORDER BY count DESC
        """
        
        source_results = client.query(source_query).result()
        for row in source_results:
            print(f"   {row.source_file}: {row.count:,} transactions ({row.min_date} to {row.max_date})")
        
        # 3. Duplicate analysis
        print("\n3️⃣ Duplicate business_keys:")
        duplicate_keys_query = f"""
        SELECT COUNT(*) as duplicate_sets, SUM(count - 1) as extra_rows
        FROM (
          SELECT business_key, COUNT(*) as count
          FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
          WHERE account = '💳 First Card'
          GROUP BY business_key
          HAVING COUNT(*) > 1
        )
        """
        
        dup_result = list(client.query(duplicate_keys_query).result())[0]
        print(f"   Duplicate business_key sets: {dup_result.duplicate_sets}")
        print(f"   Extra duplicate rows: {dup_result.extra_rows}")
        
        # 4. Proposed removal strategy
        print("\n4️⃣ Proposed duplicate removal strategy:")
        print("   Strategy: Remove reverse engineered data from 2023-05-01 onwards")
        print("   Reason: Regular uploads start 2023-05-01, creating overlap")
        
        cutoff_date = "2023-05-01"
        
        # Count what would be removed
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
        
        print(f"\n   📊 Removal plan:")
        print(f"     - REMOVE: {remove_count:,} reverse engineered transactions >= {cutoff_date}")
        print(f"     - KEEP: {keep_rev_count:,} reverse engineered transactions < {cutoff_date}")
        print(f"     - KEEP: {keep_regular_count:,} regular upload transactions")
        print(f"     - New total: {keep_rev_count + keep_regular_count:,} transactions")
        print(f"     - Reduction: {remove_count:,} duplicate transactions ({remove_count/total_count*100:.1f}%)")
        
        # 5. Expected impact on INFLOW/OUTFLOW
        print("\n5️⃣ Expected impact on INFLOW/OUTFLOW balance:")
        
        # Current totals
        current_balance_query = f"""
        SELECT 
          SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as total_outflow,
          SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) as total_inflow
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
          AND ((outflow IS NOT NULL AND outflow != '') OR (inflow IS NOT NULL AND inflow != ''))
        """
        
        current_balance = list(client.query(current_balance_query).result())[0]
        
        # Amounts that would be removed
        remove_balance_query = f"""
        SELECT 
          SUM(CAST(REPLACE(REPLACE(outflow, ' ', ''), ',', '.') AS FLOAT64)) as remove_outflow,
          SUM(CAST(REPLACE(REPLACE(inflow, ' ', ''), ',', '.') AS FLOAT64)) as remove_inflow
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' 
          AND source_file = 'orig_google_sheet_rev_engineered'
          AND date >= '{cutoff_date}'
          AND ((outflow IS NOT NULL AND outflow != '') OR (inflow IS NOT NULL AND inflow != ''))
        """
        
        remove_balance = list(client.query(remove_balance_query).result())[0]
        
        # Calculate new totals
        new_outflow = (current_balance.total_outflow or 0) - (remove_balance.remove_outflow or 0)
        new_inflow = (current_balance.total_inflow or 0) - (remove_balance.remove_inflow or 0)
        
        print(f"   Current totals:")
        print(f"     - OUTFLOW: {current_balance.total_outflow:,.2f} kr")
        print(f"     - INFLOW: {current_balance.total_inflow:,.2f} kr")
        print(f"     - Net: {(current_balance.total_inflow or 0) - (current_balance.total_outflow or 0):,.2f} kr")
        
        print(f"   Would remove:")
        print(f"     - OUTFLOW: {remove_balance.remove_outflow:,.2f} kr")
        print(f"     - INFLOW: {remove_balance.remove_inflow:,.2f} kr")
        
        print(f"   After cleanup:")
        print(f"     - OUTFLOW: {new_outflow:,.2f} kr")
        print(f"     - INFLOW: {new_inflow:,.2f} kr")
        print(f"     - Net: {new_inflow - new_outflow:,.2f} kr")
        print(f"     - OUTFLOW/INFLOW ratio: {new_outflow/new_inflow:.2f} (should be close to 1.0)")
        
        print(f"\n{'='*70}")
        print("💡 Summary:")
        print(f"✅ Found {remove_count:,} duplicate transactions to remove")
        print(f"✅ This would improve OUTFLOW/INFLOW balance significantly")
        print(f"✅ Removal would keep historical data before {cutoff_date}")
        print(f"⚠️  To execute: Run the fix_firstcard_duplicates.py script")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    analyze_firstcard_duplicates_readonly() 