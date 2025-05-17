from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from .prompt import ROOT_AGENT_INSTRUCTION
from budget_updater.config import GEMINI_MODEL_ID

from .sub_agents.gmail_agent.agent import gmail_agent
from dotenv import load_dotenv


import os
load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION")


gmail_search_tool = AgentTool(agent=gmail_agent)


root_agent = Agent(
    name="transaction_categorizer",
    model=GEMINI_MODEL_ID,
    description="A helpful financial assistant that categorizes personal transactions into predefined categories for use in a budget spreadsheet. Can search Gmail for transaction details through 'gmail_search_tool'.",
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[gmail_search_tool],
) 