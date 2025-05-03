"""Google Sheets API integration module."""

import datetime
import logging
import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Config constants
SPREADSHEET_ID = "1P-t5irZ2E_T_uWy0rAHjjWmwlUNevT0DqzLVtxq3AYk"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Sheet ranges
NEW_TRANSACTIONS_RANGE = "New Transactions!A:G"
TRANSACTIONS_RANGE = "Transactions!A:G"
BACKEND_DATA_RANGE = "BackendData!A:Z"  # We'll read specific columns from here


class SheetAPI:
    """Google Sheets API wrapper for budget updater."""

    def __init__(self):
        """Initialize Google Sheets API client."""
        self.creds = self._get_credentials()
        self.service = build("sheets", "v4", credentials=self.creds)
        self.sheet = self.service.spreadsheets()
        self.accounts = self._load_accounts()
        self.categories = self._load_categories()
        
        logger.info("Google Sheets API initialized successfully")
        logger.debug(f"Loaded {len(self.accounts)} accounts and {len(self.categories)} categories")

    def _get_credentials(self):
        """Get or refresh Google API credentials."""
        creds = None
        token_path = Path("token.json")
        creds_path = Path("credentials.json")

        # Check if token.json exists
        if token_path.exists():
            try:
                with open(token_path, "rb") as token:
                    creds = Credentials.from_authorized_user_info(pickle.load(token))
            except Exception as e:
                logger.warning(f"Error loading credentials from token.json: {e}")

        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Failed to refresh token: {e}")
                    creds = None

            # If still no valid credentials, run the OAuth flow
            if not creds:
                if not creds_path.exists():
                    raise FileNotFoundError(
                        "credentials.json file not found. Please download OAuth 2.0 credentials "
                        "from Google Cloud Console and save as credentials.json in the project root."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(token_path, "wb") as token:
                pickle.dump(creds.to_json(), token)

        return creds

    def _load_accounts(self):
        """Load account names from BackendData tab."""
        try:
            result = self.sheet.values().get(
                spreadsheetId=SPREADSHEET_ID, 
                range="BackendData!I:I"
            ).execute()
            
            values = result.get("values", [])
            if not values:
                logger.warning("No accounts found in BackendData tab")
                return []
                
            # Filter out empty values and header row (if any)
            accounts = [row[0] for row in values if row and row[0] and row[0] != "ACCOUNT"]
            logger.debug(f"Loaded accounts: {accounts}")
            return accounts
            
        except HttpError as error:
            logger.error(f"Error loading accounts: {error}")
            return []

    def _load_categories(self):
        """Load category names from BackendData tab."""
        try:
            result = self.sheet.values().get(
                spreadsheetId=SPREADSHEET_ID, 
                range="BackendData!G:G"
            ).execute()
            
            values = result.get("values", [])
            if not values:
                logger.warning("No categories found in BackendData tab")
                return []
                
            # Filter out empty values and header row (if any)
            categories = [row[0] for row in values if row and row[0] and row[0] != "CATEGORY"]
            logger.debug(f"Loaded categories: {categories}")
            return categories
            
        except HttpError as error:
            logger.error(f"Error loading categories: {error}")
            return []

    def get_transaction_headers(self):
        """Get the header row from Transactions tab to understand column mapping."""
        try:
            result = self.sheet.values().get(
                spreadsheetId=SPREADSHEET_ID, 
                range="Transactions!1:1"
            ).execute()
            
            values = result.get("values", [])
            if not values:
                logger.warning("No headers found in Transactions tab")
                return []
                
            return values[0]
            
        except HttpError as error:
            logger.error(f"Error getting transaction headers: {error}")
            return []

    def append_dummy_transaction(self):
        """Append a dummy transaction row to test connectivity."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Dummy transaction data
        values = [
            [
                today,               # DATE
                "100.00",           # OUTFLOW
                "",                 # INFLOW
                "Mat och hushåll",  # CATEGORY
                "💰 SEB",           # ACCOUNT
                "TEST TRANSACTION - PLEASE DELETE",  # MEMO
                "✅"                # STATUS
            ]
        ]
        
        body = {
            "values": values
        }
        
        try:
            result = self.sheet.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=NEW_TRANSACTIONS_RANGE,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()
            
            logger.debug(f"Append result: {result}")
            return True
            
        except HttpError as error:
            logger.error(f"Error appending dummy transaction: {error}")
            return False

    def append_transactions(self, transactions):
        """Append multiple transaction rows to New Transactions tab.
        
        Args:
            transactions: List of transaction dictionaries with keys:
                DATE, OUTFLOW, INFLOW, CATEGORY, ACCOUNT, MEMO, STATUS
        """
        if not transactions:
            logger.warning("No transactions to append")
            return False
            
        # Convert transactions to row values
        values = []
        for t in transactions:
            values.append([
                t.get("DATE", ""),
                t.get("OUTFLOW", ""),
                t.get("INFLOW", ""),
                t.get("CATEGORY", ""),
                t.get("ACCOUNT", ""),
                t.get("MEMO", ""),
                t.get("STATUS", "✅")
            ])
            
        body = {
            "values": values
        }
        
        try:
            result = self.sheet.values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=NEW_TRANSACTIONS_RANGE,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()
            
            logger.debug(f"Append result: {result}")
            return True
            
        except HttpError as error:
            logger.error(f"Error appending transactions: {error}")
            return False

    def analyze_sheet_structure(self):
        """Analyze sheet structure and write details to a reference file."""
        analysis = ["# Budget Sheet Analysis\n"]
        
        try:
            # Get Transaction tab headers
            transaction_headers = self.get_transaction_headers()
            analysis.append("## Transactions Tab Headers\n")
            analysis.append(f"Headers are in row 1: {', '.join(transaction_headers)}\n\n")
            
            # Get account names
            analysis.append("## Valid Account Names\n")
            for account in self.accounts:
                analysis.append(f"- {account}\n")
            analysis.append("\n")
            
            # Get category names
            analysis.append("## Valid Categories\n")
            for category in self.categories:
                analysis.append(f"- {category}\n")
            
            # Write analysis to file
            with open("sheet_analysis.md", "w") as f:
                f.write("\n".join(analysis))
                
            logger.info("Sheet analysis written to sheet_analysis.md")
            return True
            
        except Exception as e:
            logger.error(f"Error analyzing sheet structure: {e}")
            return False 