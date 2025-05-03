#!/usr/bin/env python3
"""Main module for Budget Updater application."""

import argparse
import logging
import sys
from pathlib import Path

from budget_updater.sheets_api import SheetAPI
from budget_updater.vertex_ai import VertexAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Budget Updater - Bank Transaction Processor for Aspire Budget Sheet"
    )
    
    parser.add_argument(
        "--file", help="Path to the bank export file", type=str
    )
    
    parser.add_argument(
        "--account", 
        help="Account name (e.g., seb, firstcard, revolut, strawberry)",
        type=str,
    )
    
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true", 
        help="Enable verbose logging"
    )
    
    parser.add_argument(
        "--test", 
        action="store_true", 
        help="Run in test mode (adds dummy data to New Transactions tab)"
    )
    
    return parser.parse_args()


def main():
    """Execute the main application logic."""
    args = parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Starting Budget Updater")
    
    try:
        # Initialize Google Sheets API connection
        sheets_api = SheetAPI()
        
        # Test connection by writing dummy data
        if args.test:
            logger.info("Running in test mode")
            sheets_api.append_dummy_transaction()
            logger.info("Successfully added dummy transaction to New Transactions tab")
            return
            
        # If not in test mode, we expect file and account arguments
        if not args.file or not args.account:
            logger.error("Both --file and --account arguments are required")
            sys.exit(1)
            
        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            sys.exit(1)
            
        # Initialize Vertex AI connection
        vertex_ai = VertexAI()
        
        # TODO: Implement actual file parsing and processing logic in future iterations
        
        logger.info("Processing completed successfully")
        
    except Exception as e:
        logger.exception(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 