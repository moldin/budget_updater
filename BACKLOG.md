# BACKLOG: Bank Transaction Processor

This document outlines the development backlog for the Bank Transaction Processor application, following an agile approach with iterative development.

## Coding Principles

* **Incremental Development:** Make small, testable changes. Commit frequently with clear messages.
* **Refactor Continuously:** Keep the codebase clean and maintainable. Refactor when code smells appear (complexity, duplication, long files/functions). Aim to keep functions concise and files under ~300 lines where practical.
* **DRY (Don't Repeat Yourself):** Prioritize reusable functions, classes, and modules. Abstract common logic (e.g., date parsing, amount handling, spreadsheet interaction).
* **Readability:** Write clear, self-documenting code with meaningful variable and function names. Add comments to explain the *why* behind complex logic, not just the *what*.
* **Modularity:** Structure the code logically into modules (e.g., `parsers`, `categorizer`, `sheets_api`, `main`).
* **Testing:** Write unit tests for core logic, especially parsing functions, transformation logic, and API interactions (potentially using mocks).
* **GIT management:** Never push anything to git until we have verified that the code works.
* **Dependency Management:** Use `uv` for managing Python dependencies and virtual environments.
* **Type Hinting:** Use Python type hints for improved code clarity and static analysis.
* **Configuration:** Keep sensitive information (API keys, Sheet IDs) and configurable parameters out of the code (use environment variables or configuration files).
* **Error Handling:** Implement robust error handling and provide informative logging/messages to the user.
* **PEP 8:** Follow standard Python style guidelines (PEP 8).
* **Wait for Confirmation:** After proposing a file edit, wait for confirmation or indication that the change has been applied before proceeding with dependent steps.

## Iterations (Sprints)

Each iteration aims to deliver a runnable version of the application with added functionality.

---

### Iteration 1: Project Setup & Core Connectivity

**Goal:** Establish the project structure, dependencies, and basic connections to Google Sheets and Vertex AI. Prove end-to-end connectivity by writing dummy data.

**Tasks:**

- [x] **Project Init:** Set up the project directory structure in a well structured way (with src test data folders etc, use standard format for github repos for python projects) Initialize `git`. Initialize `uv` and create `pyproject.toml`. Remote repo: https://github.com/moldin/budget_updater.git
- [x] **Create venv:** Use 'uv' to create a virtual environment.
- [x] **Dependencies:** Add initial dependencies (`pandas`, `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `google-cloud-aiplatform`, `tqdm`).
- [x] **CLI Framework:** Set up basic CLI argument parsing (e.g., using `argparse`) to accept placeholder arguments.
- [x] **Google Sheets Auth:** Implement OAuth 2.0 flow for Google Sheets API. Store/retrieve credentials securely (token file).
- [x] **Sheet Interaction (Read):** Create a module (`sheets_api.py`?) to connect to the Google Sheet. See URLs in `PRD.md`file.
- [x] **Analyse Spreadsheet:** Read the tabs "Transactions", "New Transactions", "BackendData" and log and describe in detail what you find in a local file that could used as reference in the project. Specifically read the list of valid `ACCOUNT` names from `BackendData` (Column I) and `CATEGORIES`from `BackendData` (Column G). Also make note of which row the header is in "Transcations" tab and what the column names are. They should be the same as in "New Transactions". These column names are crucial when the script then remaps the bank export files.
- [x] **Vertex AI Auth:** Configure authentication for Vertex AI using environment variables (`GOOGLE_APPLICATION_CREDENTIALS`, project ID, location etc.). Test basic client initialization. See the `PRD.md` file for which values should be used.
- [x] **Sheet Interaction (Write):** Implement functionality to append a row of *dummy* data (with correct columns: `DATE`, `OUTFLOW`, `INFLOW`, `CATEGORY`, `ACCOUNT`, `MEMO`, `STATUS`) to the 'New Transactions' tab.
- [x] **README:** Create an initial `README.md` with setup instructions.
- [x] **`.gitignore`:** Add a standard Python `.gitignore` file.
- [x] **Confirm UAT:** Make sure that we have a way of testing the functionality so far. 
- [ ] **Push to git:** When user confirms all works well, remember to push everything to git: https://github.com/moldin/budget_updater.git

**Deliverable:** A runnable script that authenticates with Google Sheets, reads account names, authenticates with Vertex AI (basic init), and appends a hardcoded dummy transaction row to the 'New Transactions' sheet.

---

### Iteration 2: SEB Parsing & Basic Transformation

**Goal:** Implement parsing for the first bank format (SEB) and transform its data into the target format (excluding AI categorization).

**Tasks:**

- [x] **CLI Arguments:** Refine CLI arguments to accept `--file <path_to_export>` and `--account <account_name>`. Validate the provided account name against the list read from `BackendData`.
- [x] **Parser Module:** Create a `parsers` module. Implement `parse_seb(file_path)` function.
    * Handle ~~CSV reading~~ **Excel reading (.xlsx)**, potential header rows, and encoding.
    * Extract `Bokföringsdatum`, `Text`, `Belopp` from `Sheet1`.
    * Handle potential errors during parsing.
    * Add `openpyxl` dependency.
- [x] **Transformation Logic:** Create a core transformation function/module.
    * Input: Raw transaction data (dict or object) from the parser.
    * Output: A dictionary matching the target sheet structure (`DATE`, `OUTFLOW`, `INFLOW`, `CATEGORY`, `ACCOUNT`, `MEMO`, `STATUS`).
    * Implement logic for `DATE` formatting.
    * Implement `OUTFLOW`/`INFLOW` logic based on the sign of `Belopp`.
    * Format `OUTFLOW`/`INFLOW` as strings with comma decimal for Swedish locale, use empty string for zero.
    * Set `ACCOUNT` based on CLI argument.
    * Set `MEMO` from `Text`.
    * Set `STATUS` to ✅.
    * Set `CATEGORY` to a placeholder like "PENDING_AI".
- [x] **Main Script Logic:** Update the main script to:
    * Call the appropriate parser based on (initially hardcoded for) SEB.
    * Iterate through parsed transactions.
    * Call the transformation logic for each transaction.
    * Collect the transformed data.
- [x] **Sheet Interaction (Write):** Update the sheet writing logic (`sheets_api.append_transactions`) to append the list of *transformed* SEB transactions.
- [x] **Testing:** Add basic tests for SEB parsing and transformation logic.
- [x] **Fixes:** Corrected Sheets API authentication token saving/loading (`pickle` issue). Adapted SEB parser for `.xlsx` input instead of CSV.

**Deliverable:** A script that takes an SEB export file (`.xlsx`) and account name, parses it, transforms the data (with placeholder category and correct currency formatting), and appends the results to the 'New Transactions' sheet. Authentication token persists correctly.

---

### Iteration 3: Gemini AI Categorization Integration

**Goal:** Integrate Vertex AI Gemini to categorize the parsed transactions.

**Tasks:**

- [x] **Categorizer Module:** Create a `categorizer.py` module.
- [x] **Fetch Categories:** Read the full category list *and descriptions* from the PRD (or potentially a config file/sheet later).
- [x] **AI Prompting:** Construct the prompt for Gemini, including the context (category list with descriptions) and the transaction `MEMO`.
- [x] **Vertex AI Call:** Implement a function `categorize_transaction(memo, categories)` that calls the Gemini model via the Vertex AI SDK.
    - [x] Handle API responses.
    - [x] Implement basic retry logic for transient errors. (Note: Basic error handling added, retry logic can be enhanced later if needed).
    - [x] Return the category name or "UNCATEGORIZED" on failure/uncertainty.
- [x] **Main Script Logic:**
    - [x] Modify the main loop to call `categorize_transaction` for each transformed transaction *before* writing to the sheet.
    - [x] Update the `CATEGORY` field in the transformed data with the AI's response.
    - [x] Integrate `tqdm` to show progress during categorization.
- [x] **Configuration:** Ensure Vertex AI project/location/model settings are configurable (env vars recommended, defaults added via `config.py`).
- [x] **Testing:** Add tests for the categorization module (mocking the API call).
- [x] **Refinement (Added):** Modified AI interaction to generate a concise `Memo` alongside the `Category`. Updated prompt, parsing, main loop, and tests accordingly.
- [x] **Refinement (Added):** Added support for `.env` file loading using `python-dotenv`.
- [x] **Refinement (Added):** Implemented account alias mapping (`seb` -> `💰 SEB`) for CLI input.
- [x] **Refinement (Added):** Added sorting of transactions by date before upload.

**Deliverable:** The script now categorizes SEB transactions using Gemini AI, generates a cleaned memo, accepts account aliases, sorts output, uses `.env` for credentials, and appends results to the sheet. Progress is shown via `tqdm`.

---

### Refactoring Iteration (Post-Iteration 3)

**Goal:** Improve code structure for maintainability and extensibility before adding more complex features and parsers. Focus on decoupling components and standardizing data flow.

**Tasks:**

- [x] **Refactor Parser Selection:**
    - Create a parser registry (e.g., a dictionary mapping account aliases like `'seb'` to their corresponding parser functions like `parse_seb`) probably within the `parsers` module or a dedicated factory function.
    - Update `main.py` to use this registry/factory to dynamically select the parser based on the `--account` alias, removing the `if/elif` block.
    - **Verification:** Run `budget-updater --account seb --file <seb_file>` and confirm it still parses correctly.
- [x] **Standardize Parser Output:**
    - Define a clear, consistent structure (e.g., DataFrame columns) that *all* parsers must return. This should include standardized column names for date, description, and a signed amount (e.g., `ParsedDate`, `ParsedDescription`, `ParsedAmount`).
    - Modify `parsers.parse_seb` to adhere to this structure (e.g., rename columns, ensure `ParsedAmount` has the correct sign).
    - **Verification:** Run SEB processing. Inspect the DataFrame returned by the parser. Check logs.
- [x] **Simplify Transformation Input:**
    - Update `transformation.transform_transactions` to expect the standardized DataFrame structure defined above (e.g., it now uses `ParsedAmount` for `OUTFLOW`/`INFLOW` logic directly).
    - Remove any bank-specific logic currently assumed within the transformation function (it should be purely generic).
    - **Verification:** Run SEB processing end-to-end. Check the output in the Google Sheet. Check logs.
- [x] **Externalize Category List:**
    - Move the large `CATEGORIES_WITH_DESCRIPTIONS` string literal from `categorizer.py` into `config.py` as a constant.
    - Update `categorizer.py` to import and use this constant from `config`.
    - **Verification:** Run SEB processing with categorization. Confirm categories are still generated correctly.
- [x] **(Optional) Configuration Review:** Briefly review `config.py`. Ensure necessary constants are present and naming is consistent. Consider if any other hardcoded values (e.g., `STATUS` emoji) should be moved there.

**Deliverable:** A refactored codebase where parser selection is dynamic, parser output is standardized, the transformation function is generic, and the category list is centralized in configuration. The application should still process SEB files correctly end-to-end.

---

### Iteration 4: Duplicate Handling & State Management

**Goal:** Prevent adding duplicate transactions and make the process resumable.

**Tasks:**

- [ ] **Sheet Interaction (Read Transactions):** Implement logic to read existing transactions from the 'Transactions' tab for the specified account.
- [ ] **Find Last Date:** Determine the date of the most recent transaction for the given account in the 'Transactions' tab.
- [ ] **Input Filtering:** Filter the parsed transactions from the input file, only processing those *after* the last recorded date.
- [ ] **Local State File:** Implement logic to save processed/categorized transactions to a temporary local file (e.g., JSON or CSV) *before* attempting to write to the Google Sheet. This file should be updated atomically or transactionally.
- [ ] **Resumability:** If the script fails during the Sheet writing phase, it should be possible to re-run it, detect the local state file, and attempt writing *only* those transactions to the sheet without re-processing/re-categorizing.
- [ ] **Atomic Sheet Update:** Ensure the batch append to Google Sheets happens only *after* all transactions for the file have been successfully processed and saved locally. Clear the local state file upon successful sheet update.
- [ ] **Logging:** Improve logging for better debugging, especially around duplicate checks and state management.

**Deliverable:** The script avoids adding transactions already present in the 'Transactions' tab, processes only new entries, and uses a local file to ensure data isn't lost if the sheet update fails.

---

### Iteration 5: Add Revolut Parser & Refactor

**Goal:** Add support for Revolut transactions and refactor parsing logic.

**Tasks:**

- [ ] **Revolut Parser:** Implement `parse_revolut(file_path)` in the `parsers` module.
    * Handle Revolut's specific columns (`Completed Date`, `Description`, `Amount`, `Fee`).
    * Handle date/time format.
    * Incorporate the `Fee` into the `OUTFLOW` calculation in the transformation step.
- [ ] **Parser Selection Logic:** Update the main script or a factory function to select the correct parser based on the `--account` flag (or potentially file content sniffing later).
- [ ] **Refactor Transformation:** Review the transformation logic. Ensure it correctly handles inputs from both SEB and Revolut parsers (e.g., different date formats, amount/fee structures). Abstract common transformation steps.
- [ ] **Testing:** Add tests for Revolut parsing and ensure transformation tests cover Revolut cases.

**Deliverable:** The script now supports both SEB and Revolut files, selected via the `--account` flag. Parsing and transformation logic is refactored for better maintainability.

---

### Iteration 6: Add First Card Parser & Refactor

**Goal:** Add support for First Card and implement the special handling for invoice payments.

**Tasks:**

- [ ] **First Card Parser:** Implement `parse_firstcard(file_path)` in the `parsers` module.
    * Handle First Card columns (`Datum`, `Reseinformation / Ink\u00f6psplats`, `Belopp`).
    * Remember positive `Belopp` usually means `OUTFLOW`.
- [ ] **Account Transfer Logic:**
    * In the main processing loop or transformation step, add logic to detect First Card payment transactions (based on `MEMO` like "NORDEA BANK ABP, FILIAL").
    * When detected, instead of creating one transaction, create *two* "↕️ Account Transfer" transactions as specified in the PRD (one outflow from SEB, one inflow to First Card). *This assumes the payment originates from SEB - may need refinement.*
    * Ensure regular First Card purchases are still processed normally (as outflows).
- [ ] **Parser Selection Logic:** Update parser selection to include First Card.
- [ ] **Testing:** Add tests for First Card parsing and the specific account transfer logic.

**Deliverable:** The script supports First Card files, correctly identifying purchases as outflows and handling invoice payments by creating the corresponding two account transfer entries.

---

### Iteration 7: Add Strawberry Card Parser & Refactor

**Goal:** Add support for Strawberry Card and finalize shared logic.

**Tasks:**

- [ ] **Strawberry Parser:** Implement `parse_strawberry(file_path)` in the `parsers` module.
    * Handle Strawberry columns (`Bokfört`, `Specifikation`, `Belopp`).
    * Implement **Excel serial date conversion** for the `Bokfört` column.
    * Remember positive `Belopp` usually means `OUTFLOW`.
- [ ] **Account Transfer Logic (Strawberry):** Adapt the account transfer logic to detect Strawberry Card payments (e.g., "SEB KORT BANK AB") and generate the two corresponding transfer entries.
- [ ] **Refactor:** Consolidate any remaining duplicated logic between parsers or in the main script. Ensure the account transfer logic is robust.
- [ ] **Parser Selection Logic:** Update parser selection to include Strawberry.
- [ ] **Testing:** Add tests for Strawberry parsing (including date conversion) and its account transfer logic.

**Deliverable:** The script supports all four bank formats (SEB, Revolut, First Card, Strawberry). Parsing, transformation, and account transfer logic are reasonably robust and refactored.

---

### Iteration 8: Refinement, Documentation & Final Testing

**Goal:** Polish the application, improve documentation, and perform thorough testing.

**Tasks:**

- [ ] **Code Review & Cleanup:** Perform a final pass over the codebase for clarity, consistency, and adherence to principles.
- [ ] **Error Handling Review:** Test edge cases: empty files, files with unexpected formats, API failures (Sheets, Vertex AI), network issues. Ensure graceful failure and informative messages.
- [ ] **Configuration Finalization:** Ensure all necessary configurations (Sheet ID, API settings, account mappings if not using CLI flags) are handled cleanly (e.g., via a `.env` file or a `config.yaml`).
- [ ] **README Update:** Update `README.md` with final usage instructions, configuration steps, and troubleshooting tips.
- [ ] **Requirements Update:** Ensure `pyproject.toml` lists all necessary dependencies.
- [ ] **End-to-End Testing:** Test the complete workflow with real export files for all four banks. Verify data integrity in the 'New Transactions' sheet.
- [ ] **(Optional) File Sniffing:** Implement logic to *attempt* auto-detecting the bank format based on file headers/content, potentially removing the need for the `--account` flag if reliable.

**Deliverable:** A well-tested, documented, and robust version of the Bank Transaction Processor application ready for regular use.

