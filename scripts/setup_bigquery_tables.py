#!/usr/bin/env python3
"""
BigQuery table setup script for Budget Updater.

This script creates the necessary BigQuery tables to store raw transaction data
from multiple bank sources (SEB, Revolut, FirstCard, Strawberry).

Usage:
    python scripts/setup_bigquery_tables.py
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

def create_raw_transactions_table(client: bigquery.Client, dataset_id: str, table_id: str = "raw_transactions"):
    """
    Create the main raw transactions table with flexible schema to handle all bank formats.
    
    Table design:
    - Unified schema that can handle all bank formats
    - Raw columns preserved for full fidelity  
    - Standardized columns for common analysis
    - Metadata columns for tracking and deduplication
    """
    
    table_ref = client.dataset(dataset_id).table(table_id)
    
    # Define schema - mix of standardized and flexible columns
    schema = [
        # === METADATA COLUMNS ===
        bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED", 
                            description="Unique identifier (hash of source + raw data)"),
        bigquery.SchemaField("source_bank", "STRING", mode="REQUIRED", 
                            description="Bank/card source: seb, revolut, firstcard, strawberry"),
        bigquery.SchemaField("source_file", "STRING", mode="NULLABLE", 
                            description="Original filename"),
        bigquery.SchemaField("upload_timestamp", "TIMESTAMP", mode="REQUIRED", 
                            description="When this record was uploaded to BigQuery"),
        bigquery.SchemaField("file_hash", "STRING", mode="NULLABLE", 
                            description="Hash of source file for deduplication"),
        
        # === STANDARDIZED COLUMNS (parsed by our parsers) ===
        bigquery.SchemaField("parsed_date", "DATE", mode="REQUIRED", 
                            description="Standardized transaction date"),
        bigquery.SchemaField("parsed_description", "STRING", mode="REQUIRED", 
                            description="Standardized description/text"),
        bigquery.SchemaField("parsed_amount", "FLOAT64", mode="REQUIRED", 
                            description="Standardized amount (negative=outflow, positive=inflow)"),
        
        # === RAW COLUMNS - SEB FORMAT ===
        bigquery.SchemaField("seb_bokforingsdatum", "STRING", mode="NULLABLE", 
                            description="SEB: Bokföringsdatum (raw)"),
        bigquery.SchemaField("seb_valutadatum", "STRING", mode="NULLABLE", 
                            description="SEB: Valutadatum (raw)"),
        bigquery.SchemaField("seb_verifikationsnummer", "INTEGER", mode="NULLABLE", 
                            description="SEB: Verifikationsnummer"),
        bigquery.SchemaField("seb_text", "STRING", mode="NULLABLE", 
                            description="SEB: Text (raw)"),
        bigquery.SchemaField("seb_belopp", "FLOAT64", mode="NULLABLE", 
                            description="SEB: Belopp (raw)"),
        bigquery.SchemaField("seb_saldo", "FLOAT64", mode="NULLABLE", 
                            description="SEB: Saldo"),
        
        # === RAW COLUMNS - REVOLUT FORMAT ===
        bigquery.SchemaField("revolut_type", "STRING", mode="NULLABLE", 
                            description="Revolut: Type"),
        bigquery.SchemaField("revolut_product", "STRING", mode="NULLABLE", 
                            description="Revolut: Product"),
        bigquery.SchemaField("revolut_started_date", "STRING", mode="NULLABLE", 
                            description="Revolut: Started Date (raw)"),
        bigquery.SchemaField("revolut_completed_date", "STRING", mode="NULLABLE", 
                            description="Revolut: Completed Date (raw)"),
        bigquery.SchemaField("revolut_description", "STRING", mode="NULLABLE", 
                            description="Revolut: Description (raw)"),
        bigquery.SchemaField("revolut_amount", "FLOAT64", mode="NULLABLE", 
                            description="Revolut: Amount (raw)"),
        bigquery.SchemaField("revolut_fee", "FLOAT64", mode="NULLABLE", 
                            description="Revolut: Fee"),
        bigquery.SchemaField("revolut_currency", "STRING", mode="NULLABLE", 
                            description="Revolut: Currency"),
        bigquery.SchemaField("revolut_state", "STRING", mode="NULLABLE", 
                            description="Revolut: State"),
        bigquery.SchemaField("revolut_balance", "FLOAT64", mode="NULLABLE", 
                            description="Revolut: Balance"),
        
        # === RAW COLUMNS - FIRSTCARD FORMAT ===
        bigquery.SchemaField("firstcard_datum", "STRING", mode="NULLABLE", 
                            description="FirstCard: Datum (raw)"),
        bigquery.SchemaField("firstcard_ytterligare_info", "STRING", mode="NULLABLE", 
                            description="FirstCard: Ytterligare information"),
        bigquery.SchemaField("firstcard_reseinformation", "STRING", mode="NULLABLE", 
                            description="FirstCard: Reseinformation / Inköpsplats (raw)"),
        bigquery.SchemaField("firstcard_valuta", "STRING", mode="NULLABLE", 
                            description="FirstCard: Valuta"),
        bigquery.SchemaField("firstcard_vaxlingskurs", "FLOAT64", mode="NULLABLE", 
                            description="FirstCard: Växlingskurs"),
        bigquery.SchemaField("firstcard_utlandskt_belopp", "FLOAT64", mode="NULLABLE", 
                            description="FirstCard: Utländskt belopp"),
        bigquery.SchemaField("firstcard_belopp", "FLOAT64", mode="NULLABLE", 
                            description="FirstCard: Belopp (raw)"),
        bigquery.SchemaField("firstcard_moms", "FLOAT64", mode="NULLABLE", 
                            description="FirstCard: Moms"),
        bigquery.SchemaField("firstcard_kort", "STRING", mode="NULLABLE", 
                            description="FirstCard: Kort"),
        
        # === RAW COLUMNS - STRAWBERRY FORMAT ===
        bigquery.SchemaField("strawberry_datum", "STRING", mode="NULLABLE", 
                            description="Strawberry: Datum (raw)"),
        bigquery.SchemaField("strawberry_bokfort", "STRING", mode="NULLABLE", 
                            description="Strawberry: Bokfört (raw)"),
        bigquery.SchemaField("strawberry_specifikation", "STRING", mode="NULLABLE", 
                            description="Strawberry: Specifikation (raw)"),
        bigquery.SchemaField("strawberry_ort", "STRING", mode="NULLABLE", 
                            description="Strawberry: Ort"),
        bigquery.SchemaField("strawberry_valuta", "STRING", mode="NULLABLE", 
                            description="Strawberry: Valuta"),
        bigquery.SchemaField("strawberry_utl_belopp_moms", "STRING", mode="NULLABLE", 
                            description="Strawberry: Utl.belopp/moms"),
        bigquery.SchemaField("strawberry_belopp", "FLOAT64", mode="NULLABLE", 
                            description="Strawberry: Belopp (raw)"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    
    # Set table options
    table.description = "Raw transaction data from all bank sources with standardized parsing"
    
    # Clustering and partitioning for performance
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="parsed_date"
    )
    table.clustering_fields = ["source_bank", "upload_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def create_file_processing_log_table(client: bigquery.Client, dataset_id: str, table_id: str = "file_processing_log"):
    """
    Create a log table to track file processing and prevent duplicate uploads.
    """
    
    table_ref = client.dataset(dataset_id).table(table_id)
    
    schema = [
        bigquery.SchemaField("file_hash", "STRING", mode="REQUIRED", 
                            description="SHA256 hash of the file content"),
        bigquery.SchemaField("filename", "STRING", mode="REQUIRED", 
                            description="Original filename"),
        bigquery.SchemaField("source_bank", "STRING", mode="REQUIRED", 
                            description="Bank source identifier"),
        bigquery.SchemaField("file_size_bytes", "INTEGER", mode="NULLABLE", 
                            description="File size in bytes"),
        bigquery.SchemaField("processed_timestamp", "TIMESTAMP", mode="REQUIRED", 
                            description="When the file was processed"),
        bigquery.SchemaField("records_processed", "INTEGER", mode="NULLABLE", 
                            description="Number of records loaded from this file"),
        bigquery.SchemaField("processing_status", "STRING", mode="REQUIRED", 
                            description="SUCCESS, FAILED, or PARTIAL"),
        bigquery.SchemaField("error_message", "STRING", mode="NULLABLE", 
                            description="Error details if processing failed"),
    ]
    
    table = bigquery.Table(table_ref, schema=schema)
    table.description = "Log of processed files to prevent duplicates and track processing history"
    
    # Cluster by source_bank and processed_timestamp for efficient lookups
    table.clustering_fields = ["source_bank", "processed_timestamp"]
    
    try:
        table = client.create_table(table, exists_ok=True)
        logger.info(f"✅ Created table {dataset_id}.{table_id}")
        return table
    except Exception as e:
        logger.error(f"❌ Failed to create table {dataset_id}.{table_id}: {e}")
        raise

def setup_bigquery_dataset_and_tables():
    """
    Main function to set up BigQuery dataset and all required tables.
    """
    try:
        # Initialize config and client
        config = Config()
        client = bigquery.Client(project=config.gcp_project_id)
        
        dataset_id = config.bigquery_dataset_id
        
        # Create dataset if it doesn't exist
        dataset_ref = client.dataset(dataset_id)
        try:
            dataset = client.get_dataset(dataset_ref)
            logger.info(f"✅ Dataset {dataset_id} already exists")
        except NotFound:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "EU"  # Change if needed
            dataset.description = "Budget Updater transaction data storage"
            dataset = client.create_dataset(dataset, exists_ok=True)
            logger.info(f"✅ Created dataset {dataset_id}")
        
        # Create tables
        logger.info("🏗️  Creating BigQuery tables...")
        
        # Main transactions table
        create_raw_transactions_table(client, dataset_id)
        
        # File processing log table
        create_file_processing_log_table(client, dataset_id)
        
        logger.info("🎉 BigQuery setup completed successfully!")
        
        # Print summary
        print("\n" + "="*60)
        print("📊 BIGQUERY SETUP SUMMARY")
        print("="*60)
        print(f"Project: {config.gcp_project_id}")
        print(f"Dataset: {dataset_id}")
        print("Tables created:")
        print("  • raw_transactions - Main transaction storage")
        print("  • file_processing_log - File processing tracking")
        print("\nNext steps:")
        print("  1. Use upload_transactions.py to load Excel files")
        print("  2. Query data using the standardized columns")
        print("  3. Access raw columns for bank-specific analysis")
        print("="*60)
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_bigquery_dataset_and_tables() 