import os
import pickle
import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import BaseModel, Field

from budget_updater import config as main_budget_config  # Paths to creds

logger = logging.getLogger(__name__)


# --- Define Output Schema ---
class EmailContent(BaseModel):
    date: str = Field(
        description="The date of the email. Format: YYYY-MM-DD"
    )
    amount: str = Field(
        description="The amount of money spent. Format: 1234,56"
    )
    company: str = Field(
        description="The company that sold the product. Exactly as it is in the original email."
    )
    summary: str = Field(
        description="A description of what was purchased. A summary of the purchase."
    )
    payment_details: str = Field(
        description="The payment details of the purchase. E.g. 'Nordea', 'SEB', 'PayPal', 'FirstCard', 'Revolut', 'Strawberry', 'MasterCard ****6442', 'Apple Pay', 'Unknown'"
    )


@dataclass
class EmailResult:
    """Internal representation of an extracted email."""

    date: str
    amount: str
    company: str
    summary: str
    payment_details: str
    raw_subject: Optional[str] = None
    raw_from: Optional[str] = None
    raw_body_text: Optional[str] = None


def _print_debug_email(email: EmailResult, index: int) -> None:
    """Pretty print the fetched email for debugging purposes."""
    separator = "-" * 40
    print(f"\n{separator}\nEmail {index}\n{separator}")
    print(f"Date: {email.date}")
    if email.raw_from:
        print(f"From: {email.raw_from}")
    if email.raw_subject:
        print(f"Subject: {email.raw_subject}")
    if email.raw_body_text:
        #print(email.raw_body_text)
        pass
    print(separator)

# --- Gmail API Configuration ---
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly'] # Read-only access

# Use paths from the main budget_updater config
CREDENTIALS_DIR = main_budget_config.CREDENTIALS_DIR 
CLIENT_SECRET_FILE = main_budget_config.CLIENT_SECRET_FILE_PATH
TOKEN_PICKLE_FILE = main_budget_config.TOKEN_PICKLE_FILE_PATH


def get_gmail_service():
    """Authenticate and build a Gmail service client."""
    creds = None
    if TOKEN_PICKLE_FILE.exists():
        with open(TOKEN_PICKLE_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.debug("Refreshing Gmail credentials")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"OAuth client secret file not found at {CLIENT_SECRET_FILE}."
                )
            logger.info("Running Gmail OAuth flow")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(CREDENTIALS_DIR, exist_ok=True)
        with open(TOKEN_PICKLE_FILE, "wb") as token:
            pickle.dump(creds, token)

    try:
        service = build("gmail", "v1", credentials=creds)
        logger.debug("Gmail service built successfully")
        return service
    except HttpError as error:
        logger.error("Failed to build Gmail service: %s", error)
        return None

def get_email_details(service, user_id, msg_id):
    """Retrieve detailed information for a single email."""
    try:
        message = service.users().messages().get(userId=user_id, id=msg_id, format='full').execute()
        payload = message['payload']
        headers = payload['headers']
        
        email_data = {
            'subject': None,
            'from': None,
            'date': None,
            'body_text': None,
            'body_html': None,
            'snippet': message.get('snippet')
        }

        for header in headers:
            if header['name'] == 'Subject':
                email_data['subject'] = header['value']
            if header['name'] == 'From':
                email_data['from'] = header['value']
            if header['name'] == 'Date':
                # Parse date and format to YYYY-MM-DD
                date_str = header['value']
                try:
                    # Example date format: Tue, 2 Apr 2024 08:30:00 +0200 (CEST)
                    # Handle various potential date formats if necessary
                    dt_object = datetime.strptime(date_str.split(' (')[0].strip(), '%a, %d %b %Y %H:%M:%S %z')
                    email_data['date'] = dt_object.strftime('%Y-%m-%d')
                except ValueError:
                     try: # Fallback for dates like "2 Apr 2024 08:30:00 +0200"
                         dt_object = datetime.strptime(date_str.strip(), '%d %b %Y %H:%M:%S %z')
                         email_data['date'] = dt_object.strftime('%Y-%m-%d')
                     except ValueError:
                        email_data['date'] = date_str # Keep original if parsing fails


        def get_part_data(part):
            """Recursively extract text and html from parts."""
            body_text = ""
            body_html = ""
            if part.get('body') and part['body'].get('data'):
                data = part['body']['data']
                decoded_data = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                if part['mimeType'] == 'text/plain':
                    body_text += decoded_data
                elif part['mimeType'] == 'text/html':
                    body_html += decoded_data
            
            if 'parts' in part:
                for sub_part in part['parts']:
                    text, html = get_part_data(sub_part)
                    body_text += text
                    body_html += html
            return body_text, body_html

        email_data['body_text'], email_data['body_html'] = get_part_data(payload)
        
        # Fallback: if body_text is empty but body_html is not, try to convert html to text
        if not email_data['body_text'] and email_data['body_html']:
            soup = BeautifulSoup(email_data['body_html'], 'html.parser')
            email_data['body_text'] = soup.get_text(separator='\n', strip=True)

        return email_data
    except HttpError as error:
        logger.error("Error fetching email details: %s", error)
        return None


def query_gmail_emails_structured(
    query: str,
    after_date: Optional[str] = None,  # YYYY-MM-DD
    before_date: Optional[str] = None,  # YYYY-MM-DD
    max_results: int = 15,
    *,
    debug: bool = False,
) -> List[dict]:
    """
    Searches Gmail for emails based on a query and date range, then extracts structured content.
    This tool is designed to be called by an ADK agent.

    Args:
        query: The search query string (e.g., "Invoice from Acme Corp").
        after_date: Optional. Search for emails received after this date (YYYY-MM-DD).
        before_date: Optional. Search for emails received before this date (YYYY-MM-DD).
        max_results: The maximum number of emails to return.
        debug: If True, print each fetched email to stdout for debugging.

    Returns:
        A list of dictionaries, where each dictionary contains the extracted content
        of an email matching the query. Returns an empty list if no matches or an error occurs.
    """
    print(f"=========== TOOL CALL: Querying Gmail for: Max results: {max_results} Query: {query} ===========")
    service = get_gmail_service()
    if not service:
        return {"status": "error", "message": "Failed to connect to Gmail service."}

    search_query = query
    if after_date:
        search_query += f" after:{after_date.replace('-', '/')}"
    if before_date:
        search_query += f" before:{before_date.replace('-', '/')}"

    logger.debug("Gmail search query: %s", search_query)

    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=search_query, maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])

        extracted_emails: List[EmailResult] = []
        if not messages:
            logger.debug("No emails found")
            return {"status": "success", "emails": []}

        logger.debug("Found %d email(s)", len(messages))
        for idx, msg_metadata in enumerate(messages, start=1):
            msg_id = msg_metadata["id"]
            email_content = get_email_details(service, "me", msg_id)
            if not email_content:
                continue
            email = EmailResult(
                date=email_content.get("date", "Unknown Date"),
                amount="0,00",  # TODO: parse amount
                company="Unknown Company",  # TODO: parse company
                summary=email_content.get("snippet", "No snippet available."),
                payment_details="Unknown",
                raw_subject=email_content.get("subject"),
                raw_from=email_content.get("from"),
                raw_body_text=email_content.get("body_text")[:1000],
            )
            extracted_emails.append(email)
            if debug:
                _print_debug_email(email, idx)

        return {"status": "success", "emails": [e.__dict__ for e in extracted_emails]}

    except HttpError as error:
        logger.error("Gmail API error: %s", error)
        return {"status": "error", "message": f"Gmail API error: {error}"}
    except Exception as e:
        logger.exception("Unexpected error during Gmail search")
        return {"status": "error", "message": f"Unexpected error: {e}"}


def main() -> None:
    """Simple manual test harness for the Gmail tool."""
    if not CREDENTIALS_DIR.exists():
        os.makedirs(CREDENTIALS_DIR)
        print(
            f"Created dummy '{CREDENTIALS_DIR}' for local testing if you haven't set up OAuth yet."
        )
        print(f"Make sure '{CLIENT_SECRET_FILE.name}' is in '{CREDENTIALS_DIR}'.")

    # Test Case 1: Basic search
    print("\n--- Test Case 1: Basic Search (No Dates) ---")
    test_query_1 = "Google Cloud"
    query_gmail_emails_structured(query=test_query_1, max_results=2, debug=True)

    # Test Case 2: Search with dates
    print("\n--- Test Case 2: Search with Dates ---")
    test_query_2 = "Netflix"
    after = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    before = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    query_gmail_emails_structured(
        query=test_query_2,
        after_date=after,
        before_date=before,
        max_results=1,
        debug=True,
    )

    # Test Case 3: No results expected (adjust query if needed)
    print("\n--- Test Case 3: No Results Expected ---")
    test_query_3 = "kjsdhfkjsdhfkjhsdfkjhsdkfjh"  # gibberish
    query_gmail_emails_structured(query=test_query_3, max_results=1, debug=True)

    print("\nNOTE: If you see OAuth errors or prompts, you need to:")
    print(
        f"1. Ensure '{main_budget_config.CLIENT_SECRET_FILENAME}' is in the '{main_budget_config.CREDENTIALS_DIR}' directory."
    )
    print(
        f"2. Run the script once to go through the OAuth flow. '{main_budget_config.TOKEN_PICKLE_FILENAME}' will be created."
    )
    print(
        "   The script might try to open a browser window for authentication."
    )


if __name__ == "__main__":
    main()
