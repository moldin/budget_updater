import os
import logging
from typing import Dict, Any
import uuid
import json
import re

from google.cloud import aiplatform
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from budget_updater import config as main_config
from budget_updater.adk_categorizer.agent import root_agent

logger = logging.getLogger(__name__)

def init_vertex_ai_for_adk():
    """
    Initializes Vertex AI with project and location from the main configuration.
    This is a prerequisite for ADK operations that interact with Vertex AI.
    """
    try:
        aiplatform.init(
            project=main_config.GOOGLE_CLOUD_PROJECT,
            location=main_config.GOOGLE_CLOUD_LOCATION,
            staging_bucket=os.getenv("GOOGLE_CLOUD_STAGING_BUCKET") # Get from .env
        )
        logger.info(
            f"Vertex AI initialized for ADK. Project: {main_config.GOOGLE_CLOUD_PROJECT}, "
            f"Location: {main_config.GOOGLE_CLOUD_LOCATION}, "
            f"Staging Bucket: {os.getenv('GOOGLE_CLOUD_STAGING_BUCKET')}"
        )
    except Exception as e:
        logger.error(f"Error initializing Vertex AI for ADK: {e}", exc_info=True)
        raise

def create_adk_runner_and_service(
    runner_app_name: str = "budget_categorizer_runner"
) -> tuple[Runner, InMemorySessionService]:
    """
    Initializes and returns an ADK Runner and an InMemorySessionService.
    Ensures Vertex AI is initialized first.

    Args:
        runner_app_name: An identifier for the runner's application context.

    Returns:
        A tuple containing the initialized ADK Runner and InMemorySessionService.
    """
    logger.info(f"Initializing ADK Runner and Session Service with app_name: {runner_app_name}")
    init_vertex_ai_for_adk() # Ensure Vertex AI is set up

    try:
        session_service = InMemorySessionService()
        # root_agent is imported from budget_updater.adk_categorizer.agent
        runner = Runner(
            agent=root_agent,
            app_name=runner_app_name,
            session_service=session_service
        )
        logger.info(f"ADK Runner created for agent '{root_agent.name}' and app_name '{runner_app_name}'. Session service initialized.")
        return runner, session_service
    except Exception as e:
        logger.error(f"Error creating ADK Runner for app_name '{runner_app_name}': {e}", exc_info=True)
        raise

def categorize_transaction_with_adk(
    runner: Runner,
    session_service: InMemorySessionService,
    date_str: str,
    amount_str: str,
    raw_description: str,
    account_name: str
) -> Dict[str, Any]:
    """
    Categorizes a single transaction using the initialized ADK Runner and SessionService.

    Args:
        runner: The initialized ADK Runner.
        session_service: The initialized ADK InMemorySessionService.
        date_str: Transaction date in YYYY-MM-DD string format.
        amount_str: Transaction amount as a string.
        raw_description: The raw transaction description from the bank.
        account_name: The name of the account where the transaction occurred.

    Returns:
        A dictionary containing the 'category', 'summary', 'query', and 'email_summary'.
        Returns a default error structure if categorization fails.
    """
    input_query = (
        f"Categorize this transaction:\n"
        f"Date: {date_str}\n"
        f"Amount: {amount_str}\n"
        f"Description: {raw_description}\n"
        f"Account: {account_name}"
    )
    logger.info(f"Attempting to categorize transaction with ADK Runner. Input query: \n{input_query}")

    user_id = "budget_updater_user" # Static user ID for stateless calls
    session_id = str(uuid.uuid4()) # New session ID for each call for isolation

    try:
        # Create a temporary session for this specific run.
        session_service.create_session(
            app_name=runner.app_name, # Use app_name from the runner instance
            user_id=user_id,
            session_id=session_id,
            state={} # Empty state for stateless operation
        )
        logger.debug(f"Temporary session created for ADK run: app='{runner.app_name}', user='{user_id}', session='{session_id}'")

        message_content = genai_types.Content(
            role="user", parts=[genai_types.Part(text=input_query)]
        )
        
        final_response_output = None
        run_error_message = None
        # raw_output_text = None # No longer needed here, will be assigned in loop

        for event in runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=message_content,
        ):
            # More detailed logging of the event structure
            logger.debug(f"ADK Runner Event: Type='{event.type if hasattr(event, 'type') else 'N/A'}', "
                         f"Data='{event.data if hasattr(event, 'data') else 'N/A'}', "
                         f"Content='{event.content if hasattr(event, 'content') else 'N/A'}', "
                         f"IsError='{event.is_error() if hasattr(event, 'is_error') else 'N/A'}', "
                         f"IsFinalResponse='{event.is_final_response() if hasattr(event, 'is_final_response') else 'N/A'}'")

            if event.is_final_response():
                raw_output_text_from_event = None
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, 'text'): # Check if it's a TextPart or similar
                            raw_output_text_from_event = part.text
                            logger.debug(f"Extracted text part from final response: {raw_output_text_from_event}")
                            break # Take the first text part
                
                if raw_output_text_from_event:
                    logger.info(f"Final raw output text from LLM (raw): {raw_output_text_from_event}")
                    logger.debug(f"Representation of raw_output_text_from_event: {repr(raw_output_text_from_event)}")
                    
                    text_to_process_further = raw_output_text_from_event.strip()
                    logger.debug(f"text_to_process_further (after strip): {text_to_process_further}")
                    logger.debug(f"Representation of text_to_process_further: {repr(text_to_process_further)}")

                    text_to_parse = None
                    # General regex to capture content between ```json ... ``` or ``` ... ```
                    regex_pattern = r"```(?:json)?\s*([\s\S]+?)\s*```"
                    logger.debug(f"Attempting regex pattern: {regex_pattern} on text: {repr(text_to_process_further)}")
                    match = re.search(regex_pattern, text_to_process_further, re.IGNORECASE | re.DOTALL)

                    if match:
                        logger.debug(f"Regex matched. Number of groups: {len(match.groups())}")
                        if len(match.groups()) > 0:
                            captured_group_raw = match.group(1)
                            logger.debug(f"Regex match.group(1) (raw): {repr(captured_group_raw)}")
                            potential_json_text = captured_group_raw.strip()
                            logger.debug(f"Potential JSON text after strip (from group 1): {repr(potential_json_text)}")
                            
                            if potential_json_text.startswith("{") and potential_json_text.endswith("}"):
                                text_to_parse = potential_json_text
                                logger.info(f"Extracted and validated JSON from Markdown: '{text_to_parse}'")
                            else:
                                logger.warning(f"Content within Markdown (group 1 stripped) does not appear to be a JSON object. Starts with '{potential_json_text[0] if potential_json_text else ''}' ends with '{potential_json_text[-1] if potential_json_text else ''}'. Content: '{repr(potential_json_text)}'. Original raw: '{raw_output_text_from_event}'")
                        else:
                            logger.warning("Regex matched but found no capturing groups.")
                    else:
                        logger.warning(f"Regex did NOT match. Falling back to direct JSON check.")
                        if text_to_process_further.startswith("{") and text_to_process_further.endswith("}"):
                            text_to_parse = text_to_process_further
                            logger.info(f"No Markdown detected, but raw output appears to be JSON. Will attempt to parse as is: '{text_to_parse}'")
                        else:
                            logger.warning(f"No Markdown detected and raw output does not appear to be JSON. Content (repr): {repr(text_to_process_further)} - '{text_to_process_further}'")

                    if text_to_parse:
                        try:
                            final_response_output = json.loads(text_to_parse)
                            logger.debug(f"Successfully parsed JSON: {final_response_output}")
                        except json.JSONDecodeError as e_json:
                            logger.error(f"Failed to parse extracted/raw text as JSON. Text attempted: '{text_to_parse}'. Original raw: '{raw_output_text_from_event}'. Error: {e_json}")
                            return {
                                "category": "MANUAL REVIEW (ADK JSON Error)", 
                                "summary": f"Agent output parsing error (JSONDecodeError): {e_json}. Attempted to parse: '{text_to_parse}'",
                                "query": "N/A (JSON parsing failed)",
                                "email_summary": "N/A (JSON parsing failed)"
                            }
                    else: # text_to_parse is None (either no markdown/JSON structure, or markdown content wasn't JSON)
                        # Ensure raw_output_text_from_event is used in the log for consistency with previous error messages
                        logger.error(f"ADK agent execution failed. No valid JSON structure found in agent response. Raw content: {raw_output_text_from_event if raw_output_text_from_event else 'N/A'}")
                        return {
                            "category": "MANUAL REVIEW (ADK Format Error)", 
                            "summary": f"Agent returned non-JSON or malformed response: {raw_output_text_from_event if raw_output_text_from_event else 'N/A'}",
                            "query": "N/A (Formatting error)",
                            "email_summary": "N/A (Formatting error)"
                        }
                else:
                    logger.warning("ADK final response event has content/parts, but no processable text part found.")
                    run_error_message = "Final response has no usable text content"
                break 

            elif hasattr(event, 'is_error') and event.is_error():
                run_error_message = getattr(event, 'message', getattr(event, 'error_message', str(event.data if hasattr(event, 'data') else 'Unknown error data')))
                logger.error(f"ADK runner event indicated an error: {run_error_message}")
                break
            elif hasattr(event, 'type') and isinstance(event.type, str) and "ERROR" in event.type.upper():
                 run_error_message = getattr(event, 'message', str(event.data if hasattr(event, 'data') else 'Unknown error data (type based)'))
                 logger.error(f"ADK runner event (type based) indicated an error: {run_error_message}")
                 break

        if final_response_output:
            required_keys = ["category", "summary", "query", "email_summary"]
            if not all(key in final_response_output for key in required_keys):
                logger.error(f"ADK agent response missing one or more required keys: {required_keys}. Parsed Output: {final_response_output}")
                return {
                    "category": "MANUAL REVIEW (Missing Keys)", 
                    "summary": f"Agent output (parsed but missing keys): {final_response_output}",
                    "query": final_response_output.get("query", "N/A (missing from parsed output)"),
                    "email_summary": final_response_output.get("email_summary", "N/A (missing from parsed output)")
                }
            logger.info(f"Successfully categorized transaction via Runner. Category: {final_response_output.get('category')}, Summary: {final_response_output.get('summary')}")
            return final_response_output
        
        elif run_error_message:
            logger.error(f"ADK agent execution failed. Error: {run_error_message}")
            # run_error_message already contains details including raw agent output if parsing failed
            return {
                "category": "MANUAL REVIEW (Agent Error)", 
                "summary": run_error_message if run_error_message else "Unknown agent error", 
                "query": "N/A (due to agent error)",
                "email_summary": "N/A (due to agent error)"
            }
        else: 
            logger.error("ADK agent execution failed: No final response and no specific error event caught.")
            return {
                "category": "MANUAL REVIEW (Unknown Agent Failure)",
                "summary": "Unknown error or no output from ADK agent execution.",
                "query": "N/A (due to unknown agent failure)",
                "email_summary": "N/A (due to unknown agent failure)"
            }

    except Exception as e:
        logger.error(f"Exception during ADK categorization with Runner: {e}", exc_info=True)
        return {
            "category": "MANUAL REVIEW (Service Exception)",
            "summary": f"Service exception: {str(e)}",
            "query": "N/A (due to service exception)",
            "email_summary": "N/A (due to service exception)"
        }
    finally:
        # Ensure the temporary session is deleted
        try:
            session_service.delete_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)
            logger.debug(f"Temporary session deleted: app='{runner.app_name}', user='{user_id}', session='{session_id}'")
        except Exception as e_del:
            # Log if deletion fails, but don't let it hide the primary error (if any)
            logger.warning(f"Failed to delete temporary session {session_id}: {e_del}", exc_info=True)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("Starting ADK Agent Service local test (with Runner)...")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    try:
        init_vertex_ai_for_adk()
    except Exception as e:
        logger.error(f"Failed to initialize Vertex AI for ADK in test: {e}", exc_info=True)
        exit(1)

    adk_runner = None
    adk_session_service = None
    try:
        # Using a distinct app_name for the test runner context
        adk_runner, adk_session_service = create_adk_runner_and_service(runner_app_name="test_categorizer_runner_local")
        if not adk_runner or not adk_session_service:
            raise ValueError("ADK Runner or SessionService initialization returned None.")
    except Exception as e:
        logger.error(f"Failed to create ADK Runner and Session Service in test: {e}", exc_info=True)
        exit(1)

    logger.info("Testing transaction categorization with Runner...")
    test_transactions = [
        {
            "date_str": "2025-03-11", 
            "amount_str": "−256", 
            "raw_description": "K*BOKUS.COM", 
            "account_name": "SEB"
        },
        {
            "date_str": "2025-04-15", 
            "amount_str": "124,83", 
            "raw_description": "APOTEK HJARTAT MALL OF", 
            "account_name": "Strawberry"
        },
        {
            "date_str": "230909", 
            "amount_str": "400,74", 
            "raw_description": "Kindle Svcs*TR6377370", 
            "account_name": "First Card"
        }
    ]

    for i, tx in enumerate(test_transactions):
        logger.info(f"--- Test Transaction {i+1} (Runner) ---")
        try:
            result = categorize_transaction_with_adk(
                runner=adk_runner,
                session_service=adk_session_service,
                date_str=tx["date_str"],
                amount_str=tx["amount_str"],
                raw_description=tx["raw_description"],
                account_name=tx["account_name"]
            )
            logger.info(f"Categorization result for TX {i+1}: {result}")
            if result.get("category", "").startswith("MANUAL REVIEW"):
                logger.warning(f"TX {i+1} resulted in MANUAL REVIEW.")
        except Exception as e:
            logger.error(f"Error during test transaction {i+1} categorization: {e}", exc_info=True)

    logger.info("ADK Agent Service local test (with Runner) finished.") 