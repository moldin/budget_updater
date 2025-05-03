import os
from pathlib import Path
from typing import Dict

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
ACCOUNT_NAME_MAP: Dict[str, str] = {
    "seb": "💰 SEB",
    "revolut": "💳 Revolut",
    "firstcard": "💳 First Card",
    "strawberry": "💳 Strawberry",
    # Add other aliases as needed
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

# ---vvv--- ADD CATEGORIES LIST ---vvv---
CATEGORIES_WITH_DESCRIPTIONS = """
- **↕️ Account Transfer:** This means that an amount has been transferred between two accounts. E.g. a payment of First Card credit invoice will be categorized as Account Transfer and will show up as two transactions one with outflow from SEB account and one with INFLOW to First Card.
- **🔢 Balance Adjustment:** This is only used to manually correct balances when something small has gone wrong (AI should rarely select this).
- **➡️ Starting Balance:** This should never be used by the AI; it's only used the first time an account is used in the system.
- **Available to budget:** This is used when cash is added to an account through Salary or other kinds of income.
- **Äta ute tillsammans:** This is used when I "fika" or eat together with others.
- **Mat och hushåll:** This is when I purchase food e.g. from ICA, Coop or other grocery stores. It can also be used when paying Jacob (0733-497676) or Emma (0725-886444) for food via Swish etc.
- **Bensin:** Gas for car, e.g. OKQ8, CircleK etc.
- **Bil/Parkering:** Payment for parking (easypark, mobill, apcoa, etc.).
- **Barnen:** Everything else related to Emma or Jacob (not specific items covered elsewhere).
- **Emma div:** For Emma specifically.
- **Jacob div:** For Jacob specifically.
- **Resor:** Taxi, SL, train tickets, public transport fares.
- **Nöjen:** Boardgames, computer games, streaming games, theater tickets, concerts, cinema etc.
- **Allt annat:** Misc category for things that don't fit into the others.
- **Äta ute Mats:** When I eat for myself, often at work (Convini, Knut, work canteens, solo lunches/dinners).
- **Utbildning:** Everything related to learning (Udemy, Pluralsight, Coursera, conferences, workshops).
- **Utlägg arbete:** When I have paid for something related to work that will be expensed later (company reimburses me).
- **Utlägg andra:** When I have paid for someone else who now owes me (e.g., paying for a group dinner and getting Swished back).
- **Appar/Mjukvara:** Most often through Apple AppStore/Google Play, but could also be software subscriptions (excluding those listed separately like Adobe, Microsoft 365 etc).
- **Musik:** When I purchase songs (iTunes), music streaming services (excluding Spotify), or gear for my music hobby (instruments, accessories).
- **Böcker:** Books (physical, Kindle), newspaper/magazine subscriptions (digital or print).
- **Teknik:** Electronic gear, computer stuff, gadgets, accessories, components.
- **Kläder:** Clothing, shoes, accessories.
- **Vattenfall:** Specifically for Vattenfall bills (heating/network).
- **Elektricitet:** Bills from electricity providers like Telge Energi, Fortum (the actual power consumption).
- **Internet:** Bahnhof or other internet service provider bills.
- **Huslån:** Large transfers to mortgage accounts like Lånekonto Avanza (5699 03 201 25).
- **Städning:** Cleaning services like Hemfrid.
- **E-mail:** Google GSuite/Workspace subscription fees.
- **Bankavgifter:** Bank service fees like Enkla vardagen på SEB, yearly fee for FirstCard, Revolut fees, etc.
- **Hälsa/Familj:** Pharmacy purchases (Apotek), doctor visits (Rainer), therapy, other health-related costs.
- **SL:** SL monthly passes or top-ups (should likely be under 'Resor' unless tracking separately). *Note: Consider merging with Resor?*
- **Verisure:** Specifically for Verisure alarm system bills.
- **Klippning:** Hair cuts (e.g., Barber & Books).
- **Mobil:** Cell phone bills (Tre, Hi3G, Hallon, etc.).
- **Fack/A-kassa:** Union fees (Ledarna) or unemployment insurance (Akademikernas a-kassa).
- **Glasögon:** Monthly payment for glasses subscription (Synsam).
- **Livförsäkring:** Life insurance premiums (Skandia).
- **Hemförsäkring:** Home insurance premiums (Trygg Hansa).
- **Sjuk- olycksfallsförsäkring:** Accident and illness insurance premiums (Trygg Hansa).
- **HBO:** HBO Max subscription.
- **Spotify:** Spotify subscription.
- **Netflix:** Netflix subscription.
- **Amazon Prime:** Amazon Prime subscription.
- **Disney+:** Disney+ subscription.
- **Viaplay:** Viaplay subscription.
- **C More:** TV4 Play / C More monthly subscription.
- **Apple+:** Apple TV+ service subscription.
- **Youtube gmail:** YouTube Premium subscription.
- **iCloud+:** Specifically Apple iCloud storage bills.
- **Storytel:** Storytel subscription.
- **Audible:** Monthly subscription or ad-hoc credits etc for Audible.
- **Adobe Creative Cloud:** Monthly subscription for Adobe CC.
- **Dropbox:** Yearly subscription for Dropbox.
- **Microsoft 365 Family:** Yearly subscription for Microsoft 365.
- **VPN:** VPN service subscription (ExpressVPN, NordVPN, etc).
- **Samfällighet:** Yearly fee for the local community association (Brotorp).
- **Bil underhåll:** Car maintenance costs (service, repairs, tires).
- **Hus underhåll:** Home improvement/repair costs (Hornbach, Bauhaus, materials, contractors).
- **Semester:** Everything spent during vacation (use more specific categories below if possible).
- **Sparande:** Savings transfers (excluding specific goals like Barnspar or Huslån).
- **Barnspar:** Specific monthly transfer (e.g. 500 kr) to Avanza for children's savings.
- **Patreon:** Misc Patreon payments.
- **Presenter:** Gifts purchased for others.
- **Semester äta ute:** Restaurant bills during vacation.
- **Semester nöjen:** Entertainment expenses during vacation.
- **Semester övrigt:** Misc expenses during vacation that don't fit other semester categories.
- **AI - tjänster:** Subscriptions or payments for AI services (Notion AI, ChatGPT Plus, Cursor, Github Copilot, Google Cloud AI, Midjourney, etc.).
"""
# ---^^^--- END ADD CATEGORIES LIST ---^^^--- 