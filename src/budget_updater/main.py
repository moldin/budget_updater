#!/usr/bin/env python3
"""Main module for Budget Updater application."""

import argparse
import logging
import sys
from pathlib import Path

# Use relative imports within the package
from .sheets_api import SheetAPI
from .vertex_ai import VertexAI
from .parsers import parse_seb # Import the SEB parser
from .transformation import transform_transactions # Import the transformation function

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
        help="Account name identifier (e.g., seb, firstcard, revolut, strawberry). Must match part of an account in BackendData Col I.",
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
    
    parser.add_argument(
        "--analyze", "-a",
        action="store_true",
        help="Analyze spreadsheet structure and save to sheet_analysis.md"
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
            
        # Analyze spreadsheet structure
        if args.analyze:
            logger.info("Analyzing spreadsheet structure")
            sheets_api.analyze_sheet_structure()
            logger.info("Analysis complete. See sheet_analysis.md for details")
            return
            
        # If not in test or analyze mode, we expect file and account arguments
        if not args.file or not args.account:
            logger.error("Both --file and --account arguments are required unless using --test or --analyze")
            sys.exit(1)
            
        # Validate account name
        # Access the pre-loaded accounts from the SheetAPI instance
        valid_accounts = sheets_api.accounts 
        if not valid_accounts:
             logger.error("Could not retrieve valid account names from the spreadsheet. Ensure 'BackendData' tab, Column I is populated and SheetAPI initialized correctly.")
             sys.exit(1)
             
        account_cli_arg = args.account 
        
        matched_account = None
        for valid_acc in valid_accounts:
            # Match if CLI arg is a substring of the full name, case-insensitive
            if account_cli_arg.lower() in valid_acc.lower():
                matched_account = valid_acc
                logger.info(f"Matched CLI argument '{account_cli_arg}' to sheet account: {valid_acc}")
                break
                
        if not matched_account:
            # Try matching against the first word (e.g., emoji or main name) if full substring match failed
            for valid_acc in valid_accounts:
                first_word = valid_acc.split()[0] if valid_acc else ''
                if account_cli_arg.lower() == first_word.lower():
                    matched_account = valid_acc
                    logger.info(f"Matched CLI argument '{account_cli_arg}' to first word of sheet account: {valid_acc}")
                    break
            
        if not matched_account:
            valid_options_display = [a.split()[0] for a in valid_accounts if a] # Show first word as hint
            logger.error(f"Invalid account name: '{args.account}'. Valid options based on sheet: {valid_options_display}")
            logger.debug(f"Full valid account names found in sheet: {valid_accounts}")
            sys.exit(1)
            
        account_name_validated = matched_account # Use the full, validated name going forward
        logger.info(f"Processing for account: {account_name_validated}")

        file_path = Path(args.file)
        if not file_path.is_file(): # Check if it's actually a file
            logger.error(f"File not found or is not a file: {file_path}")
            sys.exit(1)
            
        # --- Parsing Stage ---
        logger.info(f"Parsing file: {file_path}")
        parsed_data = None
        # TODO: Implement parser selection logic in future iterations
        # For now, assume SEB if account name contains 'seb'
        if 'seb' in account_name_validated.lower(): 
            parsed_data = parse_seb(file_path)
        else:
            logger.error(f"No parser implemented yet for account type associated with '{account_name_validated}'. Only SEB is supported currently.")
            sys.exit(1)

        if parsed_data is None:
            logger.error(f"Parsing failed for file: {file_path}")
            sys.exit(1)
        elif parsed_data.empty:
            logger.warning(f"No transactions found or parsed from file: {file_path}. Exiting.")
            sys.exit(0)
        else:
             logger.info(f"Successfully parsed {len(parsed_data)} transactions.")

        # --- Transformation Stage ---
        logger.info("Transforming parsed data...")
        transformed_data = transform_transactions(parsed_data, account_name_validated)

        if transformed_data is None:
            logger.error("Transformation failed.")
            sys.exit(1)
        elif transformed_data.empty:
            logger.warning("No transactions available after transformation. Exiting.")
            sys.exit(0)
        else:
            logger.info(f"Successfully transformed {len(transformed_data)} transactions.")

        # --- Upload Stage ---
        logger.info(f"Appending {len(transformed_data)} transactions to 'New Transactions' tab...")
        success = sheets_api.append_transactions(transformed_data)
        
        if success:
            logger.info("Successfully appended transactions to the Google Sheet.")
        else:
            logger.error("Failed to append transactions to the Google Sheet.")
            sys.exit(1)

        # --- Vertex AI Initialization (Keep for future use) ---
        # logger.info("Initializing Vertex AI client (for future categorization step)...")
        # try:
        #     vertex_ai = VertexAI() # Initialize to check config
        #     logger.info("Vertex AI client initialized successfully.")
        # except Exception as e:
        #     logger.error(f"Failed to initialize Vertex AI client: {e}")
            # Decide if this is critical - for Iteration 2, maybe just warn
            # sys.exit(1)

        logger.info("Processing completed successfully")
        
    except Exception as e:
        logger.exception(f"An unexpected error occurred in the main execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 