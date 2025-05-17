#!/usr/bin/env python3
"""Main module for Budget Updater application."""

import argparse
import logging
import sys
import os # Added for environment variable check
from pathlib import Path # Import Path
from dotenv import load_dotenv # Import dotenv

# Use relative imports within the package
from .parsers import parse_seb # Import the SEB parser
from .transformation import transform_transactions # Import the transformation function
# from .categorizer import categorize_transaction # OLD categorizer - REMOVED
from . import adk_agent_service # NEW ADK Service
from tqdm import tqdm # Import tqdm
from . import config # Import config module itself
from .sheets_api import SheetAPI # Import the class
from .parsers import PARSER_REGISTRY # Import the registry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def parse_args(): # Removed valid_accounts_list as input for now
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Budget Updater - Bank Transaction Processor for Aspire Budget Sheet"
    )
    
    parser.add_argument(
        "--file", help="Path to the bank export file", type=str
    )
    
    # Update help text to show expected aliases
    valid_aliases = list(config.ACCOUNT_NAME_MAP.keys())
    help_text = f"Short account name alias (e.g., {', '.join(valid_aliases)})."
    parser.add_argument(
        "--account", 
        help=help_text,
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
    load_dotenv() 
    logger.info("Loaded environment variables from .env file (if present).")

    # Initialize ADK Runner and Session Service
    adk_runner = None
    adk_session_service = None
    try:
        adk_runner, adk_session_service = adk_agent_service.create_adk_runner_and_service()
        logger.info("ADK Runner and Session Service initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize ADK Runner and Session Service: {e}", exc_info=True)
        logger.error("Categorization via AI will not be possible. Please check GCP/ADK setup and .env variables.")
        # adk_runner and adk_session_service will remain None

    # Initialize SheetAPI *after* parsing basic args, before validation
    args = parse_args()

    # Set logging level based on verbosity
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Starting Budget Updater")
    
    try:
        # Initialize SheetAPI
        try:
            sheets_api = SheetAPI()
        except Exception as e:
            logger.error(f"Failed to initialize SheetAPI: {e}", exc_info=True)
            sys.exit(1)

        if sheets_api.service is None:
             logger.error("SheetAPI service could not be initialized. Cannot proceed.")
             sys.exit(1)
        
        # Handle test/analyze modes first
        if args.test:
            logger.info("Running in test mode")
            sheets_api.append_dummy_transaction()
            logger.info(f"Dummy transaction added to '{config.NEW_TRANSACTIONS_SHEET_NAME}' tab")
            return
            
        if args.analyze:
            logger.info("Analyzing spreadsheet structure")
            sheets_api.analyze_sheet_structure()
            logger.info("Analysis complete. See sheet_analysis.md for details")
            return
            
        # --- Argument and Account Validation ---
        if not args.file or not args.account:
            logger.error("Both --file and --account arguments are required.")
            sys.exit(1)
            
        account_cli_arg = args.account.lower() # Use lower case for lookup

        # 1. Look up the alias in the map
        account_name_mapped = config.ACCOUNT_NAME_MAP.get(account_cli_arg)
        
        if not account_name_mapped:
            logger.error(f"Unknown account alias: '{args.account}'. Valid aliases are: {list(config.ACCOUNT_NAME_MAP.keys())}")
            sys.exit(1)

        # 2. Verify the mapped name exists in the sheet
        valid_accounts_from_sheet = sheets_api.accounts # Get list from SheetAPI instance
        if not valid_accounts_from_sheet:
             logger.error("Could not retrieve valid account names from the spreadsheet.")
             sys.exit(1)
             
        if account_name_mapped not in valid_accounts_from_sheet:
             logger.error(f"Mapped account name '{account_name_mapped}' (from alias '{args.account}') not found in BackendData sheet (Column I).")
             logger.debug(f"Valid accounts found in sheet: {valid_accounts_from_sheet}")
             sys.exit(1)
             
        # 3. Use the validated full name
        account_name_validated = account_name_mapped
        logger.info(f"Processing for account: {account_name_validated} (mapped from alias '{args.account}')")

        # Check Vertex AI env vars using config
        # Note: categorizer.py also checks at import time, this is an additional check before processing.
        if not config.GOOGLE_CLOUD_PROJECT:
             logger.warning("GOOGLE_CLOUD_PROJECT environment variable not set. Categorization via AI will likely fail or use placeholder.")
             # Depending on requirements, could exit here: sys.exit(1)
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
             logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set. Categorization via AI will likely fail.")
             # Depending on requirements, could exit here: sys.exit(1)

        file_path = Path(args.file)
        if not file_path.is_file(): # Check if it's actually a file
            logger.error(f"File not found or is not a file: {file_path}")
            sys.exit(1)
            
        # --- Parsing Stage ---
        logger.info(f"Parsing file: {file_path}")
        parsed_data = None
        # Update parser selection logic to use the *alias* (account_cli_arg)
        # This assumes parser logic aligns with the aliases
        parser_function = PARSER_REGISTRY.get(account_cli_arg)
        if parser_function:
            parsed_data = parser_function(file_path)
        else:
            # This should ideally not be reached due to prior alias validation
            logger.error(f"No parser function found in registry for alias '{account_cli_arg}'. Check PARSER_REGISTRY in parsers.py.")
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
        # Pass the *validated full name* to transformation
        transformed_data = transform_transactions(parsed_data, account_name_validated)

        # transform_transactions now returns list, check if empty
        if not transformed_data:
            logger.warning("No transactions available after transformation (or transformation failed). Exiting.")
            sys.exit(0)
        else:
            logger.info(f"Successfully transformed {len(transformed_data)} transactions into list format.")

            # ---vvv--- ADD SORTING STEP ---vvv---
            logger.info(f"Sorting {len(transformed_data)} transactions by date...")
            try:
                # Sort the list of dictionaries in place based on the 'Date' key
                transformed_data.sort(key=lambda txn: txn['Date'])
                logger.info("Transactions sorted chronologically.")
            except KeyError:
                logger.error("Transformation failed to produce 'Date' key correctly. Cannot sort.")
                sys.exit(1)
            except Exception as sort_err:
                 logger.error(f"Error during sorting: {sort_err}", exc_info=True)
                 sys.exit(1)
            # ---^^^--- END SORTING STEP ---^^^---

        # --- Categorization Stage ---
        logger.info("Starting AI categorization...")
        final_transactions = []
        for txn in tqdm(transformed_data, desc="Categorizing Transactions", unit="txn"):
            original_memo = txn.get('Memo') # Get original memo safely
            date_str = txn.get('Date') # Expecting YYYY-MM-DD string from transform
            # Determine the amount string to send to the AI.  Transformation
            # stores ``Outflow`` and ``Inflow`` as formatted strings ("123,45")
            # with empty strings when the value is zero.  The previous logic
            # compared the ``Outflow`` string with the integer ``0`` which
            # always evaluated to ``True`` for non-empty strings.  This resulted
            # in ``amount_str`` sometimes being an empty string and the AI
            # receiving no amount.  Instead simply pick the non-empty value.

            outflow_str = txn.get('Outflow') or ""
            inflow_str = txn.get('Inflow') or ""
            amount_str = outflow_str if outflow_str else inflow_str
            account_name = txn.get('Account') # Account name should be the validated one

            if not all([date_str, amount_str is not None, original_memo is not None, account_name]):
                logger.warning(f"Transaction missing required fields for ADK categorization (Date, Amount, Memo, Account). Skipping AI. Data: {txn}")
                txn['Category'] = "MANUAL REVIEW (Missing Data)"
                txn['Memo'] = original_memo if original_memo is not None else ""
            elif adk_runner is None or adk_session_service is None: # Check both
                logger.warning("ADK Runner or Session Service not initialized. Skipping AI categorization.")
                txn['Category'] = "MANUAL REVIEW (ADK Not Initialized)"
                txn['Memo'] = original_memo
            elif original_memo: # Only call AI if there's an original memo and other fields
                logger.debug(f"Calling ADK for: Date='{date_str}', Amount='{amount_str}', Desc='{original_memo}', Acc='{account_name}'")
                ai_result = adk_agent_service.categorize_transaction_with_adk(
                    runner=adk_runner, # Pass runner
                    session_service=adk_session_service, # Pass session_service
                    date_str=date_str,
                    amount_str=amount_str,
                    raw_description=original_memo, # Pass original memo as raw_description to ADK
                    account_name=account_name
                )
                txn['Category'] = ai_result.get("category", "MANUAL REVIEW (ADK Fallback)")
                txn['Memo'] = ai_result.get("summary", original_memo) # Use agent's 'summary' for sheet 'Memo'
                
                # Log the new detailed fields from the agent
                agent_query = ai_result.get("query", "N/A")
                agent_email_subject = ai_result.get("email_subject", "N/A")
                logger.debug(f"ADK Result for '{original_memo}': Cat='{txn['Category']}', Summary (used as Memo)='{txn['Memo']}', GmailQuery='{agent_query}', EmailSubject='{agent_email_subject}'")
            else:
                # If original memo was missing/empty, set placeholder and keep empty memo
                txn['Category'] = "UNCATEGORIZED (No Memo)"
                txn['Memo'] = ""
                logger.warning(f"Original memo missing/empty for ADK, setting category to UNCATEGORIZED. Data: {txn}")

            final_transactions.append(txn)

        logger.info(f"Finished AI categorization for {len(final_transactions)} transactions.")
        # Optional: Log category distribution or count of UNCATEGORIZED

        # --- Upload Stage ---
        logger.info(f"Appending {len(final_transactions)} transactions to '{config.NEW_TRANSACTIONS_SHEET_NAME}' tab...")
        success = sheets_api.append_transactions(final_transactions)
        
        if success:
            logger.info("Successfully appended transactions to the Google Sheet.")
        else:
            logger.error("Failed to append transactions to the Google Sheet.")
            sys.exit(1)

        logger.info("Processing completed successfully")
        
    except Exception as e:
        logger.exception(f"An unexpected error occurred in the main execution: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 