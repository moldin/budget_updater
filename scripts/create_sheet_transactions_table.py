#!/usr/bin/env python3
"""
Create BigQuery table that matches Google Sheet "Transactions" structure.

This table stores the final processed transactions that mirror what gets uploaded 
to the Google Sheet, with an additional business_key column for linking back 
to the source raw data.
"""

import logging
import sys
from pathlib import Path

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


def create_sheet_transactions_table(client: bigquery.Client, dataset_id: str, project_id: str):
    """
    Create a BigQuery table that matches the Google Sheet "Transactions" structure.
    
    This table includes:
    - All columns from the Google Sheet Transactions tab
    - Additional business_key column for linking to raw data
    - Additional metadata for tracking and analysis
    """
    table_id = "sheet_transactions"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        # === GOOGLE SHEET COLUMNS ===
        # These match exactly the TARGET_COLUMNS from config.py
        bigquery.SchemaField("date", "DATE", mode="REQUIRED",
                            description="Transaction date (Google Sheet: Date column)"),
        bigquery.SchemaField("outflow", "STRING", mode="NULLABLE",
                            description="Outflow amount as string (Google Sheet: Outflow column)"),
        bigquery.SchemaField("inflow", "STRING", mode="NULLABLE", 
                            description="Inflow amount as string (Google Sheet: Inflow column)"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED",
                            description="Transaction category (Google Sheet: Category column)"),
        bigquery.SchemaField("account", "STRING", mode="REQUIRED",
                            description="Account name (Google Sheet: Account column)"),
        bigquery.SchemaField("memo", "STRING", mode="NULLABLE",
                            description="Transaction memo/description (Google Sheet: Memo column)"),
        bigquery.SchemaField("status", "STRING", mode="NULLABLE", 
                            description="Transaction status (Google Sheet: Status column)"),
        
        # === LINKING & METADATA COLUMNS ===
        bigquery.SchemaField("business_key", "STRING", mode="REQUIRED",
                            description="Business key linking to source raw data in staging tables"),
        bigquery.SchemaField("source_bank", "STRING", mode="REQUIRED",
                            description="Source bank: seb, revolut, firstcard, strawberry"),
        bigquery.SchemaField("source_file", "STRING", mode="REQUIRED",
                            description="Original source file name"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED",
                            description="When this transaction was processed to the sheet"),
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED",
                            description="Hash of the source file"),
        
        # === ANALYSIS COLUMNS ===
        bigquery.SchemaField("amount_numeric", "FLOAT64", mode="NULLABLE",
                            description="Numeric amount (negative=outflow, positive=inflow)"),
        bigquery.SchemaField("currency", "STRING", mode="NULLABLE", 
                            description="Transaction currency"),
        bigquery.SchemaField("transaction_month", "DATE", mode="NULLABLE",
                            description="First day of transaction month for easy grouping"),
        bigquery.SchemaField("transaction_year", "INTEGER", mode="NULLABLE",
                            description="Transaction year for easy filtering"),
    ]
    
    # Create table with clustering for efficient queries
    table = bigquery.Table(table_ref, schema=schema)
    table.description = """
    Table matching Google Sheet 'Transactions' structure with additional linking capabilities.
    
    This table stores the final processed transactions exactly as they appear in the 
    Google Sheet, plus metadata for linking back to raw source data and analysis.
    
    Key features:
    - Exact match to Google Sheet TARGET_COLUMNS structure
    - business_key for linking to raw staging tables
    - Additional analysis columns for reporting
    - Clustered for efficient querying by date and account
    """
    
    # Set up clustering for query performance
    table.clustering_fields = ["transaction_month", "account", "source_bank"]
    
    # Set up partitioning by date for large datasets
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="date"
    )
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created sheet_transactions table {dataset_id}.{table_id}")
        
        # Log table details
        logger.info(f"📊 Table details:")
        logger.info(f"   - Partitioned by: date (daily)")
        logger.info(f"   - Clustered by: transaction_month, account, source_bank")
        logger.info(f"   - Schema fields: {len(schema)}")
        logger.info(f"   - Description: {table.description[:100]}...")
        
        return table
        
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise


def create_sheet_transactions_view(client: bigquery.Client, dataset_id: str, project_id: str):
    """
    Create a view that shows how to link sheet_transactions back to raw data.
    """
    view_id = "sheet_transactions_with_raw_data"
    view_ref = client.dataset(dataset_id).table(view_id)
    
    # SQL to create a view that joins sheet_transactions with raw data
    view_query = f"""
    WITH raw_data AS (
      -- SEB raw data
      SELECT 
        business_key,
        'seb' as source_bank,
        text as raw_description,
        verifikationsnummer as raw_id,
        bokforingsdatum as raw_date,
        belopp as raw_amount,
        saldo as raw_balance
      FROM `{project_id}.{dataset_id}.seb_transactions_raw`
      
      UNION ALL
      
      -- Revolut raw data  
      SELECT 
        business_key,
        'revolut' as source_bank,
        description as raw_description,
        CAST(ROW_NUMBER() OVER (ORDER BY completed_date) AS STRING) as raw_id,
        CAST(completed_date AS STRING) as raw_date,
        amount as raw_amount,
        balance as raw_balance
      FROM `{project_id}.{dataset_id}.revolut_transactions_raw`
      
      UNION ALL
      
      -- FirstCard raw data
      SELECT 
        business_key,
        'firstcard' as source_bank,
        ytterligare_information as raw_description,
        CAST(ROW_NUMBER() OVER (ORDER BY datum) AS STRING) as raw_id,
        CAST(datum AS STRING) as raw_date,
        belopp as raw_amount,
        NULL as raw_balance
      FROM `{project_id}.{dataset_id}.firstcard_transactions_raw`
      
      UNION ALL
      
      -- Strawberry raw data
      SELECT 
        business_key,
        'strawberry' as source_bank,
        specifikation as raw_description,
        CAST(ROW_NUMBER() OVER (ORDER BY datum) AS STRING) as raw_id,
        CAST(datum AS STRING) as raw_date,
        belopp as raw_amount,
        NULL as raw_balance
      FROM `{project_id}.{dataset_id}.strawberry_transactions_raw`
    )
    
    SELECT 
      st.*,
      rd.raw_description,
      rd.raw_id,
      rd.raw_date,
      rd.raw_amount,
      rd.raw_balance
    FROM `{project_id}.{dataset_id}.sheet_transactions` st
    LEFT JOIN raw_data rd ON st.business_key = rd.business_key 
                          AND st.source_bank = rd.source_bank
    """
    
    view = bigquery.Table(view_ref)
    view.view_query = view_query
    view.description = """
    View that joins sheet_transactions with raw source data.
    
    This view shows the final Google Sheet transactions alongside their 
    original raw data from the staging tables, linked via business_key.
    
    Useful for:
    - Auditing data transformations
    - Debugging data quality issues  
    - Understanding data lineage
    - Accessing original raw values when needed
    """
    
    try:
        view = client.create_table(view, exists_ok=True)
        logger.info(f"✅ Created view {dataset_id}.{view_id}")
        return view
        
    except Exception as e:
        logger.error(f"❌ Failed to create view {dataset_id}.{view_id}: {e}")
        raise


def main():
    """Create the sheet_transactions table and supporting view."""
    try:
        # Initialize configuration
        config = Config()
        
        # Initialize BigQuery client
        client = bigquery.Client(project=config.gcp_project_id)
        
        logger.info(f"🚀 Creating sheet_transactions table in {config.gcp_project_id}.{config.bigquery_dataset_id}")
        
        # Create the main table
        table = create_sheet_transactions_table(
            client, 
            config.bigquery_dataset_id, 
            config.gcp_project_id
        )
        
        # Create the linking view
        view = create_sheet_transactions_view(
            client,
            config.bigquery_dataset_id,
            config.gcp_project_id
        )
        
        logger.info("✅ All sheet_transactions objects created successfully!")
        logger.info(f"📝 Table: {config.bigquery_dataset_id}.sheet_transactions")
        logger.info(f"👁️  View:  {config.bigquery_dataset_id}.sheet_transactions_with_raw_data")
        
        # Show sample usage
        logger.info("\n📖 Sample usage:")
        logger.info("-- Query Google Sheet data:")
        logger.info(f"SELECT * FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions` LIMIT 10")
        logger.info("\n-- Query with raw data:")
        logger.info(f"SELECT * FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions_with_raw_data` LIMIT 10")
        
        
    except Exception as e:
        logger.error(f"❌ Failed to create sheet_transactions table: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 