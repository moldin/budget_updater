"""Google Sheets API integration module."""

import datetime
import glob
import logging
import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import constants from config
from . import config

logger = logging.getLogger(__name__)

# Constants moved to config.py
# SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
# SPREADSHEET_ID = config.SPREADSHEET_ID # Defined in config now
# TOKEN_PICKLE_PATH = config.TOKEN_PICKLE_PATH
# CREDENTIALS_DIR = config.CREDENTIALS_DIR
# DEFAULT_CLIENT_SECRET_PATTERN = config.DEFAULT_CLIENT_SECRET_PATTERN
# NEW_TRANSACTIONS_SHEET_NAME = config.NEW_TRANSACTIONS_SHEET_NAME
# BACKEND_DATA_SHEET_NAME = config.BACKEND_DATA_SHEET_NAME
# TRANSACTIONS_SHEET_NAME = config.TRANSACTIONS_SHEET_NAME
# ACCOUNTS_COLUMN = config.ACCOUNTS_COLUMN
# HEADER_ROW_BACKEND = config.HEADER_ROW_BACKEND
# HEADER_ROW_TRANSACTIONS = config.HEADER_ROW_TRANSACTIONS

class SheetAPI:
    """Handles interactions with the Google Sheets API."""

    def __init__(self):
        """Initializes the API client and authenticates."""
        logger.info("Initializing SheetAPI...")
        self.creds = self._authenticate()
        if not self.creds:
            logger.error("Authentication failed. SheetAPI cannot function.")
            # Depending on desired behavior, could raise an exception
            self.service = None
            self.accounts = []
            self.categories = [] # Assuming categories might be read later
        else:
            self.service = build('sheets', 'v4', credentials=self.creds)
            logger.info("Google Sheets service client built successfully.")
            self.accounts = self._read_backend_data(config.ACCOUNTS_COLUMN, config.HEADER_ROW_BACKEND)
            self.categories = [] # Placeholder: self._read_backend_data(config.CATEGORIES_COLUMN, config.HEADER_ROW_BACKEND)
            logger.info(f"Loaded {len(self.accounts)} accounts from {config.BACKEND_DATA_SHEET_NAME}.")
            # logger.info(f"Loaded {len(self.categories)} categories from {config.BACKEND_DATA_SHEET_NAME}.")

    def _get_client_secret_path(self) -> Path | None:
        """Finds the client secret JSON file in the credentials directory."""
        if not config.CREDENTIALS_DIR.is_dir():
            logger.error(f"Credentials directory not found: {config.CREDENTIALS_DIR}")
            return None

        found_files = list(config.CREDENTIALS_DIR.glob(config.DEFAULT_CLIENT_SECRET_PATTERN))

        if not found_files:
            logger.error(f"No client secret file matching '{config.DEFAULT_CLIENT_SECRET_PATTERN}' found in {config.CREDENTIALS_DIR}")
            return None
        elif len(found_files) > 1:
            logger.warning(f"Multiple client secret files found: {found_files}. Using the first one: {found_files[0]}")

        return found_files[0]

    def _authenticate(self) -> Credentials | None:
        """Handles OAuth 2.0 authentication flow."""
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if config.TOKEN_PICKLE_PATH.exists():
            logger.debug(f"Loading credentials from token file: {config.TOKEN_PICKLE_PATH}")
            try:
                with open(config.TOKEN_PICKLE_PATH, 'rb') as token:
                    creds = pickle.load(token)
            except (EOFError, pickle.UnpicklingError, FileNotFoundError) as e:
                 logger.error(f"Error loading token file ({config.TOKEN_PICKLE_PATH}), will re-authenticate: {e}")
                 creds = None # Ensure creds is None if loading fails
            except Exception as e:
                 logger.exception(f"Unexpected error loading token file ({config.TOKEN_PICKLE_PATH}): {e}")
                 creds = None

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Credentials expired, refreshing token...")
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}. Need to re-authenticate.")
                    # Attempt re-authentication if refresh fails
                    creds = None
            else:
                logger.info("No valid credentials found, starting OAuth flow...")
                client_secret_path = self._get_client_secret_path()
                if not client_secret_path:
                     return None # Cannot proceed without client secret

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secret_path, config.SCOPES)
                    # Specify host and port for the local server
                    # This prevents issues if port 8080 is already in use
                    creds = flow.run_local_server(port=0) 
                except FileNotFoundError:
                    logger.error(f"Client secrets file not found at: {client_secret_path}")
                    return None
                except Exception as e:
                    logger.exception(f"Error during OAuth flow: {e}")
                    return None

            # Save the credentials for the next run
            if creds:
                 logger.info("Authentication successful, saving credentials...")
                 try:
                     # Ensure credentials directory exists
                     config.CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
                     with open(config.TOKEN_PICKLE_PATH, 'wb') as token:
                         pickle.dump(creds, token)
                     logger.debug(f"Credentials saved to {config.TOKEN_PICKLE_PATH}")
                 except Exception as e:
                     logger.exception(f"Error saving token file to {config.TOKEN_PICKLE_PATH}: {e}")
                     # Continue even if saving fails, but log the error

        return creds


    def _read_backend_data(self, column: str, header_row: int) -> list[str]:
        """Reads a single column from the BackendData sheet."""
        if not self.service:
            logger.error("Cannot read backend data: Google Sheets service not available.")
            return []
        try:
            # Construct the range string dynamically
            # e.g., 'BackendData!I2:I' reads column I starting from row 2
            range_name = f'{config.BACKEND_DATA_SHEET_NAME}!{column}{header_row + 1}:{column}'
            logger.debug(f"Reading backend data from range: {range_name}")
            sheet = self.service.spreadsheets()
            result = sheet.values().get(spreadsheetId=config.SPREADSHEET_ID,
                                        range=range_name).execute()
            values = result.get('values', [])

            if not values:
                logger.warning(f"No data found in range {range_name}.")
                return []
            else:
                 # Flatten the list of lists and filter out empty strings
                items = [item[0] for item in values if item and item[0].strip()]
                logger.debug(f"Read {len(items)} items from {range_name}.")
                return items

        except HttpError as err:
            logger.error(f"HTTP error reading backend data: {err}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error reading backend data: {e}")
            return []

    def get_valid_account_names(self) -> list[str]:
        """Returns the cached list of valid account names."""
        return self.accounts
        
    def append_transactions(self, transactions: list[dict]) -> bool:
        """Appends rows of transaction data to the 'New Transactions' sheet."""
        if not self.service:
            logger.error("Cannot append transactions: Google Sheets service not available.")
            return False
        if not transactions:
            logger.warning("No transactions provided to append.")
            return True # Nothing to do, considered success

        try:
            # Convert list of dicts to list of lists in the correct order
            data_to_append = []
            for txn in transactions:
                # Ensure row order matches TARGET_COLUMNS definition in config
                row = [txn.get(col, '') for col in config.TARGET_COLUMNS]
                data_to_append.append(row)

            body = {
                'values': data_to_append
            }
            # Specify the sheet name from config
            range_ = f'{config.NEW_TRANSACTIONS_SHEET_NAME}!A:A' # Append after last row with data in col A
            
            logger.info(f"Appending {len(data_to_append)} rows to {config.NEW_TRANSACTIONS_SHEET_NAME}...")

            result = self.service.spreadsheets().values().append(
                spreadsheetId=config.SPREADSHEET_ID,
                range=range_,
                valueInputOption='USER_ENTERED', # Interpret values as if user typed them
                insertDataOption='INSERT_ROWS', # Insert new rows for the data
                body=body).execute()

            updates = result.get('updates', {})
            rows_appended = updates.get('updatedRows', 0)
            logger.info(f"{rows_appended} rows appended successfully.")
            return rows_appended == len(data_to_append)

        except HttpError as error:
            logger.error(f"An HTTP error occurred: {error}")
            logger.error(f"Details: {error.content}")
            return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred during append: {e}")
            return False


    def append_dummy_transaction(self):
        """Appends a single dummy transaction for testing purposes."""
        dummy_txn = {
            'Date': '2024-01-01',
            'Outflow': '12,34',
            'Inflow': '',
            'Category': 'Test Category',
            'Account': 'Test Account',
            'Memo': 'Dummy transaction for testing SheetAPI connection',
            'Status': '✅'
        }
        # Ensure the dummy transaction dict has all keys defined in TARGET_COLUMNS
        full_dummy_txn = {col: dummy_txn.get(col, '') for col in config.TARGET_COLUMNS}
        success = self.append_transactions([full_dummy_txn])
        if success:
            logger.info("Dummy transaction appended successfully.")
        else:
            logger.error("Failed to append dummy transaction.")


    def get_all_sheet_data(self, sheet_name: str) -> list | None:
        """Reads all data from a specified sheet."""
        if not self.service:
            logger.error(f"Cannot read sheet '{sheet_name}': Google Sheets service not available.")
            return None
        try:
            range_name = f'{sheet_name}' # Read the whole sheet
            logger.debug(f"Reading all data from sheet: {sheet_name}")
            sheet = self.service.spreadsheets()
            result = sheet.values().get(spreadsheetId=config.SPREADSHEET_ID,
                                        range=range_name).execute()
            values = result.get('values', [])
            logger.debug(f"Read {len(values)} rows from {sheet_name}.")
            return values
        except HttpError as err:
            logger.error(f"HTTP error reading sheet {sheet_name}: {err}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error reading sheet {sheet_name}: {e}")
            return None

    def analyze_sheet_structure(self, output_file="sheet_analysis.md"):
        """Reads structure of key sheets and writes analysis to a Markdown file."""
        logger.info(f"Analyzing sheet structure and writing to {output_file}...")
        analysis_content = "# Google Sheet Structure Analysis\n\n"
        
        sheets_to_analyze = [
            config.TRANSACTIONS_SHEET_NAME,
            config.NEW_TRANSACTIONS_SHEET_NAME,
            config.BACKEND_DATA_SHEET_NAME
        ]

        all_sheets_metadata = self.get_sheet_metadata()
        if not all_sheets_metadata:
             analysis_content += "\n**ERROR:** Could not retrieve sheet metadata.\n"
        else:
            existing_sheet_names = [s['properties']['title'] for s in all_sheets_metadata]
            analysis_content += f"**Spreadsheet ID:** `{config.SPREADSHEET_ID}`\n"
            analysis_content += f"**Detected Sheets:** `{(', '.join(existing_sheet_names))}`\n"

        for sheet_name in sheets_to_analyze:
            analysis_content += f"\n## Sheet: `{sheet_name}`\n\n"
            data = self.get_all_sheet_data(sheet_name)
            if data is None:
                analysis_content += "*Could not read data from this sheet.*\n"
                continue
            if not data:
                 analysis_content += "*Sheet is empty.*\n"
                 continue

            header_row_index = config.HEADER_ROW_TRANSACTIONS -1 if sheet_name != config.BACKEND_DATA_SHEET_NAME else config.HEADER_ROW_BACKEND -1
            if len(data) <= header_row_index:
                 analysis_content += f"*Sheet has fewer rows ({len(data)}) than expected header row ({header_row_index+1}). Cannot determine headers.*\n"
                 headers = []
            else:
                headers = data[header_row_index]
                analysis_content += f"**Header Row ({header_row_index+1}):** `{headers}`\n"
                analysis_content += f"**Number of Columns (based on header):** {len(headers)}\n"

            analysis_content += f"**Total Rows (including header):** {len(data)}\n"
            analysis_content += f"**First 5 Rows of Data (below header):**\n```\n"
            # Start from row after header, take up to 5 rows
            data_start_index = header_row_index + 1
            for row in data[data_start_index : min(data_start_index + 5, len(data))]:
                analysis_content += str(row) + "\n"
            analysis_content += "```\n"
            
            # Specific checks
            if sheet_name == config.BACKEND_DATA_SHEET_NAME:
                 col_index = self._col_letter_to_index(config.ACCOUNTS_COLUMN)
                 if col_index < len(headers):
                      analysis_content += f"- **Accounts Column ('{config.ACCOUNTS_COLUMN}'):** `{headers[col_index]}`\n"
                 else:
                      analysis_content += f"- **Accounts Column ('{config.ACCOUNTS_COLUMN}'):** *Index out of bounds for headers.*\n"
                 # Add check for Categories column if needed later

            elif sheet_name == config.NEW_TRANSACTIONS_SHEET_NAME or sheet_name == config.TRANSACTIONS_SHEET_NAME:
                 if set(config.TARGET_COLUMNS).issubset(set(headers)):
                      analysis_content += f"- **Required Columns ({config.TARGET_COLUMNS}):** Found.\n"
                 else:
                     missing_req = list(set(config.TARGET_COLUMNS) - set(headers))
                     analysis_content += f"- **Required Columns ({config.TARGET_COLUMNS}):** MISSING `({', '.join(missing_req)})`\n"

        # Add loaded Accounts and Categories
        analysis_content += f"\n## Loaded Backend Data\n\n"
        analysis_content += f"**Accounts (from {config.BACKEND_DATA_SHEET_NAME} Col '{config.ACCOUNTS_COLUMN}'):**\n```\n{self.accounts}\n```\n"
        # analysis_content += f"**Categories (from {config.BACKEND_DATA_SHEET_NAME} Col '{config.CATEGORIES_COLUMN}'):**\n```\n{self.categories}\n```\n"

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(analysis_content)
            logger.info(f"Analysis written to {output_file}")
        except Exception as e:
            logger.error(f"Failed to write analysis file {output_file}: {e}")

    def get_sheet_metadata(self):
        """Retrieves metadata for all sheets in the spreadsheet."""
        if not self.service:
            logger.error("Cannot get sheet metadata: Service not available.")
            return None
        try:
            sheet_metadata = self.service.spreadsheets().get(spreadsheetId=config.SPREADSHEET_ID).execute()
            sheets = sheet_metadata.get('sheets', '')
            return sheets
        except HttpError as err:
            logger.error(f"HTTP error getting sheet metadata: {err}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error getting sheet metadata: {e}")
            return None
            
    def _col_letter_to_index(self, letter: str) -> int:
        """Converts a column letter (A, B, ..., Z, AA, AB, ...) to a 0-based index."""
        index = 0
        power = 1
        for char in reversed(letter.upper()):
            index += (ord(char) - ord('A') + 1) * power
            power *= 26
        return index - 1 # Convert to 0-based index


# Example usage (for manual testing)
# if __name__ == '__main__':
#     logging.basicConfig(level=logging.INFO)
#     sheet_api = SheetAPI()
#     if sheet_api.service:
#         # sheet_api.append_dummy_transaction()
#         sheet_api.analyze_sheet_structure()
#         print("Valid Accounts:", sheet_api.get_valid_account_names()) # Example of getting cached accounts 