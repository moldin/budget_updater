import logging
import os
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from . import config # Import config

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Use module-specific logger

# Initialize Vertex AI using config constants
PROJECT_ID_INITIALIZED = False # Flag for successful init
try:
    # Check for application credentials first - this is mandatory
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
         logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set. Vertex AI initialization skipped.")
    elif not config.GOOGLE_CLOUD_PROJECT: # Check if project ID is available (should always be now)
         logger.error("GOOGLE_CLOUD_PROJECT is missing in configuration. Vertex AI initialization skipped.")
    else:
        # Use project and location from config (which includes defaults from PRD)
        vertexai.init(project=config.GOOGLE_CLOUD_PROJECT, location=config.GOOGLE_CLOUD_LOCATION)
        logger.info(f"Vertex AI initialized successfully for project {config.GOOGLE_CLOUD_PROJECT} in {config.GOOGLE_CLOUD_LOCATION}")
        PROJECT_ID_INITIALIZED = True
except Exception as e:
    logger.error(f"Failed to initialize Vertex AI: {e}", exc_info=True)
    # PROJECT_ID_INITIALIZED remains False

def build_prompt(memo: str) -> str:
    """Builds the prompt for the Gemini model to get category and cleaned memo."""
    prompt = f"""
    You are an expert budget categorizer and summarizer. Based ONLY on the Transaction Memo provided, perform the following two tasks:

    1.  **Categorize:** Choose the single BEST category from the list below.
    2.  **Summarize:** Create a concise, readable summary (3-5 words max) of the transaction based on the memo. 
        - Focus on the merchant or purpose. If the memo is already concise, you can reuse it. 
        - If the memo is a phonenumber (e.g. 4673334454), then categorize it as "SWISH Payment - REVIEW", 
        - If the memo is unclear prefix the original memo with "REVIEW: "

    **Available Categories and Descriptions:**
    {config.CATEGORIES_WITH_DESCRIPTIONS}

    **Important Rules:**
    1.  Analyze the 'Transaction Memo'.
    2.  For categorization, select the *single most appropriate* category from the list based on the memo and descriptions. NEVER choose '➡️ Starting Balance' or '🔢 Balance Adjustment'. If unsure, use "UNCATEGORIZED".
    3.  For summarization, create a short, clean memo as described above.
    4.  Output ONLY a valid JSON object containing two keys: "category" and "memo". Example: {{"category": "Mat och hushåll", "memo": "ICA Grocery"}}

    **Transaction Memo:**
    {memo}

    **JSON Output:**
    """
    return prompt

def categorize_transaction(original_memo: str) -> tuple[str, str]:
    """
    Categorizes a transaction and generates a clean memo using the Gemini model.

    Args:
        original_memo: The original transaction description (MEMO field).

    Returns:
        A tuple containing:
            - The determined category name (string, "UNCATEGORIZED" on failure).
            - The cleaned/generated memo (string, falls back to original_memo on failure).
    """
    fallback_category = "UNCATEGORIZED"
    # Use original memo as fallback if generation fails or memo is empty
    fallback_memo = original_memo if original_memo else ""

    if not original_memo: # Handle empty input memo
         logger.warning("Original memo is empty. Returning UNCATEGORIZED and empty memo.")
         return fallback_category, fallback_memo

    if not PROJECT_ID_INITIALIZED:
        logger.warning("Vertex AI not initialized. Skipping categorization.")
        return fallback_category, fallback_memo

    model_id = config.GEMINI_MODEL_ID
    logger.debug(f"Categorizing and summarizing memo: '{original_memo}' using model {model_id}")

    try:
        prompt = build_prompt(original_memo)
        model = GenerativeModel(model_id)
        response = model.generate_content(
            [Part.from_text(prompt)],
            generation_config={
                "max_output_tokens": 150, # Increased slightly for JSON + content
                "temperature": 0.2, # Keep low temp for consistency
                "top_p": 0.95,
                "response_mime_type": "application/json", # Request JSON output
            }
        )

        logger.debug(f"Raw AI response for memo '{original_memo}': {response.text}")

        # Parse the JSON response
        try:
            result_json = json.loads(response.text)
            ai_category = result_json.get("category")
            ai_memo = result_json.get("memo")

            # Validate response structure
            if not ai_category or not isinstance(ai_category, str):
                logger.warning(f"AI response missing or invalid 'category' for memo '{original_memo}'. Response: {response.text}")
                return fallback_category, fallback_memo # Fallback category, original memo

            if not ai_memo or not isinstance(ai_memo, str):
                logger.warning(f"AI response missing or invalid 'memo' for memo '{original_memo}'. Response: {response.text}. Using original memo.")
                ai_memo = fallback_memo # Use original memo if AI memo is bad

            # Validate category content
            if ai_category in ['➡️ Starting Balance', '🔢 Balance Adjustment']:
                 logger.warning(f"AI returned a forbidden category ('{ai_category}') for memo: '{original_memo}'. Falling back to UNCATEGORIZED.")
                 ai_category = fallback_category # Use fallback category

            # Optional: Add check against actual categories list from BackendData if loaded

            logger.debug(f"Memo: '{original_memo}' -> Category: '{ai_category}', New Memo: '{ai_memo}'")
            return ai_category, ai_memo.strip() # Return stripped memo

        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to decode JSON response for memo '{original_memo}': {json_err}. Response text: {response.text}")
            return fallback_category, fallback_memo
        except Exception as parse_err: # Catch other potential errors during parsing/validation
             logger.error(f"Error processing AI response for memo '{original_memo}': {parse_err}. Response text: {response.text}", exc_info=True)
             return fallback_category, fallback_memo


    except Exception as e:
        logger.error(f"Error during Gemini API call for memo '{original_memo}': {e}", exc_info=True)
        return fallback_category, fallback_memo

# Example usage (for testing)
if __name__ == '__main__':
    # Ensure necessary environment variables are set for testing
    # export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/keyfile.json"
    # export GOOGLE_CLOUD_PROJECT="your-gcp-project-id" # Not strictly needed if using default
    # export GOOGLE_CLOUD_LOCATION="europe-west1"
    # export GEMINI_MODEL_ID="gemini-1.5-flash-001"

    test_memos = [
        "ICA MAXI LINDHAGEN",
        "Spotify AB",
        "Netflix",
        "TRANSFER REF 12345",
        "Convini",
        "Hemfrid AB",
        "OKQ8",
        "BETALNING AV FAKTURA VIA BG",
        "Apple.com/bill",
        "Adobe Creative Cloud",
        "LÖN",
        "Payment via Swish to EMMA MOBIL",
        "46733497676", # Example unclear memo
        "Bahnhof AB"
    ]

    if PROJECT_ID_INITIALIZED:
        for m in test_memos:
            cat, new_memo = categorize_transaction(m)
            print(f"Original: '{m}' -> Category: '{cat}', Memo: '{new_memo}'")
    else:
        print("Skipping example usage as Vertex AI is not initialized (check GOOGLE_APPLICATION_CREDENTIALS env var).") 