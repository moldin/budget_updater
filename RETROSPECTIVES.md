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