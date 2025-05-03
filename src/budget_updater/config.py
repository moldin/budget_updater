import os
from pathlib import Path

# --- Google API Configuration ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Credentials paths (relative to project root assumed)
CREDENTIALS_DIR = Path("credentials")
TOKEN_PICKLE_PATH = CREDENTIALS_DIR / "token.pickle"
DEFAULT_CLIENT_SECRET_PATTERN = "client_secret_*.json" # Pattern to find client secret

# --- Google Sheet Configuration ---
# Allow overriding via environment variable, but use PRD default
DEFAULT_SPREADSHEET_ID = "1P-t5irZ2E_T_uWy0rAHjjWmwlUNevT0DqzLVtxq3AYk"
SPREADSHEET_ID = os.environ.get("GOOGLE_SHEET_ID", DEFAULT_SPREADSHEET_ID)
if not SPREADSHEET_ID: # Should only happen if env var is set to empty string
     raise ValueError("GOOGLE_SHEET_ID environment variable is set but empty.")

# Tab Names
NEW_TRANSACTIONS_SHEET_NAME = "New Transactions"
BACKEND_DATA_SHEET_NAME = "BackendData"
TRANSACTIONS_SHEET_NAME = "Transactions"

# Column Definitions (within BackendData)
ACCOUNTS_COLUMN = "I" # Column containing valid account names in BackendData
CATEGORIES_COLUMN = "G" # Column containing valid categories in BackendData (if needed later)

# Header Row Information (assuming 1-based indexing for user readability)
HEADER_ROW_BACKEND = 1 # Row number where headers are in BackendData
HEADER_ROW_TRANSACTIONS = 1 # Row number where headers are in Transactions & New Transactions

# --- Account Name Mapping ---
# Maps CLI short names to full names in the sheet (BackendData Col I)
ACCOUNT_NAME_MAP = {
    "seb": "💰 SEB",
    "revolut": "💳 Revolut",
    "firstcard": "💳 First Card",
    "strawberry": "💳 Strawberry",
    # Add other mappings here if needed for different input files/accounts
}

# --- Vertex AI Configuration ---
# Use PRD values as defaults, allow overrides via environment variables
DEFAULT_GOOGLE_CLOUD_PROJECT = "aspiro-budget-analysis"
DEFAULT_GOOGLE_CLOUD_LOCATION = "europe-west1"
DEFAULT_GEMINI_MODEL_ID = "gemini-2.0-flash-001" # Updated default based on PRD correction

GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", DEFAULT_GOOGLE_CLOUD_PROJECT)
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", DEFAULT_GOOGLE_CLOUD_LOCATION)
GEMINI_MODEL_ID = os.environ.get("GEMINI_MODEL_ID", DEFAULT_GEMINI_MODEL_ID)

# GOOGLE_APPLICATION_CREDENTIALS *must* be set as an env var pointing to the key file
# We will check for its presence directly in the relevant modules (categorizer.py)

# Check if the essential GOOGLE_CLOUD_PROJECT is available
if not GOOGLE_CLOUD_PROJECT:
     # This should only happen if the default is removed and the env var is empty/not set
     raise ValueError("GOOGLE_CLOUD_PROJECT is not defined in config defaults or environment variables.")

# --- Transformation Configuration ---
PLACEHOLDER_CATEGORY = "PENDING_AI"
DEFAULT_STATUS = "✅"
TARGET_COLUMNS = ['Date', 'Outflow', 'Inflow', 'Category', 'Account', 'Memo', 'Status'] 