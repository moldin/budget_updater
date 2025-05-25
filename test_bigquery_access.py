#!/usr/bin/env python3
"""Test BigQuery access using exact same setup as working script."""

import logging
import sys
from pathlib import Path

# Add project root to path for imports - same as working script
sys.path.append(str(Path(__file__).parent.parent))

from google.cloud import bigquery
from src.budget_updater.config import Config

# Configure logging - same as working script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_bigquery_access():
    """Test BigQuery access using exact same pattern as working upload script."""
    try:
        config = Config()
        client = bigquery.Client(project=config.gcp_project_id)
        
        print("🔍 Testing BigQuery access...")
        
        # Simple count query - same table as before
        query = f"""
        SELECT COUNT(*) as count
        FROM `{config.gcp_project_id}.{config.bigquery_dataset_id}.sheet_transactions`
        WHERE account = '💳 First Card'
        """
        
        logger.info("Running test query...")
        result = list(client.query(query).result())
        count = result[0].count if result else 0
        
        print(f"✅ Success! FirstCard transactions: {count:,}")
        return True
        
    except Exception as e:
        logger.error(f"❌ BigQuery access failed: {e}")
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    test_bigquery_access() 