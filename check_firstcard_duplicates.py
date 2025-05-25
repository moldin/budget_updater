#!/usr/bin/env python3
"""Check for duplicates and data integrity issues in FirstCard transactions."""

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

def check_firstcard_duplicates():
    """Check for various types of duplicates in FirstCard data."""
    try:
        config = Config()
        client = bigquery.Client(project=config.gcp_project_id)
        
        print("🔍 Analyzing FirstCard transactions for duplicates and issues...")
        print("="*70)
        
        # 1. Check for duplicate business_keys
        print("\n1️⃣ Checking for duplicate business_keys:")
        duplicate_keys_query = f"""
        SELECT 
          business_key, 
          COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        GROUP BY business_key
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        """
        
        result = client.query(duplicate_keys_query).result()
        duplicate_keys = list(result)
        
        if duplicate_keys:
            print(f"   ❌ Found {len(duplicate_keys)} duplicate business_keys!")
            total_extra = sum(row.count - 1 for row in duplicate_keys)
            print(f"   📊 Total extra duplicate rows: {total_extra}")
            
            for row in duplicate_keys[:5]:  # Show first 5
                print(f"     Key: {row.business_key} appears {row.count} times")
                
                # Get sample transactions for this key
                sample_query = f"""
                SELECT date, outflow, inflow, memo, source_file
                FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
                WHERE business_key = '{row.business_key}'
                ORDER BY date
                """
                sample_result = client.query(sample_query).result()
                for i, txn in enumerate(sample_result):
                    if i < 3:  # Show first 3 for each key
                        source_short = txn.source_file[:15] + "..." if len(txn.source_file) > 15 else txn.source_file
                        print(f"       {txn.date} | Out: {txn.outflow} | In: {txn.inflow} | {source_short}")
        else:
            print("   ✅ No duplicate business_keys found")
        
        # 2. Check for duplicate transactions by date + amount + memo
        print("\n2️⃣ Checking for duplicate transactions (same date, amount, memo):")
        duplicate_content_query = f"""
        SELECT 
          date, 
          outflow, 
          inflow, 
          memo,
          COUNT(*) as count,
          ARRAY_AGG(business_key) as business_keys
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        GROUP BY date, outflow, inflow, memo
        HAVING COUNT(*) > 1
        ORDER BY count DESC, date DESC
        """
        
        result = client.query(duplicate_content_query).result()
        duplicate_content = list(result)
        
        if duplicate_content:
            print(f"   ❌ Found {len(duplicate_content)} sets of duplicate transactions!")
            total_duplicates = sum(row.count - 1 for row in duplicate_content)  # Extra copies
            print(f"   📊 Total extra duplicate transactions: {total_duplicates}")
            
            for row in duplicate_content[:10]:  # Show first 10
                print(f"     {row.date} | Out: {row.outflow} | In: {row.inflow} | {row.memo[:30]} (appears {row.count} times)")
        else:
            print("   ✅ No duplicate transaction content found")
        
        # 3. Check source distribution
        print("\n3️⃣ Checking source distribution:")
        source_query = f"""
        SELECT 
          source_bank,
          source_file,
          COUNT(*) as count,
          MIN(date) as min_date,
          MAX(date) as max_date
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        GROUP BY source_bank, source_file
        ORDER BY count DESC
        """
        
        result = client.query(source_query).result()
        for row in result:
            print(f"   {row.source_bank} | {row.source_file} | {row.count:,} transactions | {row.min_date} to {row.max_date}")
        
        # 4. Check for overlapping date ranges between sources
        print("\n4️⃣ Checking for potential date overlaps between sources:")
        reverse_eng_query = f"""
        SELECT COUNT(*) as reverse_eng_count, MIN(date) as min_date, MAX(date) as max_date
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' AND source_file = 'orig_google_sheet_rev_engineered'
        """
        
        regular_query = f"""
        SELECT COUNT(*) as regular_count, MIN(date) as min_date, MAX(date) as max_date
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card' AND source_file != 'orig_google_sheet_rev_engineered'
        """
        
        reverse_result = list(client.query(reverse_eng_query).result())[0]
        regular_result = list(client.query(regular_query).result())[0]
        
        print(f"   Reverse engineered: {reverse_result.reverse_eng_count:,} transactions ({reverse_result.min_date} to {reverse_result.max_date})")
        print(f"   Regular uploads: {regular_result.regular_count:,} transactions ({regular_result.min_date} to {regular_result.max_date})")
        
        # Check for overlap
        if (reverse_result.max_date and regular_result.min_date and 
            reverse_result.max_date >= regular_result.min_date):
            print(f"   ⚠️  POTENTIAL OVERLAP detected! Reverse eng ends {reverse_result.max_date}, regular starts {regular_result.min_date}")
            
            # Check specific overlap
            overlap_query = f"""
            SELECT date, COUNT(*) as count
            FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
            WHERE account = '💳 First Card' 
              AND date BETWEEN '{regular_result.min_date}' AND '{reverse_result.max_date}'
            GROUP BY date
            HAVING COUNT(*) > 1
            ORDER BY date
            LIMIT 10
            """
            
            overlap_result = client.query(overlap_query).result()
            overlap_dates = list(overlap_result)
            
            if overlap_dates:
                print(f"   ❌ Found overlapping dates with multiple transactions:")
                for row in overlap_dates:
                    print(f"     {row.date}: {row.count} transactions")
        else:
            print("   ✅ No date overlap between reverse engineered and regular data")
        
        # 5. Sample recent transactions to verify
        print("\n5️⃣ Sample of most recent transactions:")
        recent_query = f"""
        SELECT date, outflow, inflow, memo, source_file, business_key
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        ORDER BY date DESC, business_key
        LIMIT 15
        """
        
        result = client.query(recent_query).result()
        for row in result:
            source_short = row.source_file[:20] + "..." if len(row.source_file) > 20 else row.source_file
            print(f"   {row.date} | Out: {row.outflow:>12} | In: {row.inflow:>12} | {source_short} | {row.memo[:25]}")
        
        print(f"\n{'='*70}")
        print("💡 Recommendations:")
        
        if duplicate_keys or duplicate_content:
            print("❌ DUPLICATES FOUND - This likely explains the OUTFLOW/INFLOW imbalance")
            print("   Suggest: Remove duplicates or investigate source data")
        else:
            print("✅ No obvious duplicates found")
            print("   Suggest: Check transformation logic or date range definitions")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")

if __name__ == "__main__":
    check_firstcard_duplicates() 