import sys
import os
import pandas as pd
import numpy as np
import pytest

# Add src directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from budget_updater.transformation import transform_transactions, TARGET_COLUMNS, PLACEHOLDER_CATEGORY, DEFAULT_STATUS

@pytest.fixture
def sample_parsed_data() -> pd.DataFrame:
    """Creates a sample DataFrame as output from a parser."""
    data = {
        'Date': pd.to_datetime(['2024-01-15', '2024-01-16', '2024-01-17', '2024-01-18']),
        'Description': ['Expense 1', 'Income 1', 'Expense 2', 'Zero Amount'],
        'Amount': [-100.50, 2000.00, -50.25, 0.00]
    }
    return pd.DataFrame(data)

@pytest.fixture
def sample_parsed_data_with_nan() -> pd.DataFrame:
    """Creates sample parsed data containing NaN values, then cleans like parser."""
    data = {
        'Date': pd.to_datetime(['2024-01-15', '2024-01-16', pd.NaT, '2024-01-18']),
        'Description': ['Expense 1', None, 'Expense 2', 'Valid'], # None Description is handled
        'Amount': [-100.50, 2000.00, -50.25, np.nan] # NaN Amount should be handled
    }
    df = pd.DataFrame(data)
    # Simulate parser cleanup for realistic input to transformer
    df.dropna(subset=['Date', 'Amount'], inplace=True)
    return df

def test_transform_transactions_success(sample_parsed_data: pd.DataFrame):
    """Tests successful transformation of typical parsed data."""
    account_name = "💰 SEB"
    transformed_df = transform_transactions(sample_parsed_data, account_name)
    
    assert transformed_df is not None
    assert not transformed_df.empty
    assert len(transformed_df) == 4
    assert list(transformed_df.columns) == TARGET_COLUMNS
    
    # Check first row (expense)
    row1 = transformed_df.iloc[0]
    assert row1['Date'] == '2024-01-15'
    assert row1['Outflow'] == 100.50
    assert row1['Inflow'] == 0.00
    assert row1['Category'] == PLACEHOLDER_CATEGORY
    assert row1['Account'] == account_name
    assert row1['Memo'] == 'Expense 1'
    assert row1['Status'] == DEFAULT_STATUS
    
    # Check second row (income)
    row2 = transformed_df.iloc[1]
    assert row2['Date'] == '2024-01-16'
    assert row2['Outflow'] == 0.00
    assert row2['Inflow'] == 2000.00
    assert row2['Memo'] == 'Income 1'

    # Check fourth row (zero amount)
    row4 = transformed_df.iloc[3]
    assert row4['Date'] == '2024-01-18'
    assert row4['Outflow'] == 0.00 # Zero amount treated as inflow by current logic (amount >= 0)
    assert row4['Inflow'] == 0.00
    assert row4['Memo'] == 'Zero Amount'
    
    # Check dtypes (should be object/string for most, float for amounts)
    assert transformed_df['Outflow'].dtype == 'float64'
    assert transformed_df['Inflow'].dtype == 'float64'
    assert transformed_df['Date'].dtype == 'object' # String date YYYY-MM-DD

def test_transform_transactions_empty_input():
    """Tests transformation with an empty input DataFrame."""
    empty_df = pd.DataFrame(columns=['Date', 'Description', 'Amount'])
    account_name = "💰 SEB"
    transformed_df = transform_transactions(empty_df, account_name)
    
    assert transformed_df is not None
    assert transformed_df.empty
    assert list(transformed_df.columns) == TARGET_COLUMNS # Should still have correct columns

def test_transform_transactions_none_input():
    """Tests transformation with None as input."""
    account_name = "💰 SEB"
    transformed_df = transform_transactions(None, account_name)
    
    assert transformed_df is not None
    assert transformed_df.empty
    assert list(transformed_df.columns) == TARGET_COLUMNS

def test_transform_transactions_handles_cleaned_nan_data(sample_parsed_data_with_nan: pd.DataFrame):
    """Tests transformation handles data after parser has cleaned NaNs."""
    # The fixture already simulates the parser dropping rows with NaT/NaN amounts
    account_name = "💰 SEB"
    transformed_df = transform_transactions(sample_parsed_data_with_nan, account_name)
    
    assert transformed_df is not None
    # Initial fixture has 4 rows, parser drops 2 (NaT date, NaN amount)
    assert len(transformed_df) == 2 
    assert list(transformed_df.columns) == TARGET_COLUMNS
    
    # Check remaining rows are transformed correctly
    assert transformed_df.iloc[0]['Memo'] == 'Expense 1'
    assert transformed_df.iloc[0]['Outflow'] == 100.50
    assert transformed_df.iloc[1]['Memo'] == '' # Description was None, should be transformed to empty string by transformer
    assert transformed_df.iloc[1]['Inflow'] == 2000.00

# TODO: Add tests for transformation logic specific to other account types 
# (e.g., First Card where positive amount = outflow) when implemented. 