# MERGE_PLAN.md: Integrating ADK-based Transaction Categorizer

## 1. Overview

**Goal:** Replace the current Vertex AI-based `categorizer.py` in the `Budget_updater` project with the more advanced Google Agent Development Kit (ADK)-based `transaction_categorizer` from the `GCP_BudgetAgent` project.

**Benefits:**
*   Leverage the structured approach of Google ADK for agent development.
*   Integrate Gmail search functionality for richer transaction context and more accurate categorization.
*   Utilize a more sophisticated prompting strategy and multi-agent capabilities (root agent and Gmail sub-agent).

**Key Official ADK Resources:**
*   **ADK Documentation:** [https://google.github.io/adk-docs/](https://google.github.io/adk-docs/)
*   **ADK Quickstart:** [https://cloud.google.com/vertex-ai/generative-ai/docs/agent-development-kit/quickstart](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-development-kit/quickstart)

## 2. Prerequisites

*   **Python:** Version 3.10 or higher (as required by `GCP_BudgetAgent` and ADK).
*   **Google Cloud Project:** An active GCP project.
*   **APIs Enabled in GCP:**
    *   Vertex AI API
    *   Gmail API
*   **OAuth 2.0 Credentials:** A `client_secret.json` file for the Gmail API. This can be obtained from the Google Cloud Console by creating OAuth 2.0 client ID credentials for a "Desktop app" or "Web application" (if applicable to your setup).
*   **Google Cloud SDK:** `gcloud` CLI installed and authenticated via `gcloud auth application-default login`.
*   **Virtual Environment:** Recommended for managing dependencies.
*   **Familiarity:** Basic understanding of Google ADK concepts is helpful.

## 3. Phase 1: Setup and Configuration

### 3.1. Dependency Management

1.  **Identify Dependency File:** Determine if `Budget_updater` uses `pyproject.toml` (with a build system like Poetry or Hatch) or a `requirements.txt` file.
2.  **Add Dependencies:** Add the following packages to the chosen dependency file. Versions are based on `GCP_BudgetAgent` and common ADK usage:
    ```
    # For requirements.txt
    google-adk>=0.4.0
    google-cloud-aiplatform[adk,agent_engines]>=1.91.0 
    absl-py>=1.0.0
    python-dotenv>=1.0.0
    google-auth-oauthlib>=1.0.0 
    google-api-python-client>=2.100.0
    beautifulsoup4>=4.12.0
    pydantic>=2.0.0 
    # email-validator>=2.0.0 # Included in GCP_BudgetAgent's remote deployment, consider if needed
    ```
    If using `pyproject.toml`, adapt the format accordingly.
3.  **Install Dependencies:**
    *   If `Budget_updater` is set up as a package (e.g., with `pyproject.toml` and `src` layout):
        ```bash
        pip install -e .
        ```
    *   If using `requirements.txt`:
        ```bash
        pip install -r requirements.txt
        ```

### 3.2. Environment Variables

1.  **Create/Update `.env` file:** In the root directory of the `Budget_updater` project, ensure a `.env` file exists.
2.  **Add/Update Variables:**
    ```dotenv
    GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
    GOOGLE_CLOUD_LOCATION="your-gcp-region" # e.g., us-central1 or europe-west1
    GOOGLE_CLOUD_STAGING_BUCKET="gs://your-gcp-staging-bucket-name" # Must exist, for ADK
    # GEMINI_MODEL_ID="gemini-2.5-flash-preview-04-17" # Can be set here or in config.py
    ```
    *   The ADK agent setup typically relies on Application Default Credentials (`gcloud auth application-default login`) for Vertex AI. The `GOOGLE_APPLICATION_CREDENTIALS` environment variable might not be strictly necessary for the ADK part if ADC is used, but the old `categorizer.py` checked for it. Consolidate this based on preferred auth method.

### 3.3. Directory and File Structure Setup

1.  **Create ADK Categorizer Directory:**
    ```bash
    mkdir -p Budget_updater/src/budget_updater/adk_categorizer
    ```
2.  **Copy ADK Agent Files:**
    *   Recursively copy the entire contents of `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/` into the newly created `Budget_updater/src/budget_updater/adk_categorizer/`.
    This includes `agent.py`, `prompt.py`, `config.py` (which will be adapted), and the `sub_agents/` directory.
3.  **Create Credentials Directory:**
    ```bash
    mkdir -p Budget_updater/credentials
    ```
4.  **Place OAuth Client Secret:**
    *   Download your `client_secret.json` file from the Google Cloud Console.
    *   Place it inside `Budget_updater/credentials/client_secret.json`.
    *   The `token.pickle` file (for Gmail API token storage) will be automatically generated in this directory on the first successful run of the Gmail tool.
5.  **Add `__init__.py` to `adk_categorizer` and its subdirectories if missing, to ensure they are treated as packages.**
    *   `Budget_updater/src/budget_updater/adk_categorizer/__init__.py`
    *   `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/__init__.py`
    *   `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/__init__.py`

### 3.4. Configuration Consolidation and Adjustments

1.  **Main Configuration File:** The primary configuration will reside in `Budget_updater/src/budget_updater/config.py`.
2.  **Update `Budget_updater/src/budget_updater/config.py`:**
    *   Add settings required by the ADK agent and Gmail tool:
        ```python
        from pathlib import Path

        # ... existing GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION ...
        # GOOGLE_CLOUD_STAGING_BUCKET = os.getenv("GOOGLE_CLOUD_STAGING_BUCKET") # If using .env

        # ADK and New Categorizer specific
        GEMINI_MODEL_ID = "gemini-2.5-flash-preview-04-17" # Or from .env

        # Gmail Tool Credentials (paths relative to project root)
        CREDENTIALS_DIR = Path("credentials") # Points to Budget_updater/credentials
        CLIENT_SECRET_FILENAME = "client_secret.json"
        TOKEN_PICKLE_FILENAME = "token.pickle"

        # Construct full paths for gmail_tool.py to use
        CLIENT_SECRET_FILE_PATH = CREDENTIALS_DIR / CLIENT_SECRET_FILENAME
        TOKEN_PICKLE_FILE_PATH = CREDENTIALS_DIR / TOKEN_PICKLE_FILENAME

        # Ensure CATEGORIES_WITH_DESCRIPTIONS is present and up-to-date.
        # CATEGORIES_WITH_DESCRIPTIONS = """...your categories..."""
        ```
    *   Remove any configurations specific to the old `categorizer.py` if they are no longer needed (e.g., its direct Vertex AI initialization flags if different, old prompt building logic).

3.  **Update `Budget_updater/src/budget_updater/adk_categorizer/prompt.py`:**
    *   This file defines `ROOT_AGENT_INSTRUCTION`. It needs access to `CATEGORIES_WITH_DESCRIPTIONS` from the main `Budget_updater` config.
    *   Modify the top of `adk_categorizer/prompt.py`:
        ```python
        from budget_updater import config as main_budget_config # Assuming 'src' is a root for imports

        # ... other imports ...

        # The ROOT_AGENT_INSTRUCTION f-string should then use:
        # {main_budget_config.CATEGORIES_WITH_DESCRIPTIONS}
        # Example:
        # ROOT_AGENT_INSTRUCTION = f"""
        # ...
        # <CATEGORIES_WITH_DESCRIPTIONS>
        # {main_budget_config.CATEGORIES_WITH_DESCRIPTIONS}
        # </CATEGORIES_WITH_DESCRIPTIONS>
        # ...
        # """
        ```

4.  **Update `Budget_updater/src/budget_updater/adk_categorizer/config.py` (the copied one):**
    *   This file should be simplified and removed if all its relevant settings (like `GEMINI_MODEL_ID`) are now sourced from `Budget_updater/src/budget_updater/config.py`.
    *   For a cleaner setup, modify `adk_categorizer/agent.py` and `adk_categorizer/sub_agents/gmail_agent/agent.py` to import `GEMINI_MODEL_ID` from `budget_updater.config`.
        ```python
        # In adk_categorizer/agent.py and adk_categorizer/sub_agents/gmail_agent/agent.py
        from budget_updater.config import GEMINI_MODEL_ID
        # Remove: from .config import GEMINI_MODEL_ID
        ```
    *   Ensure `adk_categorizer/config.py`, is updated accordingly.

5.  **Update `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/gmail_tool.py`:**
    *   This file handles Gmail API authentication and calls. It needs to use the credential paths defined in `Budget_updater/src/budget_updater/config.py`.
    *   Modify the top of `gmail_tool.py`:
        ```python
        from budget_updater import config as main_budget_config
        from pathlib import Path # Ensure Path is imported
        import os # Ensure os is imported

        # Replace old credential path definitions:
        # CLIENT_SECRET_FILE = 'credentials/client_secret.json'
        # TOKEN_PICKLE_FILE = 'credentials/token.pickle'
        # CREDENTIALS_DIR = 'credentials'

        # Use paths from the main Budget_updater config:
        CLIENT_SECRET_FILE = main_budget_config.CLIENT_SECRET_FILE_PATH
        TOKEN_PICKLE_FILE = main_budget_config.TOKEN_PICKLE_FILE_PATH
        # CREDENTIALS_DIR is implicitly main_budget_config.CREDENTIALS_DIR

        # In get_gmail_service() function:
        # Ensure os.makedirs uses main_budget_config.CREDENTIALS_DIR if it creates the directory.
        # Example:
        # if not os.path.exists(main_budget_config.CREDENTIALS_DIR):
        #     try:
        #         os.makedirs(main_budget_config.CREDENTIALS_DIR)
        #     except OSError as e:
        #         print(f"Error creating credentials directory {main_budget_config.CREDENTIALS_DIR}: {e}")
        #         return None
        ```

### 3.5. Gmail API Authentication and Authorization

1.  **Initial Authentication:** Ensure `gcloud auth application-default login` has been run.
2.  **OAuth Consent:** The first time the application runs and attempts to use the `gmail_tool.py` (which calls `get_gmail_service`), it will:
    *   Look for `TOKEN_PICKLE_FILE`.
    *   If not found or invalid, it will use `CLIENT_SECRET_FILE` to initiate an OAuth 2.0 flow.
    *   A URL will be printed to the console, or a browser window will attempt to open.
    *   The user must visit this URL, log in with the Google account whose Gmail is to be accessed, and grant permissions.
    *   Upon successful authorization, `token.pickle` will be created in `Budget_updater/credentials/`, storing the access and refresh tokens. Subsequent runs will use this token.

## 4. Phase 2: Code Integration

### 4.1. Create ADK Agent Interaction Service

Create a new module to encapsulate the logic for initializing and interacting with the ADK agent.

**File: `Budget_updater/src/budget_updater/adk_agent_service.py`**
```python
import os
import json
import vertexai
from vertexai.preview import reasoning_engines
from dotenv import load_dotenv

# Import the root_agent from its new location
from .adk_categorizer.agent import root_agent
from . import config as main_config # Budget_updater's main config

# Load environment variables from .env at the project root
load_dotenv(dotenv_path=main_config.Path(main_config.__file__).resolve().parent.parent.parent / ".env")

_adk_app = None
_adk_session = None
_vertex_ai_initialized = False

def init_vertex_ai_for_adk():
    global _vertex_ai_initialized
    if _vertex_ai_initialized:
        return

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or main_config.GOOGLE_CLOUD_PROJECT
    location = os.getenv("GOOGLE_CLOUD_LOCATION") or main_config.GOOGLE_CLOUD_LOCATION
    staging_bucket = os.getenv("GOOGLE_CLOUD_STAGING_BUCKET") # ADK needs this

    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT not set in .env or config.py")
    if not location:
        raise ValueError("GOOGLE_CLOUD_LOCATION not set in .env or config.py")
    if not staging_bucket:
        raise ValueError("GOOGLE_CLOUD_STAGING_BUCKET not set in .env for ADK.")

    vertexai.init(project=project_id, location=location, staging_bucket=staging_bucket)
    _vertex_ai_initialized = True
    print(f"Vertex AI initialized for ADK: project={project_id}, location={location}, staging_bucket={staging_bucket}")


def init_adk_app():
    global _adk_app, _adk_session
    if _adk_app:
        return

    init_vertex_ai_for_adk() # Ensure Vertex AI is initialized

    # The root_agent's instruction (from adk_categorizer.prompt) should now correctly
    # load CATEGORIES_WITH_DESCRIPTIONS from main_config due to prior modifications.
    print("Initializing ADK App...")
    _adk_app = reasoning_engines.AdkApp(
        agent=root_agent,
        enable_tracing=True, # Optional, useful for debugging
    )
    print("Creating ADK session...")
    _adk_session = _adk_app.create_session(user_id="budget_updater_user") # Consistent user_id
    print(f"ADK App and session (ID: {_adk_session.id}) initialized.")


def categorize_transaction_with_adk(date_str: str, amount_str: str, raw_description: str, account_name: str) -> dict:
    if not _adk_app or not _adk_session:
        init_adk_app()

    # The ADK agent's prompt (ROOT_AGENT_INSTRUCTION) expects input describing:
    # Date, Amount, Raw Description, Account
    message = f"Transaction details: Date='{date_str}', Amount='{amount_str}', Raw Description='{raw_description}', Account='{account_name}'"
    
    print(f"Sending message to ADK agent: {message}")
    
    response_texts = []
    final_json_output = None

    try:
        for event in _adk_app.stream_query(
            user_id=_adk_session.user_id,
            session_id=_adk_session.id,
            message=message,
        ):
            # ADK event structure can vary slightly. Common patterns:
            if event.type == "text_delta" and event.data.get("text"):
                response_texts.append(event.data["text"])
            elif event.type == "tool_code" and event.data.get("text"): # Older ADK or tool output preview
                response_texts.append(event.data["text"])
            elif event.type == "final_response" and event.data.get("text"): # Check for final structured output
                final_json_output = event.data["text"]
                break # Found final JSON

        if final_json_output:
            full_response_text = final_json_output
        else:
            full_response_text = "".join(response_texts).strip()

        print(f"Raw ADK response text: {full_response_text}")

        # The ADK agent is instructed to return a JSON object string.
        parsed_json = json.loads(full_response_text)
        return parsed_json

    except json.JSONDecodeError as e:
        print(f"Error decoding ADK agent JSON response: {e}. Raw text: '{full_response_text}'")
        # Fallback or re-raise
        return {
            "category": "ERROR_JSON_DECODE",
            "summary": raw_description,
            "query": "",
            "email_subject": "NO_EMAIL_USED" # Consistent with expected output keys
        }
    except Exception as e:
        print(f"Error during ADK query: {e}")
        return {
            "category": "ERROR_ADK_QUERY",
            "summary": raw_description,
            "query": "",
            "email_subject": "NO_EMAIL_USED"
        }

```

### 4.2. Modify Calling Code (e.g., in `Budget_updater/run.py` or `main.py`)

The part of `Budget_updater` that currently calls `categorizer.categorize_transaction` needs to be updated.
**Assumption:** The `Budget_updater` application iterates through transactions, and for each transaction, it has access to `date`, `amount`, `description` (memo), and `account`.

**Example of changes in the calling code:**

```python
# In Budget_updater/run.py or where categorization is performed

# Remove old import:
# from budget_updater.categorizer import categorize_transaction

# Add new import:
from budget_updater.adk_agent_service import categorize_transaction_with_adk, init_adk_app

# Initialize ADK app once (e.g., at the start of your script/main function)
# init_adk_app() # Call this early if you process multiple transactions

# ...
# Inside your transaction processing loop:
# Assume: transaction_date (str), transaction_amount (str),
#         transaction_memo (str), transaction_account (str) are available.
# ...

# Old call:
# category, new_memo = categorize_transaction(transaction_memo)

# New call:
# Ensure init_adk_app() has been called if not done globally
adk_result = categorize_transaction_with_adk(
    date_str=transaction_date, # Ensure format matches agent expectation (YYYY-MM-DD)
    amount_str=str(transaction_amount), # Ensure it's a string
    raw_description=transaction_memo,
    account_name=transaction_account
)

category = adk_result.get("category", "UNCATEGORIZED")
new_memo = adk_result.get("summary", transaction_memo)
# You can also access adk_result.get("query") and adk_result.get("email_subject")

# ... rest of your processing logic with 'category' and 'new_memo' ...
```

**Important:** The input to `categorize_transaction_with_adk` now requires `date_str`, `amount_str`, `raw_description`, and `account_name`. The previous `categorize_transaction` in `Budget_updater` only took `original_memo`. The data pipeline in `Budget_updater` leading to the categorization step will need to be adjusted to provide these additional fields.

### 4.3. Decommission Old Categorizer

1.  **Delete Old File:** Once the new ADK-based categorizer is integrated and tested, delete the old categorizer file:
    `Budget_updater/src/budget_updater/categorizer.py`
2.  **Clean Up Config:** Remove any configurations from `Budget_updater/src/budget_updater/config.py` that were solely for the old `categorizer.py` and are not used by the new system or other parts of `Budget_updater`.

## 5. Phase 3: Testing and Refinement

### 5.1. Unit and Integration Tests

*   **ADK Agent Service:** Write tests for `adk_agent_service.py`. Mock the `_adk_app.stream_query` to return sample ADK event sequences and verify that `categorize_transaction_with_adk` parses them correctly.
*   **Gmail Tool:** Test the Gmail authentication flow. This will likely be a manual test initially to ensure the OAuth consent screen appears and `token.pickle` is generated.
*   **Categorization Logic:** Prepare a set of test transaction data (date, amount, memo, account) and expected categories/summaries. Run them through the `categorize_transaction_with_adk` function and verify outputs.

### 5.2. End-to-End Testing

*   Run the complete `Budget_updater` application workflow (e.g., execute `run.py`).
*   Process a batch of sample transactions.
*   Verify that categories and memos are generated correctly and that the application handles the new output format.
*   Specifically test transactions that should involve Gmail search and those that shouldn't, to ensure the ADK agent's tool-use logic is working.

### 5.3. Error Handling and Logging

*   Review and enhance error handling in `adk_agent_service.py` and `gmail_tool.py`.
*   Implement comprehensive logging (e.g., using Python's `logging` module) throughout the new `adk_categorizer` components and the `adk_agent_service` to aid in debugging and monitoring. Log raw ADK responses, chosen categories, summaries, and any errors encountered.

## 6. Documentation Updates

*   **README.md:** Update the main `README.md` of the `Budget_updater` project to reflect:
    *   New dependencies (and how to install them).
    *   Updated list of required environment variables.
    *   Instructions for setting up Gmail API OAuth 2.0 credentials (`client_secret.json`).
    *   A note about the first-time OAuth consent flow for Gmail.
*   **Code Comments:** Ensure all new and modified code is well-commented.

## 7. Potential Challenges and Considerations

*   **Input Data Adaptation:** The most significant change in `Budget_updater`'s existing workflow will be providing the `date`, `amount`, and `account` to the categorization function, not just the `memo`.
*   **First-time OAuth Flow for Gmail:** This is an interactive step. If `Budget_updater` is fully automated, this initial manual step needs to be documented clearly for the user setting it up.
*   **ADK Initialization:** The `adk_agent_service.py` attempts to initialize the ADK app once. Depending on how `Budget_updater` is run, ensure this initialization happens correctly and efficiently.
*   **Path and Import Resolution:** Diligently check that all Python imports and file paths (especially for configurations and credentials) are correctly resolved relative to the `Budget_updater` project structure.
*   **Error Propagation:** Ensure errors from the ADK agent or Gmail tool are gracefully handled and propagated or logged appropriately in `Budget_updater`.
*   **ADK Streaming Output:** The `stream_query` method yields events. The example in `adk_agent_service.py` tries to piece together the final JSON. This might need refinement based on the exact structure of events from the ADK version used. Some ADK agent calls might return the full response directly if not streamed. The current implementation aligns with streaming.
*   **Consistency of Output Keys:** The `GCP_BudgetAgent`'s root agent prompt specifies `email_subject` in its final JSON output format. Ensure the `Budget_updater` logic adapts to this key if it was expecting `email_summary` from previous plans.

This plan provides a comprehensive guide for the merge. Adjustments may be needed based on the specific intricacies of the `Budget_updater`'s existing codebase and execution environment. 