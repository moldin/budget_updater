#!/usr/bin/env python3
"""
Transaction upload script for BigQuery - V2 (Data Warehouse Approach)

This script uploads transaction data to BigQuery staging tables and then
transforms it to the standardized table. Follows proper ETL patterns.

Usage:
    python scripts/upload_transactions_v2.py [file_path] [--bank BANK] [--dry-run] [--stage-only]
    
Examples:
    python scripts/upload_transactions_v2.py data/seb.xlsx --bank seb
    python scripts/upload_transactions_v2.py data/revolut_new.xlsx --bank revolut --stage-only
    python scripts/upload_transactions_v2.py data/ --bank all  # Process all files in directory
"""

import os
import sys
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import pandas as pd
from google.cloud import bigquery
import logging

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))
from budget_updater.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TransactionUploaderV2:
    """Handles uploading transaction data to BigQuery with proper staging approach."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
        self.log_table_id = "file_processing_log"
        
        # Staging table mappings
        self.staging_tables = {
            'seb': 'seb_transactions_raw',
            'revolut': 'revolut_transactions_raw',
            'firstcard': 'firstcard_transactions_raw',
            'strawberry': 'strawberry_transactions_raw'
        }
        
        # Column mappings from Excel to staging tables
        self.column_mappings = {
            'seb': {
                'Bokföringsdatum': 'bokforingsdatum',
                'Valutadatum': 'valutadatum',
                'Verifikationsnummer': 'verifikationsnummer',
                'Text': 'text',
                'Belopp': 'belopp',
                'Saldo': 'saldo'
            },
            'revolut': {
                'Type': 'type',
                'Product': 'product',
                'Started Date': 'started_date',
                'Completed Date': 'completed_date',
                'Description': 'description',
                'Amount': 'amount',
                'Fee': 'fee',
                'Currency': 'currency',
                'State': 'state',
                'Balance': 'balance'
            },
            'firstcard': {
                'Datum': 'datum',
                'Ytterligare information': 'ytterligare_information',
                'Reseinformation / Inköpsplats': 'reseinformation_inkopsplats',
                'Valuta': 'valuta',
                'växlingskurs': 'vaxlingskurs',
                'Utländskt belopp': 'utlandskt_belopp',
                'Belopp': 'belopp',
                'Moms': 'moms',
                'Kort': 'kort'
            },
            'strawberry': {
                'Datum': 'datum',
                'Bokfört': 'bokfort',
                'Specifikation': 'specifikation',
                'Ort': 'ort',
                'Valuta': 'valuta',
                'Utl.belopp/moms': 'utl_belopp_moms',
                'Belopp': 'belopp'
            }
        }
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file content for deduplication."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def check_file_already_processed(self, file_hash: str) -> bool:
        """Check if file has already been processed successfully."""
        query = f"""
        SELECT COUNT(*) as count
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.{self.log_table_id}`
        WHERE file_hash = @file_hash 
        AND processing_status = 'SUCCESS'
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("file_hash", "STRING", file_hash)
            ]
        )
        
        try:
            results = self.client.query(query, job_config=job_config)
            for row in results:
                return row.count > 0
        except Exception as e:
            logger.warning(f"Could not check file processing status: {e}")
            return False
        
        return False
    
    def prepare_staging_data(self, df: pd.DataFrame, source_bank: str, file_path: Path, file_hash: str) -> List[Dict]:
        """Prepare data for staging table insertion."""
        
        column_mapping = self.column_mappings[source_bank]
        staging_rows = []
        upload_timestamp = datetime.now(timezone.utc)
        
        # Filter out rows with invalid dates for banks that use 'datum' field
        if source_bank in ['firstcard', 'strawberry']:
            # Filter out rows where 'Datum' is not a datetime
            initial_count = len(df)
            df = df[pd.to_datetime(df['Datum'], errors='coerce').notna()]
            filtered_count = len(df)
            if initial_count != filtered_count:
                logger.info(f"📝 Filtered out {initial_count - filtered_count} rows with invalid dates")
        
        for i, row in df.iterrows():
            # Create base record with metadata
            record = {
                "file_hash": file_hash,
                "source_file": file_path.name,
                "upload_timestamp": upload_timestamp.isoformat(),  # Convert to ISO string
                "row_number": i + 1
            }
            
            # Map and add bank-specific columns
            for excel_col, staging_col in column_mapping.items():
                if excel_col in df.columns:
                    value = row[excel_col]
                    
                    # Handle different data types
                    if pd.isna(value):
                        record[staging_col] = None
                    elif staging_col in ['verifikationsnummer', 'row_number']:
                        record[staging_col] = int(value) if pd.notna(value) else None
                    elif 'belopp' in staging_col or 'amount' in staging_col or staging_col in ['fee', 'balance', 'vaxlingskurs', 'utlandskt_belopp', 'moms']:
                        record[staging_col] = float(value) if pd.notna(value) else None
                    else:
                        record[staging_col] = str(value) if pd.notna(value) else None
                else:
                    record[staging_col] = None
            
            # Generate business key for deduplication
            record['business_key'] = self.generate_business_key(source_bank, record)
            
            staging_rows.append(record)
        
        return staging_rows
    
    def upload_to_staging(self, file_path: Path, source_bank: str, dry_run: bool = False, force_duplicates: bool = False) -> Tuple[bool, int, str]:
        """
        Upload Excel file data to staging table.
        
        Returns:
            (success: bool, records_processed: int, error_message: str)
        """
        try:
            logger.info(f"📁 Processing {file_path} as {source_bank}")
            
            # Calculate file hash for deduplication
            file_hash = self.calculate_file_hash(file_path)
            
            # Check if already processed
            if self.check_file_already_processed(file_hash):
                logger.info(f"⏭️  File {file_path.name} already processed (hash: {file_hash[:8]}...)")
                return True, 0, "Already processed"
            
            # Validate bank and get staging table
            if source_bank not in self.staging_tables:
                error_msg = f"No staging table available for bank: {source_bank}"
                logger.error(error_msg)
                return False, 0, error_msg
            
            staging_table_id = self.staging_tables[source_bank]
            
            # Read Excel file
            df = pd.read_excel(file_path)
            logger.info(f"📊 Read {len(df)} rows from Excel file")
            
            # Prepare data for staging
            staging_data = self.prepare_staging_data(df, source_bank, file_path, file_hash)
            
            # Check for business key duplicates BEFORE uploading to staging (unless force_duplicates)
            if not force_duplicates:
                new_records, duplicate_records = self.check_business_key_duplicates(staging_data, source_bank)
                
                # Report duplicate findings
                if duplicate_records:
                    logger.warning(f"⚠️  Found {len(duplicate_records)} potential duplicate transactions!")
                    logger.warning("Duplicate transactions (will be skipped):")
                    for i, dup in enumerate(duplicate_records[:5]):  # Show first 5
                        date_field = {
                            'seb': 'bokforingsdatum',
                            'revolut': 'completed_date', 
                            'firstcard': 'datum',
                            'strawberry': 'datum'
                        }[source_bank]
                        amount_field = {
                            'seb': 'belopp',
                            'revolut': 'amount',
                            'firstcard': 'belopp', 
                            'strawberry': 'belopp'
                        }[source_bank]
                        desc_field = {
                            'seb': 'text',
                            'revolut': 'description',
                            'firstcard': 'ytterligare_information',
                            'strawberry': 'specifikation'
                        }[source_bank]
                        
                        date_val = dup.get(date_field, 'N/A')
                        amount_val = dup.get(amount_field, 'N/A')
                        desc_val = str(dup.get(desc_field, 'N/A'))[:50]
                        logger.warning(f"  {i+1}. {date_val} | {amount_val} | {desc_val}...")
                    
                    if len(duplicate_records) > 5:
                        logger.warning(f"  ... and {len(duplicate_records) - 5} more")
                
                # Use only new records for upload
                staging_data = new_records
                
                if not staging_data:
                    logger.info("📭 No new transactions to upload (all were duplicates)")
                    return True, 0, "No new transactions"
            else:
                logger.info("🔄 Force duplicates enabled - skipping duplicate check")
            
            if dry_run:
                logger.info(f"🏃‍♂️ DRY RUN: Would upload {len(staging_data)} records to {staging_table_id}")
                logger.info("Sample record:")
                if staging_data:
                    sample = {k: v for k, v in list(staging_data[0].items())[:6]}
                    for k, v in sample.items():
                        logger.info(f"  {k}: {v}")
                return True, len(staging_data), "Dry run successful"
            
            # Upload to staging table
            table_ref = self.client.dataset(self.dataset_id).table(staging_table_id)
            
            logger.info(f"⬆️  Uploading {len(staging_data)} records to staging table {staging_table_id}...")
            errors = self.client.insert_rows_json(table_ref, staging_data)
            
            if errors:
                error_msg = f"BigQuery insertion errors: {errors}"
                logger.error(error_msg)
                self.log_file_processing(file_path, source_bank, file_hash, 0, 0, "FAILED", error_msg)
                return False, 0, error_msg
            
            # Log successful processing
            self.log_file_processing(file_path, source_bank, file_hash, len(staging_data), 0, "SUCCESS")
            
            logger.info(f"✅ Successfully uploaded {len(staging_data)} records to staging")
            return True, len(staging_data), None
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error(error_msg)
            try:
                self.log_file_processing(file_path, source_bank, file_hash, 0, 0, "FAILED", error_msg)
            except:
                pass  # Don't fail if logging fails
            return False, 0, error_msg
    
    def transform_staging_to_standardized(self, source_bank: str = None, dry_run: bool = False) -> bool:
        """Transform data from staging tables to standardized table."""
        
        banks_to_process = [source_bank] if source_bank else list(self.staging_tables.keys())
        
        for bank in banks_to_process:
            logger.info(f"🔄 Transforming {bank} staging data to standardized format...")
            
            try:
                # Build transformation query based on bank
                transform_query = self.build_transform_query(bank)
                
                if dry_run:
                    logger.info(f"🏃‍♂️ DRY RUN: Would execute transformation for {bank}")
                    logger.info(f"Query preview:\n{transform_query[:200]}...")
                    continue
                
                # Execute transformation
                job = self.client.query(transform_query)
                job.result()  # Wait for completion
                
                logger.info(f"✅ Transformation completed for {bank}")
                
            except Exception as e:
                logger.error(f"❌ Transformation failed for {bank}: {e}")
                return False
        
        return True
    
    def build_transform_query(self, source_bank: str) -> str:
        """Build SQL query to transform staging data to standardized format."""
        
        staging_table = self.staging_tables[source_bank]
        project_id = self.config.gcp_project_id
        dataset_id = self.dataset_id
        
        if source_bank == 'seb':
            return f"""
            INSERT INTO `{project_id}.{dataset_id}.transactions_standardized`
            (transaction_id, source_bank, source_file, upload_timestamp, file_hash,
             transaction_date, description, amount, currency, staging_table, staging_row_id, business_key)
            SELECT 
                GENERATE_UUID() as transaction_id,
                'seb' as source_bank,
                source_file,
                upload_timestamp,
                file_hash,
                CASE 
                    WHEN bokforingsdatum IS NOT NULL 
                    THEN PARSE_DATE('%Y-%m-%d', SUBSTR(bokforingsdatum, 1, 10))
                    ELSE NULL
                END as transaction_date,
                COALESCE(text, 'SEB Transaction') as description,
                belopp as amount,
                'SEK' as currency,
                '{staging_table}' as staging_table,
                CONCAT(file_hash, '_', CAST(row_number AS STRING)) as staging_row_id,
                business_key
            FROM `{project_id}.{dataset_id}.{staging_table}`
            WHERE bokforingsdatum IS NOT NULL  -- Only process records with valid dates
            AND NOT EXISTS (
                SELECT 1 FROM `{project_id}.{dataset_id}.transactions_standardized` ts
                WHERE ts.business_key = `{project_id}.{dataset_id}.{staging_table}`.business_key
            )
            """
        
        elif source_bank == 'revolut':
            return f"""
            INSERT INTO `{project_id}.{dataset_id}.transactions_standardized`
            (transaction_id, source_bank, source_file, upload_timestamp, file_hash,
             transaction_date, description, amount, currency, staging_table, staging_row_id, business_key)
            SELECT 
                GENERATE_UUID() as transaction_id,
                'revolut' as source_bank,
                source_file,
                upload_timestamp,
                file_hash,
                CASE 
                    WHEN completed_date IS NOT NULL 
                    THEN PARSE_DATE('%Y-%m-%d', SUBSTR(completed_date, 1, 10))
                    ELSE NULL
                END as transaction_date,
                COALESCE(description, 'Revolut Transaction') as description,
                (amount - COALESCE(fee, 0)) as amount,  -- Subtract fees from amount
                COALESCE(currency, 'SEK') as currency,
                '{staging_table}' as staging_table,
                CONCAT(file_hash, '_', CAST(row_number AS STRING)) as staging_row_id,
                business_key
            FROM `{project_id}.{dataset_id}.{staging_table}`
            WHERE completed_date IS NOT NULL  -- Only process records with valid dates
            AND NOT EXISTS (
                SELECT 1 FROM `{project_id}.{dataset_id}.transactions_standardized` ts
                WHERE ts.business_key = `{project_id}.{dataset_id}.{staging_table}`.business_key
            )
            """
        
        elif source_bank == 'firstcard':
            return f"""
            INSERT INTO `{project_id}.{dataset_id}.transactions_standardized`
            (transaction_id, source_bank, source_file, upload_timestamp, file_hash,
             transaction_date, description, amount, currency, staging_table, staging_row_id, business_key)
            SELECT 
                GENERATE_UUID() as transaction_id,
                'firstcard' as source_bank,
                source_file,
                upload_timestamp,
                file_hash,
                CASE 
                    WHEN datum IS NOT NULL 
                    THEN PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10))
                    ELSE NULL
                END as transaction_date,
                COALESCE(reseinformation_inkopsplats, ytterligare_information, 'FirstCard Transaction') as description,
                belopp as amount,
                COALESCE(valuta, 'SEK') as currency,
                '{staging_table}' as staging_table,
                CONCAT(file_hash, '_', CAST(row_number AS STRING)) as staging_row_id,
                business_key
            FROM `{project_id}.{dataset_id}.{staging_table}`
            WHERE datum IS NOT NULL  -- Only process records with valid dates
            AND NOT EXISTS (
                SELECT 1 FROM `{project_id}.{dataset_id}.transactions_standardized` ts
                WHERE ts.business_key = `{project_id}.{dataset_id}.{staging_table}`.business_key
            )
            """
        
        elif source_bank == 'strawberry':
            return f"""
            INSERT INTO `{project_id}.{dataset_id}.transactions_standardized`
            (transaction_id, source_bank, source_file, upload_timestamp, file_hash,
             transaction_date, description, amount, currency, staging_table, staging_row_id, business_key)
            SELECT 
                GENERATE_UUID() as transaction_id,
                'strawberry' as source_bank,
                source_file,
                upload_timestamp,
                file_hash,
                CASE 
                    WHEN datum IS NOT NULL 
                    THEN PARSE_DATE('%Y-%m-%d', SUBSTR(datum, 1, 10))
                    ELSE NULL
                END as transaction_date,
                COALESCE(specifikation, 'Strawberry Transaction') as description,
                belopp as amount,
                COALESCE(valuta, 'SEK') as currency,
                '{staging_table}' as staging_table,
                CONCAT(file_hash, '_', CAST(row_number AS STRING)) as staging_row_id,
                business_key
            FROM `{project_id}.{dataset_id}.{staging_table}`
            WHERE datum IS NOT NULL  -- Only process records with valid dates
            AND NOT EXISTS (
                SELECT 1 FROM `{project_id}.{dataset_id}.transactions_standardized` ts
                WHERE ts.business_key = `{project_id}.{dataset_id}.{staging_table}`.business_key
            )
            """
        
        else:
            raise ValueError(f"Unknown source bank: {source_bank}")
    
    def log_file_processing(self, file_path: Path, source_bank: str, file_hash: str, 
                           staging_records: int, standardized_records: int, status: str, error_message: str = None):
        """Log file processing status to BigQuery."""
        
        log_data = {
            "file_hash": file_hash,
            "filename": file_path.name,
            "source_bank": source_bank,
            "file_size_bytes": file_path.stat().st_size,
            "processed_timestamp": datetime.now(timezone.utc).isoformat(),  # Convert to ISO string
            "staging_records_processed": staging_records,
            "standardized_records_processed": standardized_records,
            "processing_status": status,
            "error_message": error_message
        }
        
        table_ref = self.client.dataset(self.dataset_id).table(self.log_table_id)
        
        try:
            errors = self.client.insert_rows_json(table_ref, [log_data])
            if errors:
                logger.error(f"Failed to log processing status: {errors}")
        except Exception as e:
            logger.error(f"Failed to log processing status: {e}")
    
    def generate_business_key(self, source_bank: str, row_data: dict) -> str:
        """
        Generate a business key for deduplication based on bank-specific logic.
        
        Business keys strategy:
        - SEB: Use verifikationsnummer if available, else date+amount+description
        - Others: Use date+amount+description (normalized)
        """
        import hashlib
        
        if source_bank == 'seb':
            # For SEB, verifikationsnummer is the primary unique identifier
            if row_data.get('verifikationsnummer') and pd.notna(row_data['verifikationsnummer']):
                return f"seb_verif_{int(row_data['verifikationsnummer'])}"
            
            # Fallback to business key for SEB transactions without verifikationsnummer
            date_str = str(row_data.get('bokforingsdatum', '')).strip()
            amount = str(row_data.get('belopp', '')).strip()
            desc = str(row_data.get('text', '')).strip().lower()
            
        elif source_bank == 'revolut':
            date_str = str(row_data.get('completed_date', '')).strip()[:10]  # Take just date part
            amount = str(row_data.get('amount', '')).strip()
            desc = str(row_data.get('description', '')).strip().lower()
            
        elif source_bank == 'firstcard':
            date_str = str(row_data.get('datum', '')).strip()
            amount = str(row_data.get('belopp', '')).strip()
            desc = str(row_data.get('ytterligare_information', '')).strip().lower()
            
        elif source_bank == 'strawberry':
            date_str = str(row_data.get('datum', '')).strip()
            amount = str(row_data.get('belopp', '')).strip()
            desc = str(row_data.get('specifikation', '')).strip().lower()
        
        else:
            raise ValueError(f"Unknown source bank: {source_bank}")
        
        # Normalize description (remove extra spaces, common variations)
        desc = ' '.join(desc.split())  # Normalize whitespace
        
        # Create business key from normalized components
        business_components = f"{source_bank}|{date_str}|{amount}|{desc}"
        
        # Hash it to create a consistent key (avoid too long strings)
        business_key = hashlib.md5(business_components.encode('utf-8')).hexdigest()
        
        return f"{source_bank}_biz_{business_key}"
    
    def check_business_key_duplicates(self, staging_data: List[Dict], source_bank: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Check for business key duplicates against existing standardized data.
        
        Returns:
            (new_records, duplicate_records)
        """
        if not staging_data:
            return [], []
        
        # Business keys should already be set in prepare_staging_data
        # Extract business keys to check
        business_keys = [record['business_key'] for record in staging_data]
        
        # Query existing business keys in standardized table
        placeholders = ', '.join([f"@key_{i}" for i in range(len(business_keys))])
        query = f"""
        SELECT DISTINCT business_key
        FROM `{self.config.gcp_project_id}.{self.dataset_id}.transactions_standardized`
        WHERE business_key IN ({placeholders})
        """
        
        # Create query parameters
        query_parameters = [
            bigquery.ScalarQueryParameter(f"key_{i}", "STRING", key)
            for i, key in enumerate(business_keys)
        ]
        
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        
        try:
            results = self.client.query(query, job_config=job_config)
            existing_keys = {row.business_key for row in results}
            
            # Separate new vs duplicate records
            new_records = []
            duplicate_records = []
            
            for record in staging_data:
                if record['business_key'] in existing_keys:
                    duplicate_records.append(record)
                else:
                    new_records.append(record)
            
            return new_records, duplicate_records
            
        except Exception as e:
            logger.warning(f"Could not check business key duplicates: {e}")
            # On error, assume all are new (safer than skipping)
            return staging_data, []

def detect_bank_from_filename(filename: str) -> Optional[str]:
    """Detect bank source from filename."""
    filename_lower = filename.lower()
    if 'seb' in filename_lower:
        return 'seb'
    elif 'revolut' in filename_lower:
        return 'revolut'
    elif 'firstcard' in filename_lower or 'first' in filename_lower:
        return 'firstcard'
    elif 'strawberry' in filename_lower:
        return 'strawberry'
    return None

def main():
    parser = argparse.ArgumentParser(description="Upload transaction data to BigQuery (V2 - Data Warehouse)")
    parser.add_argument("path", help="Path to Excel file or directory")
    parser.add_argument("--bank", choices=['seb', 'revolut', 'firstcard', 'strawberry', 'all'], 
                       help="Bank source (required for single file, optional for directory)")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be uploaded without actually uploading")
    parser.add_argument("--stage-only", action="store_true",
                       help="Only upload to staging tables, skip transformation to standardized")
    parser.add_argument("--force-duplicates", action="store_true",
                       help="Force upload even if duplicate transactions are detected")
    
    args = parser.parse_args()
    
    try:
        config = Config()
        uploader = TransactionUploaderV2(config)
        
        path = Path(args.path)
        
        if path.is_file():
            # Single file upload
            if not args.bank:
                detected_bank = detect_bank_from_filename(path.name)
                if detected_bank:
                    logger.info(f"🔍 Auto-detected bank: {detected_bank}")
                    args.bank = detected_bank
                else:
                    logger.error("❌ Could not detect bank from filename. Please specify --bank")
                    sys.exit(1)
            
            # Upload to staging
            success, records, error = uploader.upload_to_staging(path, args.bank, args.dry_run, args.force_duplicates)
            if not success:
                logger.error(f"❌ Staging upload failed: {error}")
                sys.exit(1)
            
            logger.info(f"✅ Staging upload completed: {records} records")
            
            # Transform to standardized (unless stage-only)
            if not args.stage_only and not args.dry_run:
                if uploader.transform_staging_to_standardized(args.bank, args.dry_run):
                    logger.info("✅ Transformation to standardized table completed")
                else:
                    logger.error("❌ Transformation failed")
                    sys.exit(1)
                
        elif path.is_dir():
            # Directory upload
            excel_files = list(path.glob("*.xlsx")) + list(path.glob("*.xls"))
            
            if not excel_files:
                logger.error(f"❌ No Excel files found in {path}")
                sys.exit(1)
            
            total_records = 0
            successful_files = 0
            
            for file_path in excel_files:
                bank = args.bank if args.bank != 'all' else detect_bank_from_filename(file_path.name)
                
                if not bank:
                    logger.warning(f"⚠️  Skipping {file_path.name}: Could not detect bank")
                    continue
                
                success, records, error = uploader.upload_to_staging(file_path, bank, args.dry_run, args.force_duplicates)
                if success:
                    total_records += records
                    successful_files += 1
                else:
                    logger.error(f"❌ Failed to upload {file_path.name}: {error}")
            
            logger.info(f"✅ Batch staging upload completed: {successful_files} files, {total_records} total records")
            
            # Transform all to standardized (unless stage-only)
            if not args.stage_only and not args.dry_run:
                if uploader.transform_staging_to_standardized(None, args.dry_run):
                    logger.info("✅ Transformation to standardized table completed for all banks")
                else:
                    logger.error("❌ Some transformations failed")
                    sys.exit(1)
        
        else:
            logger.error(f"❌ Path not found: {path}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Script failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 