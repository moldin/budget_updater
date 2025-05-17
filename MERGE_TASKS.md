# MERGE_TASKS.md: Step-by-Step Integration of ADK Categorizer

This document outlines the specific tasks to integrate the ADK-based transaction categorizer into the `Budget_updater` project.

## Legend
*   `[ ]` - Task To Do
*   `[x]` - Task Completed
*   **(AI)** - Task to be performed by the AI assistant
*   **(USER)** - Task to be performed by the User

## Iteration 1: Initial Setup (Dependencies, Env Vars, Directories & Files)

*   [x] **(AI)** Identify dependency file in `Budget_updater` (e.g., `requirements.txt` or `pyproject.toml`).
*   [x] **(AI)** Add ADK-related dependencies to the identified file as specified in `MERGE_PLAN.md` (Section 3.1).
*   [x] **(USER)** Review the dependency changes.
*   [x] **(USER)** Install the updated dependencies (e.g., `uv sync`).
*   [x] **(USER)** Create or update the `.env` file in the `Budget_updater` root directory with:
    *   `GOOGLE_CLOUD_PROJECT = "aspiro-budget-analysis"`
    *   `GOOGLE_CLOUD_LOCATION = "us-central1"`
    *   `GOOGLE_GENAI_USE_VERTEXAI=1`
*   [x] **(AI)** Create directory: `Budget_updater/src/budget_updater/adk_categorizer`
*   [x] **(AI)** Verify directory creation by listing contents of `Budget_updater/src/budget_updater/`.
*   [x] **(AI)** Copy ADK agent files:
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/__init__.py` to `Budget_updater/src/budget_updater/adk_categorizer/__init__.py`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/agent.py` to `Budget_updater/src/budget_updater/adk_categorizer/agent.py`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/config.py` to `Budget_updater/src/budget_updater/adk_categorizer/config.py` (this will be modified/deleted later)
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/prompt.py` to `Budget_updater/src/budget_updater/adk_categorizer/prompt.py`
    *   [x] Create directory: `Budget_updater/src/budget_updater/adk_categorizer/sub_agents`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/sub_agents/__init__.py` to `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/__init__.py`
    *   [x] Create directory: `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/sub_agents/gmail_agent/__init__.py` to `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/__init__.py`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/sub_agents/gmail_agent/agent.py` to `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/agent.py`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/sub_agents/gmail_agent/config.py` to `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/config.py` (this will be modified/deleted later)
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/sub_agents/gmail_agent/gmail_tool.py` to `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/gmail_tool.py`
    *   [x] Copy `GCP_BudgetAgent/gcp_budget_agent/transaction_categorizer/sub_agents/gmail_agent/prompt.py` to `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/prompt.py`
*   [x] **(AI)** Verify copied files by listing contents of `Budget_updater/src/budget_updater/adk_categorizer/` and its subdirectories.
*   [x] **(AI)** Create directory: `Budget_updater/credentials`
*   [x] **(AI)** Verify directory creation by listing contents of `Budget_updater/`.
*   [x] **(USER)** Download your OAuth 2.0 `client_secret.json` file from the Google Cloud Console and place it into `Budget_updater/credentials/client_secret.json`.
*   [x] **(AI)** Add `__init__.py` files if they were not part of the copy and are missing:
    *   [x] `Budget_updater/src/budget_updater/adk_categorizer/__init__.py` (should exist from copy)
    *   [x] `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/__init__.py` (should exist from copy)
    *   [x] `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/__init__.py` (should exist from copy)
*   [x] **(AI)** Verify `__init__.py` files are present.
*   [x] **(AI)** Update this `MERGE_TASKS.md` with completed tasks for Iteration 1.

## Iteration 2: Configuration Consolidation (Main Config File)

*   [x] **(AI)** Modify `Budget_updater/src/budget_updater/config.py` as per `MERGE_PLAN.md` (Section 3.4.2):
    *   [x] Add `from pathlib import Path`.
    *   [x] Add `GEMINI_MODEL_ID`.
    *   [x] Add `CREDENTIALS_DIR`, `CLIENT_SECRET_FILENAME`, `TOKEN_PICKLE_FILENAME`.
    *   [x] Add `CLIENT_SECRET_FILE_PATH`, `TOKEN_PICKLE_FILE_PATH`.
    *   [x] Ensure `CATEGORIES_WITH_DESCRIPTIONS` is present and correctly defined.
    *   [x] Remove any configurations specific to the old `categorizer.py` if clearly identifiable.
*   [x] **(AI)** Read `Budget_updater/src/budget_updater/config.py` to check for syntax and structure.
*   [x] **(AI)** Update this `MERGE_TASKS.md` with completed tasks for Iteration 2.

## Iteration 3: Configuration Consolidation (ADK Categorizer Module Configs)

*   [x] **(AI)** Modify `Budget_updater/src/budget_updater/adk_categorizer/prompt.py` as per `MERGE_PLAN.md` (Section 3.4.3):
    *   [x] Add `from budget_updater import config as main_budget_config`.
    *   [x] Update `ROOT_AGENT_INSTRUCTION` to use `main_budget_config.CATEGORIES_WITH_DESCRIPTIONS`.
*   [x] **(AI)** Read `Budget_updater/src/budget_updater/adk_categorizer/prompt.py` to check changes.
*   [x] **(AI)** Modify `Budget_updater/src/budget_updater/adk_categorizer/agent.py` as per `MERGE_PLAN.md` (Section 3.4.4):
    *   [x] Change `from .config import GEMINI_MODEL_ID` to `from budget_updater.config import GEMINI_MODEL_ID`.
*   [x] **(AI)** Read `Budget_updater/src/budget_updater/adk_categorizer/agent.py` to check changes.
*   [x] **(AI)** Modify `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/agent.py` as per `MERGE_PLAN.md` (Section 3.4.4):
    *   [x] Change `from .config import GEMINI_MODEL_ID` to `from budget_updater.config import GEMINI_MODEL_ID`.
*   [x] **(AI)** Read `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/agent.py` to check changes.
*   [x] **(AI)** Modify `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/gmail_tool.py` as per `MERGE_PLAN.md` (Section 3.4.5):
    *   [x] Add `from budget_updater import config as main_budget_config`.
    *   [x] Add `from pathlib import Path` and `import os` if not present.
    *   [x] Replace old credential path definitions with new ones using `main_budget_config`.
    *   [x] Update `os.makedirs` path to use `main_budget_config.CREDENTIALS_DIR`.
*   [x] **(AI)** Read `Budget_updater/src/budget_updater/adk_categorizer/sub_agents/gmail_agent/gmail_tool.py` to check changes.
*   [x] **(AI)** Update this `MERGE_TASKS.md` with completed tasks for Iteration 3.

## Iteration 4: ADK Agent Service Implementation

*   [x] **(AI)** Create and implement `Budget_updater/src/budget_updater/adk_agent_service.py` as detailed in `MERGE_PLAN.md` (Section 4.1).
    *   [x] Implement `init_vertex_ai_for_adk()`.
    *   [x] Implement `init_adk_app()`.
    *   [x] Implement `categorize_transaction_with_adk()`.
*   [x] **(AI)** Read `Budget_updater/src/budget_updater/adk_agent_service.py` to check structure and syntax.
*   [x] **(AI)** Update this `MERGE_TASKS.md` with completed tasks for Iteration 4.

## Iteration 5: Code Integration in Main Application

*   [ ] **(AI)** Identify the main calling script in `Budget_updater` (e.g., `run.py` or `main.py`). (Assume `run.py` for now, USER to confirm if different).
*   [ ] **(AI)** Read the identified script to understand current usage of the old categorizer.
*   [ ] **(AI)** Modify the identified script (`run.py` or other) as per `MERGE_PLAN.md` (Section 4.2):
    *   Remove old categorizer import.
    *   Add new `adk_agent_service` imports.
    *   Add call to `