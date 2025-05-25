#!/usr/bin/env python3
"""
Transform raw bank data to Google Sheet "Transactions" format.

This script provides functions to transform raw transaction data from different banks
into the format expected by the Google Sheet "Transactions" table.

Rules for INFLOW/OUTFLOW:
- SEB['Belopp'] & Revolut['Amount']: negative → OUTFLOW, positive → INFLOW  
- FirstCard['Belopp'] & Strawberry['Belopp']: negative → INFLOW, positive → OUTFLOW
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

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


class SheetTransactionTransformer:
    """Transforms raw bank data to Google Sheet Transactions format."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
    
    def format_amount(self, amount: float) -> str:
        """Format amount as string with Swedish number formatting."""
        if amount == 0:
            return ""
        return f"{abs(amount):,.2f}".replace(',', ' ')
    
    def transform_seb_to_sheet_transactions_sql(self) -> str:
        """
        Generate SQL to transform SEB raw data to sheet_transactions format.
        SEB Rule: negative belopp → OUTFLOW, positive belopp → INFLOW
        """
        return f"""
        INSERT INTO `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions`
        (
            date, outflow, inflow, category, account, memo, status,
            business_key, source_bank, source_file, upload_timestamp, file_hash,
            amount_numeric, currency, transaction_month, transaction_year
        )
        SELECT 
            PARSE_DATE('%Y-%m-%d', SUBSTR(bokforingsdatum, 1, 10)) as date,
            CASE 
                WHEN belopp < 0 THEN FORMAT("%.2f", ABS(belopp))
                ELSE ""
            END as outflow,
            CASE 
                WHEN belopp >= 0 THEN FORMAT("%.2f", belopp)
                ELSE ""
            END as inflow,
            "" as category,  -- To be set later
            "💰 SEB" as account,
            COALESCE(text, "") as memo,
            "✅" as status,
            business_key,
            "seb" as source_bank,
            source_file,
            CURRENT_TIMESTAMP() as upload_timestamp,
            file_hash,
            belopp as amount_numeric,
            "SEK" as currency,
            DATE_TRUNC(PARSE_DATE('%Y-%m-%d', SUBSTR(bokforingsdatum, 1, 10)), MONTH) as transaction_month,
            EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', SUBSTR(bokforingsdatum, 1, 10))) as transaction_year
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.seb_transactions_raw`
        WHERE bokforingsdatum IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions` st
            WHERE st.business_key = `{self.config.gcp_project_id}.{self.dataset_id}.seb_transactions_raw`.business_key
        )
        """
    
    def transform_revolut_to_sheet_transactions_sql(self) -> str:
        """
        Generate SQL to transform Revolut raw data to sheet_transactions format.
        Revolut Rule: negative amount → OUTFLOW, positive amount → INFLOW
        """
        return f"""
        INSERT INTO `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions`
        (
            date, outflow, inflow, category, account, memo, status,
            business_key, source_bank, source_file, upload_timestamp, file_hash,
            amount_numeric, currency, transaction_month, transaction_year
        )
        SELECT 
            PARSE_DATE('%Y-%m-%d', SUBSTR(completed_date, 1, 10)) as date,
            CASE 
                WHEN (amount - COALESCE(fee, 0)) < 0 THEN FORMAT("%.2f", ABS(amount - COALESCE(fee, 0)))
                ELSE ""
            END as outflow,
            CASE 
                WHEN (amount - COALESCE(fee, 0)) >= 0 THEN FORMAT("%.2f", (amount - COALESCE(fee, 0)))
                ELSE ""
            END as inflow,
            "" as category,  -- To be set later
            "💳 Revolut" as account,
            COALESCE(description, "") as memo,
            "✅" as status,
            business_key,
            "revolut" as source_bank,
            source_file,
            CURRENT_TIMESTAMP() as upload_timestamp,
            file_hash,
            (amount - COALESCE(fee, 0)) as amount_numeric,
            COALESCE(currency, "SEK") as currency,
            DATE_TRUNC(PARSE_DATE('%Y-%m-%d', SUBSTR(completed_date, 1, 10)), MONTH) as transaction_month,
            EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', SUBSTR(completed_date, 1, 10))) as transaction_year
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.revolut_transactions_raw`
        WHERE completed_date IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions` st
            WHERE st.business_key = `{self.config.gcp_project_id}.{self.dataset_id}.revolut_transactions_raw`.business_key
        )
        """
    
    def transform_firstcard_to_sheet_transactions_sql(self) -> str:
        """
        Generate SQL to transform FirstCard raw data to sheet_transactions format.
        FirstCard Rule: negative belopp → INFLOW, positive belopp → OUTFLOW
        """
        return f"""
        INSERT INTO `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions`
        (
            date, outflow, inflow, category, account, memo, status,
            business_key, source_bank, source_file, upload_timestamp, file_hash,
            amount_numeric, currency, transaction_month, transaction_year
        )
        SELECT 
            PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10)) as date,
            CASE 
                WHEN belopp > 0 THEN FORMAT("%.2f", belopp)  -- REVERSED: positive → OUTFLOW
                ELSE ""
            END as outflow,
            CASE 
                WHEN belopp < 0 THEN FORMAT("%.2f", ABS(belopp))  -- REVERSED: negative → INFLOW
                ELSE ""
            END as inflow,
            "" as category,  -- To be set later
            "💳 First Card" as account,
            COALESCE(
                reseinformation_inkopsplats, 
                ytterligare_information, 
                "FirstCard Transaction"
            ) as memo,
            "✅" as status,
            business_key,
            "firstcard" as source_bank,
            source_file,
            CURRENT_TIMESTAMP() as upload_timestamp,
            file_hash,
            belopp as amount_numeric,
            COALESCE(valuta, "SEK") as currency,
            DATE_TRUNC(PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10)), MONTH) as transaction_month,
            EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10))) as transaction_year
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.firstcard_transactions_raw`
        WHERE datum IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions` st
            WHERE st.business_key = `{self.config.gcp_project_id}.{self.dataset_id}.firstcard_transactions_raw`.business_key
        )
        """
    
    def transform_strawberry_to_sheet_transactions_sql(self) -> str:
        """
        Generate SQL to transform Strawberry raw data to sheet_transactions format.
        Strawberry Rule: negative belopp → INFLOW, positive belopp → OUTFLOW
        """
        return f"""
        INSERT INTO `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions`
        (
            date, outflow, inflow, category, account, memo, status,
            business_key, source_bank, source_file, upload_timestamp, file_hash,
            amount_numeric, currency, transaction_month, transaction_year
        )
        SELECT 
            PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10)) as date,
            CASE 
                WHEN belopp > 0 THEN FORMAT("%.2f", belopp)  -- REVERSED: positive → OUTFLOW
                ELSE ""
            END as outflow,
            CASE 
                WHEN belopp < 0 THEN FORMAT("%.2f", ABS(belopp))  -- REVERSED: negative → INFLOW
                ELSE ""
            END as inflow,
            "" as category,  -- To be set later
            "💳 Strawberry" as account,
            COALESCE(specifikation, "") as memo,
            "✅" as status,
            business_key,
            "strawberry" as source_bank,
            source_file,
            CURRENT_TIMESTAMP() as upload_timestamp,
            file_hash,
            belopp as amount_numeric,
            COALESCE(valuta, "SEK") as currency,
            DATE_TRUNC(PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10)), MONTH) as transaction_month,
            EXTRACT(YEAR FROM PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10))) as transaction_year
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.strawberry_transactions_raw`
        WHERE datum IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions` st
            WHERE st.business_key = `{self.config.gcp_project_id}.{self.dataset_id}.strawberry_transactions_raw`.business_key
        )
        """
    
    def transform_bank_to_sheet_transactions(self, source_bank: str) -> int:
        """
        Transform all data from a specific bank's staging table to sheet_transactions.
        
        Args:
            source_bank: Bank source ('seb', 'revolut', 'firstcard', 'strawberry')
            
        Returns:
            Number of rows inserted
        """
        sql_map = {
            'seb': self.transform_seb_to_sheet_transactions_sql,
            'revolut': self.transform_revolut_to_sheet_transactions_sql,
            'firstcard': self.transform_firstcard_to_sheet_transactions_sql,
            'strawberry': self.transform_strawberry_to_sheet_transactions_sql
        }
        
        if source_bank not in sql_map:
            raise ValueError(f"Unknown source bank: {source_bank}")
        
        sql_query = sql_map[source_bank]()
        
        logger.info(f"Transforming {source_bank} data to sheet_transactions...")
        
        try:
            # Execute the transformation query
            job = self.client.query(sql_query)
            result = job.result()  # Wait for completion
            
            # Get the number of rows inserted
            rows_inserted = job.num_dml_affected_rows or 0
            
            logger.info(f"✅ Successfully transformed {rows_inserted} {source_bank} transactions")
            return rows_inserted
            
        except Exception as e:
            logger.error(f"❌ Failed to transform {source_bank} data: {e}")
            raise
    
    def transform_all_banks_to_sheet_transactions(self) -> Dict[str, int]:
        """
        Transform all bank data to sheet_transactions table.
        
        Returns:
            Dictionary mapping bank names to number of rows inserted
        """
        banks = ['seb', 'revolut', 'firstcard', 'strawberry']
        results = {}
        total_inserted = 0
        
        for bank in banks:
            try:
                rows_inserted = self.transform_bank_to_sheet_transactions(bank)
                results[bank] = rows_inserted
                total_inserted += rows_inserted
                
                if rows_inserted > 0:
                    logger.info(f"✅ {bank.upper()}: {rows_inserted} transactions inserted")
                else:
                    logger.info(f"ℹ️  {bank.upper()}: No new transactions to insert")
                    
            except Exception as e:
                logger.error(f"❌ {bank.upper()}: Failed - {e}")
                results[bank] = 0
        
        logger.info(f"\n🎉 Total transactions inserted: {total_inserted}")
        return results
    
    def get_sample_transactions(self, limit: int = 10) -> None:
        """Show sample transactions from the sheet_transactions table."""
        query = f"""
        SELECT 
            date, outflow, inflow, category, account, memo, status,
            source_bank, amount_numeric, currency
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.sheet_transactions`
        ORDER BY date DESC
        LIMIT {limit}
        """
        
        logger.info(f"📊 Sample transactions from sheet_transactions table:")
        
        try:
            result = self.client.query(query).result()
            
            for row in result:
                logger.info(f"  {row.date} | {row.account} | {row.outflow or row.inflow} | {row.memo[:50]}...")
                
        except Exception as e:
            logger.error(f"Failed to fetch sample transactions: {e}")


def main():
    """Demo/test the transformation functionality."""
    try:
        config = Config()
        transformer = SheetTransactionTransformer(config)
        
        logger.info("🚀 Starting sheet transaction transformation")
        
        # Transform all banks
        results = transformer.transform_all_banks_to_sheet_transactions()
        
        # Show results summary
        logger.info("\n📈 Transformation Results:")
        for bank, count in results.items():
            logger.info(f"  {bank.upper()}: {count} transactions")
        
        # Show sample data
        logger.info("\n" + "="*60)
        transformer.get_sample_transactions(5)
        
        # Show useful queries
        logger.info("\n📖 Sample queries:")
        logger.info(f"-- All transactions:")
        logger.info(f"SELECT * FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions` ORDER BY date DESC LIMIT 20")
        logger.info(f"\n-- Monthly summary:")
        logger.info(f"SELECT transaction_month, account, COUNT(*) as txn_count, SUM(amount_numeric) as total_amount FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions` GROUP BY 1,2 ORDER BY 1 DESC")
        
    except Exception as e:
        logger.error(f"❌ Transformation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 