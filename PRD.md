# PRD: Bank Transaction Processor for Aspire Budget Sheet

**Version:** 1.1
**Date:** 2025-05-03

## 1. Introduction

This document describes the requirements for a Python application designed to automate the process of importing bank transactions into the "MOL Aspire Budget" Google Sheet. The application will read transaction export files from various banks, parse them, categorize transactions using AI, format the data according to the budget sheet's structure, and upload the formatted transactions to a specific tab for review.

## 2. Goals

* Significantly reduce the manual effort required to log bank transactions.
* Ensure consistent formatting of transactions added to the budget sheet.
* Leverage AI for automatic transaction categorization, minimizing manual selection.
* Provide a staging area ('New Transactions' tab) for reviewing processed transactions before final integration.

## 3. User Stories / Features

* **As a user, I want to:**
    * Provide a bank transaction export file (from SEB, First Card, Revolut, or Strawberry Card) to the application.
    * Specify which bank account the export file belongs to.
    * Have the application read and parse the transactions from the file.
    * Have the application automatically categorize each transaction using Google Gemini AI based on the transaction description and my predefined category list with detailed descriptions.
    * Have transactions that cannot be categorized marked as "UNCATEGORIZED".
    * Have the application format the parsed transactions into the structure required by the 'New Transactions' tab of my Google Sheet (`DATE`, `OUTFLOW`, `INFLOW`, `CATEGORY`, `ACCOUNT`, `MEMO`, `STATUS`).
    * Have the application upload these formatted transactions to the 'New Transactions' tab in my Google Sheet.
    * See a confirmation or log of the transactions processed and uploaded.

## 4. Input Data Handling (Bank File Parsers)

The application must be able to parse transaction data from the following bank export formats (CSV derived from original XLS/XLSX):

**Supported Banks & File Structures:**

1.  **SEB (`seb.xlsx - Sheet1.csv`)**
    * **Date:** `Bokföringsdatum` (Format: YYYY-MM-DD)
    * **Description:** `Text`
    * **Amount:** `Belopp` (Negative values represent outflow, positive values represent inflow)
    * **Account Name (to be mapped):** e.g., "SEB Privat"

2.  **First Card (`firstcard.xlsx - Transactions.csv`)**
    * **Date:** `Datum` (Format: YYYY-MM-DD)
    * **Description:** `Reseinformation / Ink\u00f6psplats` (Note: Column name contains unicode slash)
    * **Amount:** `Belopp` (Note: These appear to be positive for purchases on a credit card. **Logic required:** Treat all positive amounts as `OUTFLOW`. Inflows (e.g., invoice payments) need separate handling - see Open Questions).
    * **Account Name (to be mapped):** e.g., "First Card"

3.  **Revolut (`revolut.xlsx - Sheet 1 - account-statement_202.csv`)**
    * **Date:** `Completed Date` (Format: YYYY-MM-DD HH:MM:SS - Extract Date part)
    * **Description:** `Description`
    * **Amount:** `Amount` (Negative values represent outflow, positive values represent inflow)
    * **Fee:** `Fee` (Note: Fees should be added to the `OUTFLOW` amount if present and non-zero).
    * **Account Name (to be mapped):** e.g., "Revolut"

4.  **Strawberry Card (`strawberry.xls - Sökta transaktioner Mitt Strawb.csv`)**
    * **Date:** `Bokfört` (Format: Excel Serial Date Number - **Requires conversion to YYYY-MM-DD**)
    * **Description:** `Specifikation`
    * **Amount:** `Belopp` (Note: These appear to be positive for purchases on a credit card. **Logic required:** Treat all positive amounts as `OUTFLOW`. Inflows (e.g., invoice payments) need separate handling - see Open Questions).
    * **Account Name (to be mapped):** e.g., "Strawberry Card"

**Requirements:**

* The application should identify the bank format (potentially based on user input or filename convention).
* Robust parsing logic to handle potential variations or header rows in export files.
* Correct extraction of Date, Description, and Amount fields based on the identified format.
* Handle character encoding issues (e.g., Swedish characters like 'å', 'ä', 'ö').
* Handle different date formats, including Excel serial numbers.

## 5. Data Transformation Logic

Each transaction parsed from the input file must be transformed into a row matching the target Google Sheet structure:

* **`DATE`**: Extracted date from the bank file, formatted as YYYY-MM-DD.
* **`OUTFLOW`**:
    * The absolute value of the transaction amount if it represents money leaving the account (e.g., negative amounts in SEB/Revolut, positive amounts in First Card/Strawberry).
    * Should be empty or 0 if it's an inflow.
* **`INFLOW`**:
    * The absolute value of the transaction amount if it represents money entering the account (e.g., positive amounts in SEB/Revolut).
    * Should be empty or 0 if it's an outflow.
* **`CATEGORY`**: Determined by the Categorization Engine (see Section 6). Set to "UNCATEGORIZED" if AI cannot categorize.
* **`ACCOUNT`**: The name of the account the transaction belongs to (exactly one of these: "💰 SEB", "💳 Revolut","Utlägg/Lån till andra","Sparkonto" which has account no "53653319781","Buffertkonto","Kontanter","💳 First Card","Lån av andra","💳 Strawberry"). This must exactly match an account name defined in the 'BackendData' sheet (Assumed Column F: 'Account'). The application needs a mechanism to associate the input file with the correct account name (e.g., user selection, filename pattern).
* **`MEMO`**: The cleaned-up transaction description extracted from the bank file.
* **`STATUS`**: Set to the emoji: ✅

## 6. Categorization Engine (Gemini AI)

* The application will use the Google Gemini AI model via Vertex AI to categorize transactions.
* **Input to AI:** The `MEMO` (transaction description) field extracted from the bank file.
* **Context/Instructions for AI:** The AI should be prompted to choose the single best category from the provided list based on the memo. The prompt must include the following list of categories and their detailed descriptions to guide the selection process. The AI should only output the chosen category name (e.g., "Mat och hushåll", "Teknik", "↕️ Account Transfer").
* **Available Categories and Descriptions (Provide to AI):**

    * **↕️ Account Transfer:** This means that an amount has been transferred between two accounts. E.g. a payment of First Card credit invoice will be categorized as Account Transfer and will show up as two transactions one with outflow from SEB account and one with INFLOW to First Card.
    * **🔢 Balance Adjustment:** This is only used to manually correct balances when something small has gone wrong (AI should rarely select this).
    * **➡️ Starting Balance:** This should never be used by the AI; it's only used the first time an account is used in the system.
    * **Available to budget:** This is used when cash is added to an account through Salary or other kinds of income.
    * **Äta ute tillsammans:** This is used when I "fika" or eat together with others.
    * **Mat och hushåll:** This is when I purchase food e.g. from ICA, Coop or other grocery stores. It can also be used when paying Jacob (0733-497676) or Emma (0725-886444) for food via Swish etc.
    * **Bensin:** Gas for car, e.g. OKQ8, CircleK etc.
    * **Bil/Parkering:** Payment for parking (easypark, mobill, apcoa, etc.).
    * **Barnen:** Everything else related to Emma or Jacob (not specific items covered elsewhere).
    * **Emma div:** For Emma specifically.
    * **Jacob div:** For Jacob specifically.
    * **Resor:** Taxi, SL, train tickets, public transport fares.
    * **Nöjen:** Boardgames, computer games, streaming games, theater tickets, concerts, cinema etc.
    * **Allt annat:** Misc category for things that don't fit into the others.
    * **Äta ute Mats:** When I eat for myself, often at work (Convini, Knut, work canteens, solo lunches/dinners).
    * **Utbildning:** Everything related to learning (Udemy, Pluralsight, Coursera, conferences, workshops).
    * **Utlägg arbete:** When I have paid for something related to work that will be expensed later (company reimburses me).
    * **Utlägg andra:** When I have paid for someone else who now owes me (e.g., paying for a group dinner and getting Swished back).
    * **Appar/Mjukvara:** Most often through Apple AppStore/Google Play, but could also be software subscriptions (excluding those listed separately like Adobe, Microsoft 365 etc).
    * **Musik:** When I purchase songs (iTunes), music streaming services (excluding Spotify), or gear for my music hobby (instruments, accessories).
    * **Böcker:** Books (physical, Kindle), newspaper/magazine subscriptions (digital or print).
    * **Teknik:** Electronic gear, computer stuff, gadgets, accessories, components.
    * **Kläder:** Clothing, shoes, accessories.
    * **Vattenfall:** Specifically for Vattenfall bills (heating/network).
    * **Elektricitet:** Bills from electricity providers like Telge Energi, Fortum (the actual power consumption).
    * **Internet:** Bahnhof or other internet service provider bills.
    * **Huslån:** Large transfers to mortgage accounts like Lånekonto Avanza (5699 03 201 25).
    * **Städning:** Cleaning services like Hemfrid.
    * **E-mail:** Google GSuite/Workspace subscription fees.
    * **Bankavgifter:** Bank service fees like Enkla vardagen på SEB, yearly fee for FirstCard, Revolut fees, etc.
    * **Hälsa/Familj:** Pharmacy purchases (Apotek), doctor visits (Rainer), therapy, other health-related costs.
    * **SL:** SL monthly passes or top-ups (should likely be under 'Resor' unless tracking separately). *Note: Consider merging with Resor?*
    * **Verisure:** Specifically for Verisure alarm system bills.
    * **Klippning:** Hair cuts (e.g., Barber & Books).
    * **Mobil:** Cell phone bills (Tre, Hi3G, Hallon, etc.).
    * **Fack/A-kassa:** Union fees (Ledarna) or unemployment insurance (Akademikernas a-kassa).
    * **Glasögon:** Monthly payment for glasses subscription (Synsam).
    * **Livförsäkring:** Life insurance premiums (Skandia).
    * **Hemförsäkring:** Home insurance premiums (Trygg Hansa).
    * **Sjuk- olycksfallsförsäkring:** Accident and illness insurance premiums (Trygg Hansa).
    * **HBO:** HBO Max subscription.
    * **Spotify:** Spotify subscription.
    * **Netflix:** Netflix subscription.
    * **Amazon Prime:** Amazon Prime subscription.
    * **Disney+:** Disney+ subscription.
    * **Viaplay:** Viaplay subscription.
    * **C More:** TV4 Play / C More monthly subscription.
    * **Apple+:** Apple TV+ service subscription.
    * **Youtube gmail:** YouTube Premium subscription.
    * **iCloud+:** Specifically Apple iCloud storage bills.
    * **Storytel:** Storytel subscription.
    * **Audible:** Monthly subscription or ad-hoc credits etc for Audible.
    * **Adobe Creative Cloud:** Monthly subscription for Adobe CC.
    * **Dropbox:** Yearly subscription for Dropbox.
    * **Microsoft 365 Family:** Yearly subscription for Microsoft 365.
    * **VPN:** VPN service subscription (ExpressVPN, NordVPN, etc).
    * **Samfällighet:** Yearly fee for the local community association (Brotorp).
    * **Bil underhåll:** Car maintenance costs (service, repairs, tires).
    * **Hus underhåll:** Home improvement/repair costs (Hornbach, Bauhaus, materials, contractors).
    * **Semester:** Everything spent during vacation (use more specific categories below if possible).
    * **Sparande:** Savings transfers (excluding specific goals like Barnspar or Huslån).
    * **Barnspar:** Specific monthly transfer (e.g. 500 kr) to Avanza for children's savings.
    * **Patreon:** Misc Patreon payments.
    * **Presenter:** Gifts purchased for others.
    * **Semester äta ute:** Restaurant bills during vacation.
    * **Semester nöjen:** Entertainment expenses during vacation.
    * **Semester övrigt:** Misc expenses during vacation that don't fit other semester categories.
    * **AI - tjänster:** Subscriptions or payments for AI services (Notion AI, ChatGPT Plus, Cursor, Github Copilot, Google Cloud AI, Midjourney, etc.).

* **Output:** The single category name chosen by the AI.
* **Fallback:** If the AI cannot determine a suitable category or fails, the `CATEGORY` field should be set to "UNCATEGORIZED".
* **API Configuration:**
    * Use Vertex AI.
    * `GOOGLE_CLOUD_PROJECT=aspiro-budget-analysis`
    * `GOOGLE_GENAI_USE_VERTEXAI=TRUE`
    * `GOOGLE_CLOUD_LOCATION="europe-west1"`
    * `GEMINI_MODEL_ID="gemini-2.0-flash-001"` (or newer compatible model)
* **Error Handling:** Implement retries and logging for API call failures.
* **Google Spreadsheet URLs:** The URLs to the spreadsheet containing the budget are:
    * The "New Transactions" tab where new transactions should be written: https://docs.google.com/spreadsheets/d/1P-t5irZ2E_T_uWy0rAHjjWmwlUNevT0DqzLVtxq3AYk/edit?gid=1165725543#gid=1165725543
    * The "BackendData" where configuration and names can be read: https://docs.google.com/spreadsheets/d/1P-t5irZ2E_T_uWy0rAHjjWmwlUNevT0DqzLVtxq3AYk/edit?gid=968129680#gid=968129680
    * The "Transactions" tab where existing transactions are: https://docs.google.com/spreadsheets/d/1P-t5irZ2E_T_uWy0rAHjjWmwlUNevT0DqzLVtxq3AYk/edit?gid=925237105#gid=925237105

## 7. Output (Google Sheet Integration)

* The application must connect to the user's "MOL Aspire Budget" Google Sheet.
* Authentication with Google Sheets API is required and OAuth 2.0 MUST be used. The application should store the client secret etc as well as the token to facilitate future logins.
* The transformed and categorized transactions should be **appended** as new rows to the **'New Transactions'** tab.
* The application should not modify any other tabs.
* Consider handling potential API rate limits or errors during the write process.

## 8. Technical Specifications

* **Language:** Python 3.x
* **Libraries (Recommended):**
    * `pandas` (for data manipulation and parsing CSV/Excel files)
    * `google-cloud-aiplatform` (for Vertex AI/Gemini interaction)
    * `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` (for Google Sheets API) OR `gspread` and `gspread-dataframe` (often simpler for sheet interactions)
    * `openpyxl` (if direct `.xlsx` reading is preferred over pre-conversion to CSV)
    * `xlrd` (if direct `.xls` reading is preferred over pre-conversion to CSV)
* **Interface:** Command-Line Interface (CLI). The user will run the script, likely providing the input filename and account type as arguments.
* **Configuration:** API keys, Google Sheet ID, file paths, and potentially category lists/mappings should be managed via configuration files or environment variables, not hardcoded.

## 9. Assumptions

* The structure (column names and order) of the bank export files remains consistent.
* The target Google Sheet ('MOL Aspire Budget') and the 'New Transactions' tab exist and have the specified column headers (`DATE`, `OUTFLOW`, `INFLOW`, `CATEGORY`, `ACCOUNT`, `MEMO`, `STATUS`).
* Valid account names are defined in the 'BackendData' tab, specifically in Column F ('Account'). The application will need access to this list. (*Initial analysis failed to confirm this column - verification needed*).
* The user has the necessary permissions (GCP project, Vertex AI API enabled, Google Sheets API enabled) and credentials set up for the application to run.
* Credit card exports (First Card, Strawberry) primarily contain expense transactions, and positive amounts in their exports represent outflows. Specific handling for credit card payments/inflows is TBD.

## 10. Further Clarifications

1.  **Account Name Source:** Please confirm the exact Sheet and Column name within the Google Sheet where the definitive list of `ACCOUNT` names (e.g., "SEB Privat", "First Card", "Revolut", "Strawberry Card") is maintained?
    * Account names can be read from Column I in BackendData: https://docs.google.com/spreadsheets/d/1P-t5irZ2E_T_uWy0rAHjjWmwlUNevT0DqzLVtxq3AYk/edit?gid=968129680#gid=968129680
2.  **Account Mapping:** How should the application determine which `ACCOUNT` name to assign to the transactions from a given input file? (e.g., Ask the user every time? Use filename conventions like `seb_export.csv` -> "SEB Privat"? Add a configuration mapping?)
    * The script should use a flag like "--account seb" (or firstcard, revolut, strawberry)
3.  **Credit Card Inflows:** How should payments *to* the credit card accounts (First Card, Strawberry) be handled? These would be inflows to the credit card account but outflows from another account (like SEB). Should the tool attempt to identify these, perhaps marking them for special review or categorizing them as '↕️ Account Transfer'? Currently, the spec assumes positive values in these files are outflows.
    * The invoice to FirstCard is paid from the SEB account, the description is often "NORDEA BANK ABP, FILIAL" or similar. This should be logged as two transactions:
        1. An "↕️ Account Transfer" with the amount as OUTFLOW and 'ACCOUNT' set to "💰 SEB" and MEMO set to "Betalning FirstCard"
        2. AN "↕️ Account Transfer" with the amount as INFLOW and 'ACCOUNT' set to "💳 First Card" with MEMO "Betalning från SEB"
    * A transfer of money from SEB to Revolut should simlarly be two transactions as above for "💰 SEB" and "💳 Revolut" and MEMO "Överföring till Revolut" respektive "Överföring från SEB"
    * A payment to Strawberry is often described as "SEB KORT BANK AB". This should be logged as two Account transfers as above.
5.  **Duplicate Handling:** Should the application check if a transaction (based on Date, Amount, Memo, Account) already exists in the 'New Transactions' or 'Transactions' tab before adding it, to prevent duplicates?
    * Yes, it should look for the last transactions for that account as they are logged in "Transactions" tab and make an intelligent decision on which date the new transactions starta at.
6.  **Error Handling Details:** What specific behavior is desired if a file format is unrecognized, parsing fails, or Google Sheets/Gemini APIs are unavailable? (e.g., Stop processing? Skip file? Log errors?).
    * It should store every transaction it has categorized in a file atomically on a local file so that if something breaks it can pick-up where it failed. 
    * It should not update the spreadsheet until all transactions have passed
    * It should give detailed logging on the progress of the categorization and processing, using tqdm as well as descriptive error messages.
7.  **Starting Balance / Balance Adjustments:** Should the AI ever select `➡️ Starting Balance` or `🔢 Balance Adjustment`? (Probably not automatically).
    * No, it should never use these categories. They are only used manually.

