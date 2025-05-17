#!/usr/bin/env python3
"""Main module for Budget Updater application."""

import argparse
import logging
import sys
import os # Added for environment variable check
from pathlib import Path # Import Path
from dotenv import load_dotenv # Import dotenv

# Use relative imports within the package
from .transformation import transform_transactions
from . import adk_agent_service
from tqdm import tqdm
from . import config
from .sheets_api import SheetAPI
from .parsers import PARSER_REGISTRY

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
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

    args = parser.parse_args()

    # Handle verbose logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Verbose logging enabled.")
    
    return args


def init_adk():
    """Initialize the ADK runner and session service."""
    try:
        runner, session_service = adk_agent_service.create_adk_runner_and_service()
        logger.info("ADK Runner and Session Service initialized successfully.")
        return runner, session_service
    except Exception as e:
        logger.error(
            f"Failed to initialize ADK Runner and Session Service: {e}",
            exc_info=True,
        )
        logger.error(
            "Categorization via AI will not be possible. Please check GCP/ADK setup and .env variables."
        )
        return None, None


def init_sheets_api() -> SheetAPI:
    """Initialize and return :class:`SheetAPI`. Exit on failure."""
    try:
        api = SheetAPI()
    except Exception as e:
        logger.error(f"Failed to initialize SheetAPI: {e}", exc_info=True)
        sys.exit(1)

    if api.service is None:
        logger.error("SheetAPI service could not be initialized. Cannot proceed.")
        sys.exit(1)

    return api


def handle_special_modes(args: argparse.Namespace, sheets_api: SheetAPI) -> bool:
    """Process --test or --analyze modes.

    Returns ``True`` if a special mode was executed and the program should exit.
    """
    if args.test:
        logger.info("Running in test mode")
        sheets_api.append_dummy_transaction()
        logger.info(
            f"Dummy transaction added to '{config.NEW_TRANSACTIONS_SHEET_NAME}' tab"
        )
        return True

    if args.analyze:
        logger.info("Analyzing spreadsheet structure")
        sheets_api.analyze_sheet_structure()
        logger.info("Analysis complete. See sheet_analysis.md for details")
        return True

    return False


def validate_inputs(args: argparse.Namespace, sheets_api: SheetAPI) -> tuple[str, Path]:
    """Validate CLI arguments and environment prerequisites."""
    if not args.file or not args.account:
        logger.error("Both --file and --account arguments are required.")
        sys.exit(1)

    account_cli_arg = args.account.lower()
    account_name_mapped = config.ACCOUNT_NAME_MAP.get(account_cli_arg)
    if not account_name_mapped:
        logger.error(
            f"Unknown account alias: '{args.account}'. Valid aliases are: {list(config.ACCOUNT_NAME_MAP.keys())}"
        )
        sys.exit(1)

    valid_accounts_from_sheet = sheets_api.accounts
    if not valid_accounts_from_sheet:
        logger.error("Could not retrieve valid account names from the spreadsheet.")
        sys.exit(1)

    if account_name_mapped not in valid_accounts_from_sheet:
        logger.error(
            f"Mapped account name '{account_name_mapped}' (from alias '{args.account}') not found in BackendData sheet (Column I)."
        )
        logger.debug(f"Valid accounts found in sheet: {valid_accounts_from_sheet}")
        sys.exit(1)

    logger.info(
        f"Processing for account: {account_name_mapped} (mapped from alias '{args.account}')"
    )

    if not config.GOOGLE_CLOUD_PROJECT:
        logger.warning(
            "GOOGLE_CLOUD_PROJECT environment variable not set. Categorization via AI will likely fail or use placeholder."
        )
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.warning(
            "GOOGLE_APPLICATION_CREDENTIALS environment variable not set. Categorization via AI will likely fail."
        )

    file_path = Path(args.file)
    if not file_path.is_file():
        logger.error(f"File not found or is not a file: {file_path}")
        sys.exit(1)

    return account_name_mapped, file_path


def parse_file(file_path: Path, alias: str):
    """Run the parser associated with ``alias`` on ``file_path``."""
    logger.info(f"Parsing file: {file_path}")
    parser_function = PARSER_REGISTRY.get(alias)
    if not parser_function:
        logger.error(
            f"No parser function found in registry for alias '{alias}'. Check PARSER_REGISTRY in parsers.py."
        )
        sys.exit(1)

    parsed_data = parser_function(file_path)
    if parsed_data is None:
        logger.error(f"Parsing failed for file: {file_path}")
        sys.exit(1)
    if parsed_data.empty:
        logger.warning(f"No transactions found or parsed from file: {file_path}. Exiting.")
        sys.exit(0)

    logger.info(f"Successfully parsed {len(parsed_data)} transactions.")
    return parsed_data


def sort_transactions(transactions):
    """Sort a list of :class:`Transaction` instances by date."""
    logger.info(f"Sorting {len(transactions)} transactions by date...")
    try:
        transactions.sort(key=lambda txn: txn.date)
        logger.info("Transactions sorted chronologically.")
    except AttributeError:
        logger.error(
            "Transformation failed to produce date attribute correctly. Cannot sort."
        )
        sys.exit(1)
    except Exception as sort_err:
        logger.error(f"Error during sorting: {sort_err}", exc_info=True)
        sys.exit(1)
    return transactions


def categorize_transactions(transactions, adk_runner, session_service):
    """Categorize transactions using the ADK agent."""
    logger.info("Starting AI categorization...")
    final_transactions = []
    for txn in tqdm(transactions, desc="Categorizing Transactions", unit="txn"):
        original_memo = txn.memo
        date_str = txn.date
        outflow_str = txn.outflow or ""
        inflow_str = txn.inflow or ""
        amount_str = outflow_str if outflow_str else inflow_str
        account_name = txn.account

        if not all([date_str, amount_str is not None, original_memo is not None, account_name]):
            logger.warning(
                "Transaction missing required fields for ADK categorization (Date, Amount, Memo, Account). Skipping AI. Data: %s",
                txn,
            )
            txn.category = "MANUAL REVIEW (Missing Data)"
            txn.memo = original_memo if original_memo is not None else ""
        elif adk_runner is None or session_service is None:
            logger.warning(
                "ADK Runner or Session Service not initialized. Skipping AI categorization."
            )
            txn.category = "MANUAL REVIEW (ADK Not Initialized)"
            txn.memo = original_memo
        elif original_memo:
            logger.debug(
                f"Calling ADK for: Date='{date_str}', Amount='{amount_str}', Desc='{original_memo}', Acc='{account_name}'"
            )
            ai_result = adk_agent_service.categorize_transaction_with_adk(
                runner=adk_runner,
                session_service=session_service,
                date_str=date_str,
                amount_str=amount_str,
                raw_description=original_memo,
                account_name=account_name,
            )
            txn.category = ai_result.get("category", "MANUAL REVIEW (ADK Fallback)")
            txn.memo = ai_result.get("summary", original_memo)

            agent_query = ai_result.get("query", "N/A")
            agent_email_subject = ai_result.get("email_subject", "N/A")
            logger.debug(
                "ADK Result for '%s': Cat='%s', Summary (used as Memo)='%s', GmailQuery='%s', EmailSubject='%s'",
                original_memo,
                txn.category,
                txn.memo,
                agent_query,
                agent_email_subject,
            )
        else:
            txn.category = "UNCATEGORIZED (No Memo)"
            txn.memo = ""
            logger.warning(
                "Original memo missing/empty for ADK, setting category to UNCATEGORIZED. Data: %s",
                txn,
            )

        final_transactions.append(txn)

    logger.info(f"Finished AI categorization for {len(final_transactions)} transactions.")
    return final_transactions


def upload_transactions(transactions, sheets_api: SheetAPI):
    """Append transactions to the sheet and log the outcome."""
    logger.info(
        f"Appending {len(transactions)} transactions to '{config.NEW_TRANSACTIONS_SHEET_NAME}' tab..."
    )
    success = sheets_api.append_transactions(transactions)
    if success:
        logger.info("Successfully appended transactions to the Google Sheet.")
    else:
        logger.error("Failed to append transactions to the Google Sheet.")
        sys.exit(1)
    return success


def main():
    """Execute the main application logic."""
    load_dotenv()
    logger.info("Loaded environment variables from .env file (if present).")

    args = parse_args()

    logger.info("Starting Budget Updater")

    adk_runner, adk_session_service = init_adk()
    sheets_api = init_sheets_api()

    if handle_special_modes(args, sheets_api):
        return

    account_name_validated, file_path = validate_inputs(args, sheets_api)

    parsed_data = parse_file(file_path, args.account.lower())

    logger.info("Transforming parsed data...")
    transformed_data = transform_transactions(parsed_data, account_name_validated)

    if not transformed_data:
        logger.warning(
            "No transactions available after transformation (or transformation failed). Exiting."
        )
        sys.exit(0)

    logger.info(
        f"Successfully transformed {len(transformed_data)} transactions into list format."
    )

    sorted_transactions = sort_transactions(transformed_data)
    final_transactions = categorize_transactions(sorted_transactions, adk_runner, adk_session_service)
    upload_transactions(final_transactions, sheets_api)

    logger.info("Processing completed successfully")

    return 0


if __name__ == "__main__":
    main()
