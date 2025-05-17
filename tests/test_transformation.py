import sys
import os
import pandas as pd
import numpy as np
import pytest

# Add src directory to sys.path
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Import the function to test AND the constants from config
from budget_updater.transformation import transform_transactions
from budget_updater.models import Transaction
from budget_updater import config # Import config

# Define fixtures for test data
@pytest.fixture
def sample_parsed_data() -> pd.DataFrame:
    """Provides a sample DataFrame as output by a parser."""
    data = {
        "Date": pd.to_datetime(["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18"]),
        "Description": ["Expense 1", "Income 1", "Expense 2", "Zero Amount"],
        "Amount": [-100.50, 2000.00, -50.25, 0.00]
    }
    return pd.DataFrame(data)

@pytest.fixture
def sample_parsed_data_with_nan() -> pd.DataFrame:
    """Provides data with NaNs/NaTs *after* parser cleaning would have happened."""
    # Assume parser drops rows where critical data (Date, Amount) is unusable
    # This fixture represents data ready for transformation
    data = {
        "Date": pd.to_datetime(["2024-01-15", "2024-01-16"]),
        "Description": ["Expense 1", None], # Description can be None/empty
        "Amount": [-100.5, 2000.0]
    }
    return pd.DataFrame(data)

def test_transform_transactions_success(sample_parsed_data: pd.DataFrame):
    """Tests successful transformation of typical parsed data."""
    account_name = "💰 SEB"
    transformed_list = transform_transactions(sample_parsed_data, account_name)

    assert transformed_list is not None
    assert isinstance(transformed_list, list)
    assert len(transformed_list) == 4
    assert all(isinstance(item, Transaction) for item in transformed_list)

    # Check first row (expense)
    row1 = transformed_list[0]
    assert row1.date == '2024-01-15'
    assert row1.outflow == '100,50'
    assert row1.inflow == ''
    # Use config.PLACEHOLDER_CATEGORY for the check
    assert row1.category == config.PLACEHOLDER_CATEGORY
    assert row1.account == account_name
    assert row1.memo == 'Expense 1'
    # Use config.DEFAULT_STATUS for the check
    assert row1.status == config.DEFAULT_STATUS

    # Check second row (income)
    row2 = transformed_list[1]
    assert row2.date == '2024-01-16'
    assert row2.outflow == ''
    assert row2.inflow == '2000,00'
    assert row2.memo == 'Income 1'

    # Check third row (expense)
    row3 = transformed_list[2]
    assert row3.date == '2024-01-17'
    assert row3.outflow == '50,25'
    assert row3.inflow == ''
    assert row3.memo == 'Expense 2'

    # Check fourth row (zero amount)
    row4 = transformed_list[3]
    assert row4.date == '2024-01-18'
    assert row4.outflow == ''
    assert row4.inflow == ''
    assert row4.memo == 'Zero Amount'

def test_transform_transactions_empty_input():
    """Tests transformation with an empty DataFrame."""
    empty_df = pd.DataFrame(columns=["Date", "Description", "Amount"])
    transformed_list = transform_transactions(empty_df, "💰 SEB") # Renamed variable
    assert isinstance(transformed_list, list)
    assert len(transformed_list) == 0

def test_transform_transactions_missing_columns():
    """Tests transformation when input DataFrame is missing expected columns."""
    # This scenario should ideally be caught by the parser, but test robustness
    invalid_df = pd.DataFrame({"Date": [pd.Timestamp("2024-01-15")]})
    # The function now handles this by logging an error and returning an empty list
    result = transform_transactions(invalid_df, "💰 SEB")
    assert result == [] # Expect an empty list
    # We could also potentially check the logs here if logging is captured

def test_transform_transactions_handles_cleaned_nan_data(sample_parsed_data_with_nan: pd.DataFrame):
    """Tests transformation handles data after parser has cleaned NaNs."""
    account_name = "💰 SEB"
    transformed_list = transform_transactions(sample_parsed_data_with_nan, account_name)

    assert transformed_list is not None
    assert isinstance(transformed_list, list)
    assert len(transformed_list) == 2 # Fixture has 2 rows ready for transformation

    # Check remaining rows are transformed correctly
    row1 = transformed_list[0]
    assert row1.memo == 'Expense 1'
    assert row1.outflow == '100,50'
    assert row1.inflow == ''

    row2 = transformed_list[1]
    assert row2.memo == ''
    assert row2.outflow == ''
    assert row2.inflow == '2000,00'

# TODO: Add tests for transformation logic specific to other account types 
# (e.g., First Card where positive amount = outflow) when implemented. 