# Retrospectives

This file documents the retrospectives held after each development iteration.

---

## Iteration 1: Project Setup & Core Connectivity

**Date:** 2025-05-03

**Participants:** User, Gemini

### What went well?

*   **Project Scaffolding:** Successfully set up the standard Python project structure (`src`, `tests`, `data`), initialized `git`, and configured `uv` with a `pyproject.toml` containing necessary dependencies.
*   **Core API Connectivity:** Established functional connections to both Google Sheets API (including OAuth 2.0 flow with token storage/refresh and handling specific credential filenames) and Vertex AI (basic client initialization).
*   **Sheet Interaction:** Implemented logic to read required data (account names, category names, headers) from the target Google Sheet.
*   **Basic Functionality:** Added a working `--test` mode to append dummy data and an `--analyze` mode to generate a structural analysis file (`sheet_analysis.md`), proving end-to-end connectivity and basic script execution.
*   **CLI:** Set up a command-line interface using `argparse` and defined a `budget-updater` entry point, making the script runnable after installation.
*   **Documentation & Git:** Created an initial `README.md` and a comprehensive `.gitignore`.

### What were the challenges?

*   **Execution Environment:** Encountered `ModuleNotFoundError` issues initially. This stemmed from not consistently ensuring the package was installed in editable mode (`pip install -e .`) within the active virtual environment (`source .venv/bin/activate`), which is necessary for the entry point and relative imports to work correctly during development.
*   **Credential File Handling:** The specific filename provided for the Google OAuth client secret wasn't anticipated by the initial code, requiring a revision to use pattern matching (`glob`) for more robustness.
*   **Workflow Adherence:** Initially, I combined too many steps before verifying functionality, deviating from the agreed-upon principle of small, verifiable increments. Several changes were made and committed before confirming they worked as expected.

### How did we solve them?

*   **Environment/Installation:** Explicitly ran `pip install -e .` after activating the virtual environment to ensure the package was correctly installed and accessible.
*   **Credential Files:** Modified `sheets_api.py` to search for `client_secret_*.json` patterns in the `credentials/` directory.
*   **Workflow Correction:** Adjusted the process to explicitly test each logical code change using the `budget-updater` command (e.g., `--test`, `--analyze`) and waited for confirmation before committing or moving to the next task, following user feedback.

### What did we learn? / Key Takeaways for Next Iteration

*   **Verify Installation:** Always ensure the package is installed in editable mode (`pip install -e .`) within the active venv for development. This makes the entry points (`budget-updater`) and internal package imports work reliably.
*   **Test After *Every* Change:** Reinforce the discipline of testing functionality immediately after *each* code modification, no matter how small, before committing. Use the defined CLI commands for testing.
*   **Confirm Before Proceeding:** Explicitly check in with the user after verifying a task is complete and *before* starting the next task in the backlog.
*   **Anticipate Variations:** Be mindful that external factors (like filenames) might differ from initial assumptions. Implement flexible solutions where possible.
*   **Use Entry Points:** Prefer running the application via its installed entry point (`budget-updater` in this case) rather than `python -m ...` or runner scripts once `pip install -e .` is done, as it simulates the end-user experience better.

---

## Iteration 2: SEB Parsing & Basic Transformation

**Date:** 2025-05-03

**Participants:** User, Gemini

### What went well?

*   **SEB Parser Implementation:** Successfully created a parser (`parsers.parse_seb`) capable of reading SEB `.xlsx` files (adapting from the initial CSV plan).
*   **Column Identification & Extraction:** The parser correctly identifies and extracts the required columns (`Bokföringsdatum`, `Text`, `Belopp`) from the specified sheet (`Sheet1`).
*   **Data Transformation:** Implemented `transformation.transform_transactions` to convert parsed data into the target Google Sheet structure (`DATE`, `OUTFLOW`, `INFLOW`, `CATEGORY`, `ACCOUNT`, `MEMO`, `STATUS`).
*   **Currency Formatting:** Correctly identified and fixed the currency formatting issue by sending locale-specific strings (e.g., "123,45") and empty strings for zero values, resolving spreadsheet display problems.
*   **Authentication Fix:** Diagnosed and fixed the `token.json` pickling issue in `sheets_api`, ensuring authentication credentials persist correctly between runs.
*   **CLI Argument Validation:** Added validation for the `--account` argument against the list loaded from the spreadsheet.
*   **Module Integration:** Successfully integrated the parser and transformer modules into the main application flow in `main.py`.
*   **Testing:** Added unit tests for both the parser (`tests/test_parsers.py`) and the transformer (`tests/test_transformation.py`), covering basic success and failure cases.
*   **Workflow Adherence (Improved):** We successfully applied the "Wait for Confirmation" principle and the "Test After *Every* Change" principle (after a reminder!), which helped catch issues like the parser expecting CSV instead of XLSX and the authentication bug.

### What were the challenges?

*   **Initial File Format Misunderstanding:** The parser was initially built for CSV based on early interpretation, requiring modification to handle the actual `.xlsx` format provided.
*   **Authentication Bug:** The `pickle` saving/loading logic for credentials was flawed, requiring debugging and correction.
*   **Spreadsheet Formatting:** The interaction between Python float representation and Google Sheets locale settings caused incorrect currency display, needing specific string formatting as a workaround.
*   **Forgetting Principles:** I initially forgot the "Test After *Every* Change" principle and tried to move to Iteration 3 prematurely.

### How did we solve them?

*   **Parser Adaptation:** Modified `parse_seb` to use `pandas.read_excel`, specifying the sheet name and adding the `openpyxl` dependency.
*   **Authentication Debugging:** Analyzed the `AttributeError` traceback, identified the `pickle.dump`/`load` mismatch (saving JSON string vs. loading object), and corrected the code to pickle the `Credentials` object directly. Manually deleted the old token file to allow regeneration.
*   **Currency Formatting:** Updated `transform_transactions` to format numbers as Swedish locale strings (`f"{value:.2f}".replace('.', ',')`) and use empty strings (`''`) instead of `0.0` for zero values before sending to the sheet.
*   **Workflow Correction:** User reminder prompted adherence to testing principles. Adopted the explicit wait step after proposing edits.

### What did we learn? / Key Takeaways for Next Iteration

*   **Verify Input Formats Early:** Double-check assumptions about input file formats (XLSX vs. CSV) against provided examples or documentation early in the implementation step.
*   **Test API Interactions Thoroughly:** Interactions with external APIs (like Google Sheets locale handling) can have subtle issues. Test the *output* in the target system (the spreadsheet) to confirm formatting.
*   **Pickle Objects Carefully:** Ensure consistency between what is saved (`pickle.dump`) and what is expected when loading (`pickle.load`). Pickling the object directly is often more robust than pickling its string representation if the loading function expects the object.
*   **Adhere Strictly to Workflow:** Consistently follow the established principles ("Test After *Every* Change", "Wait for Confirmation") to catch errors early and avoid rework. Slowing down slightly improves overall speed.
*   **Parser Flexibility:** As we add more parsers, consider how to handle potential variations in sheet names or column headers within the same bank's exports over time.

--- 