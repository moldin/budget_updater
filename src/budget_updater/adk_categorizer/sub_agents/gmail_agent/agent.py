from google.adk.agents import Agent
from budget_updater.config import GEMINI_MODEL_ID
from .gmail_tool import query_gmail_emails_structured
from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

query_gmail_tool = FunctionTool(func=query_gmail_emails_structured)
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

gmail_agent = Agent(
    name="gmail_agent",
    model=GEMINI_MODEL_ID,
    description="A helpful assistant that searches for emails related to personal financial transactions.",
    instruction="""
    You are a helpful assistant that searches for emails related to personal financial transactions.
    You will be given a a query from the user. The query will consist of a date and an amount for a purchase.
    The user's query will also include a note about the purchase as it is written by a credit/debit card company.
    This note is not always very instructive but you will use it as a guide to find the correct email.

    **INSTRUCTIONS**:
    1. Create a query to search for gmail.
    2. Be smart to take only the parts from the "note" that seem like good search criteria. E.g.:
        - The note: "ICA NARA JAR/25-03-20" you would only take "ICA" "ICA NARA JAR" as the search criteria 
        - The note: "BRÖD & SALT /25-03-18" you would only take "BRÖD & SALT" as the search criteria
        - The note: "VATTENFALL KUNDSERVICE AB/25-03-18" you would only take "VATTENFALL" as the search criteria
        - The note: "NORDEA BANK ABP, FILIAL" you would only take "NORDEA" as the search criteria
    2. Use the 'query_gmail_emails_structured' tool to search for emails matching the details given by the user:
        - before: two days after the given date
        - after: two days before the given date
        - query: the query to search for. Include the amount and 

    3. The amount could be in different formats: e.g. "1234,56" or "1 234,56" or "1234.56". Make sure to query for all of them using gmail "or" operator.

    4. Exclude all emails that seem to be promotional or marketing emails.
    5. For each email that matches the query and that seems like a receipt for an online purchase, extract the following information:
        - date: the date of the email. Format: YYYY-MM-DD
        - amount: the amount of money spent. Format: 1234,56
        - company: the company that sold the product. Exactly as it is in the original email.
        - summary: a description of what was purchased. A summary of the purchase.
        - payment_provider: the payment provider that processed the payment. E.g. 'Nordea', 'SEB', 'PayPal', 'FirstCard', 'Revolut', 'Strawberry', 'MasterCard', 'Apple Pay', 'Unknown'

    Return the following JSON object:
    {
        "status": "success" if an email was found and processed or "error" if no email was found in which case the emails list will be []
        "emails": [
            {
                "date": "YYYY-MM-DD", // The date of the email
                "amount": "1234,56",  // The amount of money spent
                "company": "Company Name", // The company that sold the product, as in the original email
                "summary": "A description of what was purchased. A summary of the purchase.",
                "payment_provider": "Nordea" // E.g. 'Nordea', 'SEB', 'PayPal', etc.
        }
        // ... more email objects if any
     ]
    }
    IMPORTANT: only return the JSON object, nothing else.
    """,
    tools=[query_gmail_tool],
    #output_schema=EmailContent,
)

root_agent = gmail_agent 