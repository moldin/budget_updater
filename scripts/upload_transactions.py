#!/usr/bin/env python3
"""
Transaction upload script for BigQuery.

This script uploads transaction data from Excel files to BigQuery, handling
deduplication, error recovery, and all supported bank formats.

Usage:
    python scripts/upload_transactions.py [file_path] [--bank BANK] [--dry-run]
    
Examples:
    python scripts/upload_transactions.py data/seb.xlsx --bank seb
    python scripts/upload_transactions.py data/revolut_new.xlsx --bank revolut --dry-run
    python scripts/upload_transactions.py data/ --bank all  # Process all files in directory
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
from budget_updater.parsers import PARSER_REGISTRY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TransactionUploader:
    """Handles uploading transaction data to BigQuery with deduplication and error handling."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
        self.table_id = "raw_transactions"
        self.log_table_id = "file_processing_log"
        
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
    
    def log_file_processing(self, file_path: Path, source_bank: str, file_hash: str, 
                           records_processed: int, status: str, error_message: str = None):
        """Log file processing status to BigQuery."""
        
        log_data = {
            "file_hash": file_hash,
            "filename": file_path.name,
            "source_bank": source_bank,
            "file_size_bytes": file_path.stat().st_size,
            "processed_timestamp": datetime.now(timezone.utc),
            "records_processed": records_processed,
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
    
    def map_raw_columns(self, df: pd.DataFrame, source_bank: str) -> Dict:
        """Map original DataFrame columns to BigQuery raw columns based on bank source."""
        
        # Get the original column names from the DataFrame
        original_columns = df.columns.tolist()
        
        # Bank-specific column mappings
        column_mappings = {
            'seb': {
                'Bokföringsdatum': 'seb_bokforingsdatum',
                'Valutadatum': 'seb_valutadatum', 
                'Verifikationsnummer': 'seb_verifikationsnummer',
                'Text': 'seb_text',
                'Belopp': 'seb_belopp',
                'Saldo': 'seb_saldo'
            },
            'revolut': {
                'Type': 'revolut_type',
                'Product': 'revolut_product',
                'Started Date': 'revolut_started_date',
                'Completed Date': 'revolut_completed_date',
                'Description': 'revolut_description',
                'Amount': 'revolut_amount',
                'Fee': 'revolut_fee',
                'Currency': 'revolut_currency',
                'State': 'revolut_state',
                'Balance': 'revolut_balance'
            },
            'firstcard': {
                'Datum': 'firstcard_datum',
                'Ytterligare information': 'firstcard_ytterligare_info',
                'Reseinformation / Inköpsplats': 'firstcard_reseinformation',
                'Valuta': 'firstcard_valuta',
                'växlingskurs': 'firstcard_vaxlingskurs',
                'Utländskt belopp': 'firstcard_utlandskt_belopp',
                'Belopp': 'firstcard_belopp',
                'Moms': 'firstcard_moms',
                'Kort': 'firstcard_kort'
            },
            'strawberry': {
                'Datum': 'strawberry_datum',
                'Bokfört': 'strawberry_bokfort',
                'Specifikation': 'strawberry_specifikation',
                'Ort': 'strawberry_ort',
                'Valuta': 'strawberry_valuta',
                'Utl.belopp/moms': 'strawberry_utl_belopp_moms',
                'Belopp': 'strawberry_belopp'
            }
        }
        
        mapping = column_mappings.get(source_bank, {})
        
        # Create result dict with all raw columns as None
        result = {}
        
        # Add the mapped columns
        for original_col in original_columns:
            if original_col in mapping:
                bigquery_col = mapping[original_col]
                result[bigquery_col] = df[original_col].tolist()
        
        return result
    
    def create_transaction_id(self, source_bank: str, file_hash: str, row_index: int, 
                            parsed_date: str, parsed_description: str, parsed_amount: float) -> str:
        """Create unique transaction ID based on source data."""
        id_string = f"{source_bank}_{file_hash}_{row_index}_{parsed_date}_{parsed_description}_{parsed_amount}"
        return hashlib.md5(id_string.encode()).hexdigest()
    
    def prepare_bigquery_data(self, parsed_df: pd.DataFrame, original_df: pd.DataFrame, 
                            source_bank: str, file_path: Path, file_hash: str) -> List[Dict]:
        """Prepare data for BigQuery insertion."""
        
        raw_columns = self.map_raw_columns(original_df, source_bank)
        bigquery_rows = []
        
        upload_timestamp = datetime.now(timezone.utc)
        
        for i, row in parsed_df.iterrows():
            # Create base record with standardized columns
            record = {
                "transaction_id": self.create_transaction_id(
                    source_bank, file_hash, i,
                    str(row['ParsedDate']), row['ParsedDescription'], row['ParsedAmount']
                ),
                "source_bank": source_bank,
                "source_file": file_path.name,
                "upload_timestamp": upload_timestamp,
                "file_hash": file_hash,
                "parsed_date": row['ParsedDate'].date() if pd.notna(row['ParsedDate']) else None,
                "parsed_description": str(row['ParsedDescription']),
                "parsed_amount": float(row['ParsedAmount']) if pd.notna(row['ParsedAmount']) else None,
            }
            
            # Add raw columns for this specific bank
            for col_name, col_values in raw_columns.items():
                if i < len(col_values):
                    value = col_values[i]
                    # Convert to appropriate type
                    if pd.isna(value):
                        record[col_name] = None
                    elif col_name.endswith('_datum') or col_name.endswith('_date'):
                        record[col_name] = str(value)
                    elif 'belopp' in col_name or 'amount' in col_name or col_name.endswith('_fee') or col_name.endswith('_balance'):
                        record[col_name] = float(value) if pd.notna(value) else None
                    elif col_name.endswith('_nummer') or col_name.endswith('_size_bytes'):
                        record[col_name] = int(value) if pd.notna(value) else None
                    else:
                        record[col_name] = str(value)
                else:
                    record[col_name] = None
            
            bigquery_rows.append(record)
        
        return bigquery_rows
    
    def upload_file(self, file_path: Path, source_bank: str, dry_run: bool = False) -> Tuple[bool, int, str]:
        """
        Upload a single file to BigQuery.
        
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
            
            # Parse the file using our existing parsers
            if source_bank not in PARSER_REGISTRY:
                error_msg = f"No parser available for bank: {source_bank}"
                logger.error(error_msg)
                return False, 0, error_msg
            
            # Read original file for raw columns
            original_df = pd.read_excel(file_path)
            
            # Parse using our standardized parser
            parser_func = PARSER_REGISTRY[source_bank]
            parsed_df = parser_func(file_path)
            
            if parsed_df is None or len(parsed_df) == 0:
                error_msg = f"Failed to parse file or no data found"
                logger.error(error_msg)
                return False, 0, error_msg
            
            logger.info(f"📊 Parsed {len(parsed_df)} transactions")
            
            # Prepare data for BigQuery
            bigquery_data = self.prepare_bigquery_data(
                parsed_df, original_df, source_bank, file_path, file_hash
            )
            
            if dry_run:
                logger.info(f"🏃‍♂️ DRY RUN: Would upload {len(bigquery_data)} records")
                logger.info("Sample record:")
                if bigquery_data:
                    sample = {k: v for k, v in list(bigquery_data[0].items())[:8]}
                    for k, v in sample.items():
                        logger.info(f"  {k}: {v}")
                return True, len(bigquery_data), "Dry run successful"
            
            # Upload to BigQuery
            table_ref = self.client.dataset(self.dataset_id).table(self.table_id)
            
            logger.info(f"⬆️  Uploading {len(bigquery_data)} records to BigQuery...")
            errors = self.client.insert_rows_json(table_ref, bigquery_data)
            
            if errors:
                error_msg = f"BigQuery insertion errors: {errors}"
                logger.error(error_msg)
                self.log_file_processing(file_path, source_bank, file_hash, 0, "FAILED", error_msg)
                return False, 0, error_msg
            
            # Log successful processing
            self.log_file_processing(file_path, source_bank, file_hash, len(bigquery_data), "SUCCESS")
            
            logger.info(f"✅ Successfully uploaded {len(bigquery_data)} transactions")
            return True, len(bigquery_data), None
            
        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error(error_msg)
            try:
                self.log_file_processing(file_path, source_bank, file_hash, 0, "FAILED", error_msg)
            except:
                pass  # Don't fail if logging fails
            return False, 0, error_msg

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
    parser = argparse.ArgumentParser(description="Upload transaction data to BigQuery")
    parser.add_argument("path", help="Path to Excel file or directory")
    parser.add_argument("--bank", choices=['seb', 'revolut', 'firstcard', 'strawberry', 'all'], 
                       help="Bank source (required for single file, optional for directory)")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be uploaded without actually uploading")
    
    args = parser.parse_args()
    
    try:
        config = Config()
        uploader = TransactionUploader(config)
        
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
            
            success, records, error = uploader.upload_file(path, args.bank, args.dry_run)
            if success:
                logger.info(f"🎉 Upload completed: {records} records")
            else:
                logger.error(f"❌ Upload failed: {error}")
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
                
                success, records, error = uploader.upload_file(file_path, bank, args.dry_run)
                if success:
                    total_records += records
                    successful_files += 1
                else:
                    logger.error(f"❌ Failed to upload {file_path.name}: {error}")
            
            logger.info(f"🎉 Batch upload completed: {successful_files} files, {total_records} total records")
        
        else:
            logger.error(f"❌ Path not found: {path}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"❌ Script failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 