#!/usr/bin/env python3
"""
Query transaction data from BigQuery.

This script provides common queries for analyzing transaction data stored in BigQuery.

Usage:
    python scripts/query_transactions.py [query_name] [--limit N] [--output csv]
    
Examples:
    python scripts/query_transactions.py summary
    python scripts/query_transactions.py recent --limit 10
    python scripts/query_transactions.py by_bank --output csv
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from google.cloud import bigquery

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))
from budget_updater.config import Config

class TransactionQueryManager:
    """Manages common queries for transaction data."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
        self.table_id = "transactions_standardized"  # V2 architecture
        self.full_table_name = f"{config.gcp_project_id}.{config.bigquery_dataset_id}.{self.table_id}"
    
    def get_summary(self, limit: int = None) -> None:
        """Get summary statistics of all transactions."""
        query = f"""
        SELECT 
            source_bank,
            COUNT(*) as transaction_count,
            MIN(transaction_date) as earliest_date,
            MAX(transaction_date) as latest_date,
            ROUND(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) as total_outflow,
            ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) as total_inflow,
            ROUND(SUM(amount), 2) as net_amount,
            ROUND(AVG(amount), 2) as avg_amount
        FROM `{self.full_table_name}`
        GROUP BY source_bank
        ORDER BY transaction_count DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        
        result = self.client.query(query).result()
        
        print(f"{'Bank':<12} {'Count':<8} {'Earliest':<12} {'Latest':<12} {'Outflow':<12} {'Inflow':<12} {'Net':<12} {'Avg':<10}")
        print("-" * 90)
        
        for row in result:
            print(f"{row.source_bank:<12} {row.transaction_count:<8} {str(row.earliest_date):<12} {str(row.latest_date):<12} {row.total_outflow:<12} {row.total_inflow:<12} {row.net_amount:<12} {row.avg_amount:<10}")
    
    def get_recent_transactions(self, limit: int = 20) -> None:
        """Get most recent transactions across all banks."""
        query = f"""
        SELECT 
            transaction_date,
            source_bank,
            description,
            amount,
            currency
        FROM `{self.full_table_name}`
        ORDER BY transaction_date DESC
        LIMIT {limit}
        """
        
        result = self.client.query(query).result()
        
        print(f"{'Date':<12} {'Bank':<8} {'Description':<40} {'Amount':<12} {'Currency':<8}")
        print("-" * 85)
        
        for row in result:
            desc = (row.description[:37] + "...") if len(row.description) > 40 else row.description
            print(f"{str(row.transaction_date):<12} {row.source_bank:<8} {desc:<40} {row.amount:<12} {row.currency:<8}")
    
    def get_transactions_by_bank(self, bank: str = None, limit: int = None) -> pd.DataFrame:
        """Get transactions for a specific bank or all banks."""
        where_clause = f"WHERE source_bank = '{bank}'" if bank else ""
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        query = f"""
        SELECT 
            transaction_date,
            source_bank,
            description,
            amount,
            currency,
            source_file,
            merchant_name,
            location
        FROM `{self.full_table_name}`
        {where_clause}
        ORDER BY transaction_date DESC
        {limit_clause}
        """
        
        return self.client.query(query).to_dataframe()
    
    def get_monthly_summary(self, limit: int = 12) -> pd.DataFrame:
        """Get monthly transaction summary using V2 views."""
        query = f"""
        SELECT 
            year,
            month,
            source_bank,
            transaction_count,
            total_expenses,
            total_income,
            net_amount
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.monthly_summary`
        ORDER BY year DESC, month DESC, source_bank
        LIMIT {limit}
        """
        
        return self.client.query(query).to_dataframe()
    
    def get_large_transactions(self, threshold: float = 1000, limit: int = 50) -> pd.DataFrame:
        """Get transactions above a certain threshold."""
        query = f"""
        SELECT 
            transaction_date,
            source_bank,
            description,
            amount,
            ABS(amount) as abs_amount
        FROM `{self.full_table_name}`
        WHERE ABS(amount) >= {threshold}
        ORDER BY abs_amount DESC
        LIMIT {limit}
        """
        
        return self.client.query(query).to_dataframe()
    
    def get_file_processing_status(self, limit: int = 20) -> pd.DataFrame:
        """Get file processing history."""
        query = f"""
        SELECT 
            filename,
            source_bank,
            processed_timestamp,
            staging_records_processed,
            standardized_records_processed,
            processing_status,
            ROUND(file_size_bytes / 1024.0, 2) as file_size_kb,
            error_message
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.file_processing_log`
        ORDER BY processed_timestamp DESC
        LIMIT {limit}
        """
        
        return self.client.query(query).to_dataframe()
    
    def search_transactions(self, search_term: str, limit: int = 50) -> pd.DataFrame:
        """Search transactions by description."""
        query = f"""
        SELECT 
            transaction_date,
            source_bank,
            description,
            amount,
            merchant_name,
            location
        FROM `{self.full_table_name}`
        WHERE LOWER(description) LIKE LOWER('%{search_term}%')
           OR LOWER(merchant_name) LIKE LOWER('%{search_term}%')
        ORDER BY transaction_date DESC
        LIMIT {limit}
        """
        
        return self.client.query(query).to_dataframe()

def main():
    parser = argparse.ArgumentParser(description="Query transaction data from BigQuery")
    parser.add_argument("query", choices=[
        'summary', 'recent', 'by_bank', 'monthly', 'large', 'files', 'search'
    ], help="Type of query to run")
    parser.add_argument("--limit", type=int, help="Limit number of results")
    parser.add_argument("--bank", choices=['seb', 'revolut', 'firstcard', 'strawberry'], 
                       help="Filter by specific bank (for by_bank query)")
    parser.add_argument("--threshold", type=float, default=1000, 
                       help="Amount threshold for large transactions")
    parser.add_argument("--search", help="Search term for transaction descriptions")
    parser.add_argument("--output", choices=['table', 'csv'], default='table',
                       help="Output format")
    
    args = parser.parse_args()
    
    try:
        config = Config()
        query_manager = TransactionQueryManager(config)
        
        # Execute the selected query
        if args.query == 'summary':
            print("\n📊 TRANSACTION SUMMARY BY BANK")
            print("=" * 60)
            query_manager.get_summary(args.limit)
            
        elif args.query == 'recent':
            limit = args.limit or 20
            print(f"\n📅 {limit} MOST RECENT TRANSACTIONS")
            print("=" * 60)
            query_manager.get_recent_transactions(limit)
            
        elif args.query == 'by_bank':
            df = query_manager.get_transactions_by_bank(args.bank, args.limit)
            bank_name = args.bank.upper() if args.bank else "ALL BANKS"
            print(f"\n🏦 TRANSACTIONS FOR {bank_name}")
            print("=" * 60)
            
            # Output results for dataframe queries
            if df.empty:
                print("No results found.")
            else:
                if args.output == 'csv':
                    filename = f"query_results_{args.query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"Results saved to {filename}")
                else:
                    print(df.to_string(index=False))
                
                print(f"\nTotal records: {len(df)}")
            
        elif args.query == 'monthly':
            limit = args.limit or 12
            df = query_manager.get_monthly_summary(limit)
            print(f"\n📈 MONTHLY TRANSACTION SUMMARY (Last {limit} months)")
            print("=" * 60)
            
            # Output results for dataframe queries
            if df.empty:
                print("No results found.")
            else:
                if args.output == 'csv':
                    filename = f"query_results_{args.query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"Results saved to {filename}")
                else:
                    print(df.to_string(index=False))
                
                print(f"\nTotal records: {len(df)}")
            
        elif args.query == 'large':
            df = query_manager.get_large_transactions(args.threshold, args.limit or 50)
            print(f"\n💰 LARGE TRANSACTIONS (>= {args.threshold} SEK)")
            print("=" * 60)
            
            # Output results for dataframe queries
            if df.empty:
                print("No results found.")
            else:
                if args.output == 'csv':
                    filename = f"query_results_{args.query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"Results saved to {filename}")
                else:
                    print(df.to_string(index=False))
                
                print(f"\nTotal records: {len(df)}")
            
        elif args.query == 'files':
            limit = args.limit or 20
            df = query_manager.get_file_processing_status(limit)
            print(f"\n📁 FILE PROCESSING STATUS")
            print("=" * 60)
            
            # Output results for dataframe queries
            if df.empty:
                print("No results found.")
            else:
                if args.output == 'csv':
                    filename = f"query_results_{args.query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"Results saved to {filename}")
                else:
                    print(df.to_string(index=False))
                
                print(f"\nTotal records: {len(df)}")
            
        elif args.query == 'search':
            if not args.search:
                print("❌ --search parameter required for search query")
                sys.exit(1)
            df = query_manager.search_transactions(args.search, args.limit or 50)
            print(f"\n🔍 TRANSACTIONS MATCHING '{args.search}'")
            print("=" * 60)
            
            # Output results for dataframe queries
            if df.empty:
                print("No results found.")
            else:
                if args.output == 'csv':
                    filename = f"query_results_{args.query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"Results saved to {filename}")
                else:
                    print(df.to_string(index=False))
                
                print(f"\nTotal records: {len(df)}")
    
    except Exception as e:
        print(f"❌ Query failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 