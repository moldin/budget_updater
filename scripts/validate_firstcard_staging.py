#!/usr/bin/env python3
"""
Validate FirstCard staging file for BigQuery compatibility.

This script validates that the staging file contains valid data that is compatible
with the firstcard_transactions_raw BigQuery table schema and business requirements.
"""

import logging
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Tuple

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


class FirstCardStagingValidator:
    """Validate FirstCard staging file for BigQuery upload."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id)
        self.dataset_id = config.bigquery_dataset_id
        
        # Expected schema for firstcard_transactions_raw
        self.expected_schema = {
            'file_hash': str,
            'source_file': str,
            'upload_timestamp': str,
            'row_number': int,
            'datum': str,
            'ytterligare_information': (str, type(None)),
            'reseinformation_inkopsplats': (str, type(None)),
            'valuta': (str, type(None)),
            'vaxlingskurs': (float, type(None)),
            'utlandskt_belopp': (float, type(None)),
            'belopp': (float, type(None)),
            'moms': (float, type(None)),
            'kort': (str, type(None)),
            'business_key': str
        }
        
        self.validation_errors = []
        self.validation_warnings = []
    
    def load_staging_file(self, staging_file: Path) -> Dict:
        """Load and parse staging file."""
        try:
            logger.info(f"📖 Loading staging file: {staging_file}")
            
            if not staging_file.exists():
                raise FileNotFoundError(f"Staging file not found: {staging_file}")
            
            with open(staging_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"✅ Loaded staging file ({staging_file.stat().st_size:,} bytes)")
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in staging file: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load staging file: {e}")
    
    def validate_file_structure(self, data: Dict) -> bool:
        """Validate basic file structure."""
        logger.info("🔍 Validating file structure...")
        
        # Check required top-level keys
        required_keys = ['metadata', 'transactions']
        for key in required_keys:
            if key not in data:
                self.validation_errors.append(f"Missing required top-level key: {key}")
        
        if 'metadata' in data:
            metadata = data['metadata']
            required_metadata = ['extraction_timestamp', 'cutoff_date', 'total_transactions']
            for key in required_metadata:
                if key not in metadata:
                    self.validation_warnings.append(f"Missing metadata key: {key}")
        
        if 'transactions' in data:
            transactions = data['transactions']
            if not isinstance(transactions, list):
                self.validation_errors.append("'transactions' must be a list")
            else:
                logger.info(f"   📋 Found {len(transactions)} transactions")
        
        return len(self.validation_errors) == 0
    
    def validate_transaction_schema(self, transactions: List[Dict]) -> bool:
        """Validate each transaction against expected schema."""
        logger.info("🔍 Validating transaction schemas...")
        
        schema_errors = 0
        
        for i, transaction in enumerate(transactions):
            transaction_errors = []
            
            # Remove debug fields before validation
            clean_transaction = {k: v for k, v in transaction.items() 
                               if not k.startswith('_debug')}
            
            # Check required fields
            for field, expected_type in self.expected_schema.items():
                if field not in clean_transaction:
                    transaction_errors.append(f"Missing field: {field}")
                    continue
                
                value = clean_transaction[field]
                
                # Check type (allow None for nullable fields)
                if isinstance(expected_type, tuple):
                    # Multiple allowed types (e.g., str or None)
                    if not isinstance(value, expected_type):
                        transaction_errors.append(
                            f"Field '{field}' has wrong type: {type(value).__name__}, "
                            f"expected one of: {[t.__name__ for t in expected_type]}"
                        )
                else:
                    # Single expected type
                    if not isinstance(value, expected_type):
                        transaction_errors.append(
                            f"Field '{field}' has wrong type: {type(value).__name__}, "
                            f"expected: {expected_type.__name__}"
                        )
            
            # Check for unexpected fields (excluding debug fields)
            expected_fields = set(self.expected_schema.keys())
            actual_fields = set(clean_transaction.keys())
            unexpected_fields = actual_fields - expected_fields
            
            if unexpected_fields:
                transaction_errors.append(f"Unexpected fields: {unexpected_fields}")
            
            if transaction_errors:
                schema_errors += 1
                if schema_errors <= 5:  # Only show first 5 errors
                    for error in transaction_errors:
                        self.validation_errors.append(f"Transaction {i+1}: {error}")
                elif schema_errors == 6:
                    self.validation_errors.append("... (more schema errors truncated)")
        
        if schema_errors == 0:
            logger.info("   ✅ All transactions have valid schema")
        else:
            logger.error(f"   ❌ {schema_errors} transactions have schema errors")
        
        return schema_errors == 0
    
    def validate_business_rules(self, transactions: List[Dict]) -> bool:
        """Validate business logic and constraints."""
        logger.info("🔍 Validating business rules...")
        
        business_errors = 0
        date_errors = 0
        amount_errors = 0
        key_errors = 0
        
        business_keys = set()
        dates = []
        amounts = []
        
        for i, transaction in enumerate(transactions):
            # Validate date format
            datum = transaction.get('datum')
            if datum:
                try:
                    parsed_date = datetime.strptime(datum, '%Y-%m-%d')
                    dates.append(parsed_date)
                except ValueError:
                    date_errors += 1
                    if date_errors <= 3:
                        self.validation_errors.append(
                            f"Transaction {i+1}: Invalid date format '{datum}', expected YYYY-MM-DD"
                        )
            
            # Validate amounts
            belopp = transaction.get('belopp')
            if belopp is not None:
                if not isinstance(belopp, (int, float)):
                    amount_errors += 1
                    if amount_errors <= 3:
                        self.validation_errors.append(
                            f"Transaction {i+1}: Amount must be numeric, got {type(belopp).__name__}"
                        )
                else:
                    amounts.append(belopp)
                    # Check for reasonable amount range
                    if abs(belopp) > 1000000:  # 1 million SEK
                        self.validation_warnings.append(
                            f"Transaction {i+1}: Large amount {belopp} SEK"
                        )
            
            # Validate business key uniqueness
            business_key = transaction.get('business_key')
            if business_key:
                if business_key in business_keys:
                    key_errors += 1
                    if key_errors <= 3:
                        self.validation_errors.append(
                            f"Transaction {i+1}: Duplicate business_key '{business_key}'"
                        )
                else:
                    business_keys.add(business_key)
            
            # Validate required business fields
            if not transaction.get('valuta'):
                self.validation_warnings.append(f"Transaction {i+1}: Missing currency")
            
            if not transaction.get('kort'):
                self.validation_warnings.append(f"Transaction {i+1}: Missing card info")
        
        # Summary statistics
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            logger.info(f"   📅 Date range: {min_date.date()} to {max_date.date()}")
        
        if amounts:
            min_amount = min(amounts)
            max_amount = max(amounts)
            total_amount = sum(amounts)
            logger.info(f"   💰 Amount range: {min_amount:.2f} to {max_amount:.2f} SEK")
            logger.info(f"   💰 Total amount: {total_amount:.2f} SEK")
        
        logger.info(f"   🔑 Unique business keys: {len(business_keys)}")
        
        total_business_errors = date_errors + amount_errors + key_errors
        if total_business_errors == 0:
            logger.info("   ✅ All business rules validated")
        else:
            logger.error(f"   ❌ {total_business_errors} business rule violations")
        
        return total_business_errors == 0
    
    def check_existing_duplicates(self, transactions: List[Dict]) -> Tuple[int, List[str]]:
        """Check for duplicates against existing BigQuery data."""
        logger.info("🔍 Checking for existing duplicates in BigQuery...")
        
        business_keys = [t.get('business_key') for t in transactions if t.get('business_key')]
        
        if not business_keys:
            logger.info("   ℹ️  No business keys to check")
            return 0, []
        
        try:
            # Check existing keys in BigQuery
            placeholders = ', '.join([f"'{key}'" for key in business_keys])
            query = f"""
            SELECT business_key, COUNT(*) as count
            FROM `{self.config.gcp_project_id}.{self.dataset_id}.firstcard_transactions_raw`
            WHERE business_key IN ({placeholders})
            GROUP BY business_key
            """
            
            result = self.client.query(query).result()
            existing_keys = [row.business_key for row in result]
            
            if existing_keys:
                logger.warning(f"   ⚠️  Found {len(existing_keys)} existing duplicates")
                return len(existing_keys), existing_keys
            else:
                logger.info("   ✅ No duplicates found in BigQuery")
                return 0, []
                
        except Exception as e:
            logger.warning(f"   ⚠️  Could not check BigQuery duplicates: {e}")
            self.validation_warnings.append(f"Failed to check BigQuery duplicates: {e}")
            return 0, []
    
    def validate_staging_file(self, staging_file: Path) -> Tuple[bool, Dict]:
        """
        Main validation function.
        
        Returns:
            (is_valid, validation_report)
        """
        logger.info("🚀 Starting staging file validation")
        
        self.validation_errors = []
        self.validation_warnings = []
        
        try:
            # Load file
            data = self.load_staging_file(staging_file)
            
            # Validate file structure
            structure_valid = self.validate_file_structure(data)
            
            if not structure_valid:
                logger.error("❌ File structure validation failed")
                return False, self.create_validation_report(data)
            
            transactions = data.get('transactions', [])
            metadata = data.get('metadata', {})
            
            # Validate transaction schemas
            schema_valid = self.validate_transaction_schema(transactions)
            
            # Validate business rules
            business_valid = self.validate_business_rules(transactions)
            
            # Check for existing duplicates
            duplicate_count, duplicate_keys = self.check_existing_duplicates(transactions)
            
            # Overall validation result
            is_valid = structure_valid and schema_valid and business_valid
            
            # Create validation report
            validation_report = self.create_validation_report(data, duplicate_count, duplicate_keys)
            
            if is_valid and duplicate_count == 0:
                logger.info("✅ Validation PASSED - File is ready for upload")
            elif is_valid and duplicate_count > 0:
                logger.warning("⚠️  Validation PASSED with warnings - File contains duplicates")
            else:
                logger.error("❌ Validation FAILED - File is not ready for upload")
            
            return is_valid, validation_report
            
        except Exception as e:
            logger.error(f"❌ Validation failed with error: {e}")
            self.validation_errors.append(f"Validation error: {e}")
            return False, self.create_validation_report({})
    
    def create_validation_report(self, data: Dict, duplicate_count: int = 0, 
                                duplicate_keys: List[str] = None) -> Dict:
        """Create detailed validation report."""
        metadata = data.get('metadata', {})
        transactions = data.get('transactions', [])
        
        report = {
            'validation_timestamp': datetime.now().isoformat(),
            'file_info': {
                'total_transactions': len(transactions),
                'extraction_timestamp': metadata.get('extraction_timestamp'),
                'cutoff_date': metadata.get('cutoff_date'),
                'date_range': metadata.get('date_range', {})
            },
            'validation_results': {
                'is_valid': len(self.validation_errors) == 0,
                'error_count': len(self.validation_errors),
                'warning_count': len(self.validation_warnings),
                'duplicate_count': duplicate_count
            },
            'errors': self.validation_errors,
            'warnings': self.validation_warnings,
            'duplicates': duplicate_keys or []
        }
        
        return report
    
    def save_validation_report(self, staging_file: Path, report: Dict) -> Path:
        """Save validation report to file."""
        report_file = staging_file.with_suffix('.validation_report.json')
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📄 Validation report saved: {report_file}")
            return report_file
            
        except Exception as e:
            logger.error(f"Failed to save validation report: {e}")
            raise


def main():
    """Run staging file validation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate FirstCard staging file")
    parser.add_argument("staging_file", help="Path to staging file to validate")
    parser.add_argument("--save-report", action="store_true", 
                       help="Save validation report to file")
    
    args = parser.parse_args()
    
    try:
        staging_file = Path(args.staging_file)
        
        config = Config()
        validator = FirstCardStagingValidator(config)
        
        is_valid, report = validator.validate_staging_file(staging_file)
        
        # Save report if requested
        if args.save_report:
            validator.save_validation_report(staging_file, report)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*60}")
        print(f"File: {staging_file}")
        print(f"Transactions: {report['file_info']['total_transactions']}")
        print(f"Valid: {'✅ YES' if is_valid else '❌ NO'}")
        print(f"Errors: {report['validation_results']['error_count']}")
        print(f"Warnings: {report['validation_results']['warning_count']}")
        print(f"Duplicates: {report['validation_results']['duplicate_count']}")
        
        if is_valid:
            print(f"\n🎉 Ready for upload! Run:")
            print(f"   python scripts/upload_firstcard_staging.py {staging_file}")
        else:
            print(f"\n❌ Fix errors before upload")
            if report['errors']:
                print(f"\nErrors:")
                for error in report['errors'][:10]:  # Show first 10 errors
                    print(f"  - {error}")
        
        if report['warnings']:
            print(f"\nWarnings:")
            for warning in report['warnings'][:5]:  # Show first 5 warnings
                print(f"  - {warning}")
        
        sys.exit(0 if is_valid else 1)
        
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 