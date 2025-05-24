#!/usr/bin/env python3
"""
BigQuery table setup script for Budget Updater - V2 (Proper Data Warehouse Design)

This script creates a proper data warehouse structure with:
1. Staging tables per bank (raw data)
2. Standardized transactions table (unified format)  
3. Category and mapping tables (business logic)

Usage:
    python scripts/setup_bigquery_tables_v2.py
"""

import os
import sys
from pathlib import Path
from google.cloud import bigquery
from google.cloud.exceptions import NotFound, Conflict
import logging

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))
from budget_updater.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_seb_staging_table(client: bigquery.Client, dataset_id: str):
    """Create staging table for SEB raw data."""
    table_id = "seb_transactions_raw"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        # Metadata
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("row_number", "INTEGER", mode="REQUIRED"),
        
        # SEB Raw Columns (exactly as in Excel)
        bigquery.SchemaField("bokforingsdatum", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("valutadatum", "STRING", mode="NULLABLE"), 
        bigquery.SchemaField("verifikationsnummer", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("text", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("belopp", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("saldo", "FLOAT64", mode="NULLABLE"),
        
        # Deduplication
        bigquery.SchemaField("business_key", "STRING", mode="REQUIRED",
                            description="Business key for deduplication"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "SEB raw transaction data exactly as exported from Excel"
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="upload_timestamp"
    )
    table.clustering_fields = ["file_hash", "upload_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created staging table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_revolut_staging_table(client: bigquery.Client, dataset_id: str):
    """Create staging table for Revolut raw data."""
    table_id = "revolut_transactions_raw"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        # Metadata
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("row_number", "INTEGER", mode="REQUIRED"),
        
        # Revolut Raw Columns
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("product", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("started_date", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("completed_date", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("amount", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("fee", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("state", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("balance", "FLOAT64", mode="NULLABLE"),
        
        # Deduplication
        bigquery.SchemaField("business_key", "STRING", mode="REQUIRED",
                            description="Business key for deduplication"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Revolut raw transaction data exactly as exported from Excel"
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="upload_timestamp"
    )
    table.clustering_fields = ["file_hash", "upload_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created staging table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_firstcard_staging_table(client: bigquery.Client, dataset_id: str):
    """Create staging table for FirstCard raw data."""
    table_id = "firstcard_transactions_raw"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        # Metadata
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("row_number", "INTEGER", mode="REQUIRED"),
        
        # FirstCard Raw Columns
        bigquery.SchemaField("datum", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("ytterligare_information", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("reseinformation_inkopsplats", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("valuta", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("vaxlingskurs", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("utlandskt_belopp", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("belopp", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("moms", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("kort", "STRING", mode="NULLABLE"),
        
        # Deduplication
        bigquery.SchemaField("business_key", "STRING", mode="REQUIRED",
                            description="Business key for deduplication"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "FirstCard raw transaction data exactly as exported from Excel"
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="upload_timestamp"
    )
    table.clustering_fields = ["file_hash", "upload_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created staging table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_strawberry_staging_table(client: bigquery.Client, dataset_id: str):
    """Create staging table for Strawberry raw data."""
    table_id = "strawberry_transactions_raw"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        # Metadata
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("row_number", "INTEGER", mode="REQUIRED"),
        
        # Strawberry Raw Columns
        bigquery.SchemaField("datum", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("bokfort", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("specifikation", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("ort", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("valuta", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("utl_belopp_moms", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("belopp", "FLOAT64", mode="NULLABLE"),
        
        # Deduplication
        bigquery.SchemaField("business_key", "STRING", mode="REQUIRED",
                            description="Business key for deduplication"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Strawberry raw transaction data exactly as exported from Excel"
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="upload_timestamp"
    )
    table.clustering_fields = ["file_hash", "upload_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created staging table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_transactions_standardized_table(client: bigquery.Client, dataset_id: str):
    """Create unified standardized transactions table."""
    table_id = "transactions_standardized"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        # Primary Key & Metadata
        bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED", 
                            description="Unique transaction identifier"),
        bigquery.SchemaField("source_bank", "STRING", mode="REQUIRED",
                            description="Bank source: seb, revolut, firstcard, strawberry"),
        bigquery.SchemaField("source_file", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
        
        # Standardized Business Fields
        bigquery.SchemaField("transaction_date", "DATE", mode="REQUIRED",
                            description="Standardized transaction date"),
        bigquery.SchemaField("description", "STRING", mode="REQUIRED",
                            description="Standardized description"),
        bigquery.SchemaField("amount", "FLOAT64", mode="REQUIRED",
                            description="Amount in SEK (negative=expense, positive=income)"),
        bigquery.SchemaField("currency", "STRING", mode="NULLABLE", default_value_expression="'SEK'",
                            description="Transaction currency"),
        
        # Optional standardized fields
        bigquery.SchemaField("merchant_name", "STRING", mode="NULLABLE",
                            description="Extracted merchant/store name"),
        bigquery.SchemaField("location", "STRING", mode="NULLABLE",
                            description="Transaction location if available"),
        bigquery.SchemaField("card_type", "STRING", mode="NULLABLE",
                            description="Card or account type"),
        
        # Reference to staging data
        bigquery.SchemaField("staging_table", "STRING", mode="REQUIRED",
                            description="Source staging table name"),
        bigquery.SchemaField("staging_row_id", "STRING", mode="REQUIRED",
                            description="Reference to staging table row"),
        
        # Deduplication
        bigquery.SchemaField("business_key", "STRING", mode="REQUIRED",
                            description="Business key for deduplication (bank+date+amount+description hash)"),
        
        # Category fields (to be populated later)
        bigquery.SchemaField("category_id", "STRING", mode="NULLABLE",
                            description="Assigned category ID"),
        bigquery.SchemaField("subcategory_id", "STRING", mode="NULLABLE",
                            description="Assigned subcategory ID"),
        bigquery.SchemaField("is_manual_categorization", "BOOLEAN", mode="NULLABLE", default_value_expression="FALSE",
                            description="Whether category was manually assigned"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Standardized transactions from all banks in unified format"
    
    # Optimize for queries by date and bank
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="transaction_date"
    )
    table.clustering_fields = ["source_bank", "category_id"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created standardized table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_transaction_categories_table(client: bigquery.Client, dataset_id: str):
    """Create transaction categories reference table."""
    table_id = "transaction_categories"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        bigquery.SchemaField("category_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category_description", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("parent_category_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("budget_type", "STRING", mode="REQUIRED", 
                            description="INCOME, EXPENSE, TRANSFER, SAVINGS"),
        bigquery.SchemaField("is_active", "BOOLEAN", mode="REQUIRED", default_value_expression="TRUE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Transaction categories for budget classification"
    table.clustering_fields = ["budget_type", "parent_category_id"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created categories table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_categorization_rules_table(client: bigquery.Client, dataset_id: str):
    """Create automatic categorization rules table."""
    table_id = "categorization_rules"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        bigquery.SchemaField("rule_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("rule_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("pattern_type", "STRING", mode="REQUIRED",
                            description="CONTAINS, REGEX, EXACT, STARTS_WITH"),
        bigquery.SchemaField("pattern_value", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("field_to_match", "STRING", mode="REQUIRED",
                            description="description, merchant_name, etc."),
        bigquery.SchemaField("category_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("subcategory_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("priority", "INTEGER", mode="REQUIRED", default_value_expression="100"),
        bigquery.SchemaField("is_active", "BOOLEAN", mode="REQUIRED", default_value_expression="TRUE"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Rules for automatic transaction categorization"
    table.clustering_fields = ["pattern_type", "is_active"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created categorization rules table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_file_processing_log_table(client: bigquery.Client, dataset_id: str):
    """Create file processing log table."""
    table_id = "file_processing_log"
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("filename", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_bank", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("file_size_bytes", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("processed_timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("staging_records_processed", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("standardized_records_processed", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("processing_status", "STRING", mode="REQUIRED",
                            description="SUCCESS, FAILED, PARTIAL"),
        bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Log of processed files to prevent duplicates"
    table.clustering_fields = ["source_bank", "processed_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created file processing log table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_analysis_views(client: bigquery.Client, dataset_id: str, project_id: str):
    """Create useful views for analysis."""
    
    # Monthly summary view
    monthly_summary_sql = f"""
    CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.monthly_summary` AS
    SELECT 
        EXTRACT(YEAR FROM transaction_date) as year,
        EXTRACT(MONTH FROM transaction_date) as month,
        source_bank,
        COUNT(*) as transaction_count,
        ROUND(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) as total_expenses,
        ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) as total_income,
        ROUND(SUM(amount), 2) as net_amount
    FROM `{project_id}.{dataset_id}.transactions_standardized`
    GROUP BY year, month, source_bank
    ORDER BY year DESC, month DESC, source_bank
    """
    
    # Category summary view  
    category_summary_sql = f"""
    CREATE OR REPLACE VIEW `{project_id}.{dataset_id}.category_summary` AS
    SELECT 
        c.category_name,
        c.budget_type,
        COUNT(t.transaction_id) as transaction_count,
        ROUND(SUM(t.amount), 2) as total_amount,
        ROUND(AVG(t.amount), 2) as avg_amount,
        MIN(t.transaction_date) as earliest_date,
        MAX(t.transaction_date) as latest_date
    FROM `{project_id}.{dataset_id}.transactions_standardized` t
    LEFT JOIN `{project_id}.{dataset_id}.transaction_categories` c 
        ON t.category_id = c.category_id
    GROUP BY c.category_name, c.budget_type
    ORDER BY total_amount DESC
    """
    
    try:
        client.query(monthly_summary_sql).result()
        logger.info(f"✅ Created view {dataset_id}.monthly_summary")
        
        client.query(category_summary_sql).result()
        logger.info(f"✅ Created view {dataset_id}.category_summary")
        
    except Exception as e:
        logger.error(f"❌ Failed to create views: {e}")
        raise

def insert_default_categories(client: bigquery.Client, dataset_id: str, project_id: str):
    """Insert default categories into the categories table."""
    
    default_categories = [
        # Income categories
        ("INC001", "Salary", "Monthly salary and wages", None, "INCOME"),
        ("INC002", "Freelance", "Freelance and consulting income", None, "INCOME"),
        ("INC003", "Investment Returns", "Dividends, interest, capital gains", None, "INCOME"),
        ("INC004", "Other Income", "Miscellaneous income", None, "INCOME"),
        
        # Main expense categories
        ("EXP001", "Housing", "Rent, mortgage, utilities", None, "EXPENSE"),
        ("EXP002", "Transportation", "Car, public transport, fuel", None, "EXPENSE"),
        ("EXP003", "Food & Dining", "Groceries, restaurants, cafes", None, "EXPENSE"),
        ("EXP004", "Shopping", "Clothes, electronics, general shopping", None, "EXPENSE"),
        ("EXP005", "Healthcare", "Medical, dental, pharmacy", None, "EXPENSE"),
        ("EXP006", "Entertainment", "Movies, sports, hobbies", None, "EXPENSE"),
        ("EXP007", "Travel", "Vacations, business travel", None, "EXPENSE"),
        ("EXP008", "Education", "Courses, books, training", None, "EXPENSE"),
        ("EXP009", "Insurance", "Health, car, home insurance", None, "EXPENSE"),
        ("EXP010", "Taxes", "Income tax, property tax", None, "EXPENSE"),
        ("EXP011", "Other Expenses", "Miscellaneous expenses", None, "EXPENSE"),
        
        # Sub-categories for Food
        ("EXP003_01", "Groceries", "Supermarket shopping", "EXP003", "EXPENSE"),
        ("EXP003_02", "Restaurants", "Dining out", "EXP003", "EXPENSE"),
        ("EXP003_03", "Fast Food", "Quick meals", "EXP003", "EXPENSE"),
        ("EXP003_04", "Coffee & Cafes", "Coffee shops, cafes", "EXP003", "EXPENSE"),
        
        # Sub-categories for Transportation
        ("EXP002_01", "Fuel", "Gas for car", "EXP002", "EXPENSE"),
        ("EXP002_02", "Public Transport", "Bus, train, metro", "EXP002", "EXPENSE"),
        ("EXP002_03", "Taxi & Ride Share", "Uber, taxi", "EXP002", "EXPENSE"),
        ("EXP002_04", "Car Maintenance", "Repairs, service", "EXP002", "EXPENSE"),
        
        # Transfers and savings
        ("TRN001", "Bank Transfer", "Transfers between accounts", None, "TRANSFER"),
        ("SAV001", "Savings", "Money moved to savings", None, "SAVINGS"),
        ("SAV002", "Investments", "Money invested", None, "SAVINGS"),
    ]
    
    insert_sql = f"""
    INSERT INTO `{project_id}.{dataset_id}.transaction_categories` 
    (category_id, category_name, category_description, parent_category_id, budget_type, is_active, created_at, updated_at)
    VALUES
    """
    
    values = []
    for cat_id, name, desc, parent, budget_type in default_categories:
        parent_sql = 'NULL' if parent is None else f"'{parent}'"
        values.append(f"('{cat_id}', '{name}', '{desc}', {parent_sql}, '{budget_type}', TRUE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())")
    
    insert_sql += ",\n".join(values)
    
    try:
        client.query(insert_sql).result()
        logger.info(f"✅ Inserted {len(default_categories)} default categories")
    except Exception as e:
        logger.error(f"❌ Failed to insert default categories: {e}")
        raise

def setup_bigquery_data_warehouse():
    """Main function to set up the complete BigQuery data warehouse."""
    try:
        # Initialize config and client
        config = Config()
        client = bigquery.Client(project=config.gcp_project_id)
        dataset_id = config.bigquery_dataset_id
        project_id = config.gcp_project_id
        
        # Create dataset if it doesn't exist
        dataset_ref = client.dataset(dataset_id)
        try:
            dataset = client.get_dataset(dataset_ref)
            logger.info(f"✅ Dataset {dataset_id} already exists")
        except NotFound:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "EU"  # Change if needed
            dataset.description = "Budget Updater data warehouse"
            dataset = client.create_dataset(dataset, exists_ok=True)
            logger.info(f"✅ Created dataset {dataset_id}")
        
        logger.info("🏗️  Creating BigQuery data warehouse...")
        
        # 1. STAGING LAYER - Raw data per bank
        logger.info("📦 Creating staging tables...")
        create_seb_staging_table(client, dataset_id)
        create_revolut_staging_table(client, dataset_id)
        create_firstcard_staging_table(client, dataset_id)
        create_strawberry_staging_table(client, dataset_id)
        
        # 2. CLEAN LAYER - Standardized data
        logger.info("🧹 Creating standardized tables...")
        create_transactions_standardized_table(client, dataset_id)
        
        # 3. BUSINESS LAYER - Categories and rules
        logger.info("📊 Creating business tables...")
        create_transaction_categories_table(client, dataset_id)
        create_categorization_rules_table(client, dataset_id)
        
        # 4. OPERATIONAL TABLES
        logger.info("⚙️  Creating operational tables...")
        create_file_processing_log_table(client, dataset_id)
        
        # 5. ANALYSIS VIEWS
        logger.info("📈 Creating analysis views...")
        create_analysis_views(client, dataset_id, project_id)
        
        # 6. INSERT DEFAULT DATA
        logger.info("💾 Inserting default categories...")
        insert_default_categories(client, dataset_id, project_id)
        
        logger.info("🎉 BigQuery data warehouse setup completed!")
        
        # Print summary
        print("\n" + "="*80)
        print("📊 BIGQUERY DATA WAREHOUSE SETUP SUMMARY")
        print("="*80)
        print(f"Project: {project_id}")
        print(f"Dataset: {dataset_id}")
        print("\n🏗️  ARCHITECTURE:")
        print("   📦 STAGING LAYER (Raw data exactly as from banks):")
        print("      • seb_transactions_raw")
        print("      • revolut_transactions_raw") 
        print("      • firstcard_transactions_raw")
        print("      • strawberry_transactions_raw")
        print("\n   🧹 CLEAN LAYER (Standardized format):")
        print("      • transactions_standardized")
        print("\n   📊 BUSINESS LAYER (Categories & rules):")
        print("      • transaction_categories")
        print("      • categorization_rules")
        print("\n   📈 ANALYSIS LAYER (Views):")
        print("      • monthly_summary")
        print("      • category_summary")
        print("\n   ⚙️  OPERATIONAL:")
        print("      • file_processing_log")
        print("\n🚀 NEXT STEPS:")
        print("   1. Use upload_transactions_v2.py to load data into staging")
        print("   2. Transform staging → standardized with ETL script")
        print("   3. Set up categorization rules")
        print("   4. Query standardized tables for analysis")
        print("="*80)
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_bigquery_data_warehouse() 