# tests/test_categorizer.py
import pytest
from unittest.mock import patch, MagicMock
import os
import json
import unittest
import pandas as pd
import sys

# Add the parent directory to the path so we can import the budget_updater module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment variables for testing BEFORE importing the module
os.environ['GOOGLE_CLOUD_PROJECT'] = 'test-project'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'dummy_credentials.json' # Needs to be set, even if dummy

# Import the function to test AFTER setting env vars
from budget_updater.categorizer import categorizer

@pytest.fixture(autouse=True)
def mock_vertex_init(monkeypatch):
    """Auto-mock vertexai.init to prevent actual initialization."""
    monkeypatch.setattr(categorizer.vertexai, "init", MagicMock())
    # Also mock PROJECT_ID_INITIALIZED for tests where init is skipped implicitly
    monkeypatch.setattr(categorizer, "PROJECT_ID_INITIALIZED", True)


@patch('budget_updater.categorizer.GenerativeModel')
def test_categorize_transaction_success(mock_generative_model):
    """Test successful categorization and memo generation."""
    # Arrange
    ai_response_dict = {"category": "Mat och hushåll", "memo": "ICA Maxi Grocery"}
    mock_response = MagicMock()
    mock_response.text = json.dumps(ai_response_dict) # Simulate JSON string
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value = mock_response
    mock_generative_model.return_value = mock_model_instance # Mock the class constructor

    original_memo = "ICA MAXI LINDHAGEN"
    expected_category = "Mat och hushåll"
    expected_memo = "ICA Maxi Grocery"

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo
    mock_model_instance.generate_content.assert_called_once()
    # Optional: Add more detailed assertions on the prompt content if needed

@patch('budget_updater.categorizer.GenerativeModel')
def test_categorize_transaction_api_error(mock_generative_model):
    """Test fallback when the API call fails."""
    # Arrange
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.side_effect = Exception("API Error")
    mock_generative_model.return_value = mock_model_instance

    original_memo = "Some random memo causing error"
    expected_category = "UNCATEGORIZED"
    expected_memo = original_memo # Fallback memo

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo
    mock_model_instance.generate_content.assert_called_once()


@patch('budget_updater.categorizer.GenerativeModel')
def test_categorize_transaction_invalid_json(mock_generative_model):
    """Test fallback when API response is not valid JSON."""
    # Arrange
    mock_response = MagicMock()
    mock_response.text = "This is not JSON" # Invalid JSON
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value = mock_response
    mock_generative_model.return_value = mock_model_instance

    original_memo = "Memo leading to bad JSON"
    expected_category = "UNCATEGORIZED"
    expected_memo = original_memo # Fallback memo

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo

@patch('budget_updater.categorizer.GenerativeModel')
def test_categorize_transaction_missing_keys(mock_generative_model):
    """Test fallback when JSON response is missing required keys."""
    # Arrange
    ai_response_dict = {"memo": "Some Memo"} # Missing 'category'
    mock_response = MagicMock()
    mock_response.text = json.dumps(ai_response_dict)
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value = mock_response
    mock_generative_model.return_value = mock_model_instance

    original_memo = "Memo leading to missing keys"
    expected_category = "UNCATEGORIZED"
    expected_memo = original_memo # Fallback memo

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo


@patch('budget_updater.categorizer.GenerativeModel')
def test_categorize_transaction_forbidden_category(mock_generative_model):
    """Test fallback when AI returns a forbidden category."""
    # Arrange
    ai_response_dict = {"category": "➡️ Starting Balance", "memo": "AI generated memo"}
    mock_response = MagicMock()
    mock_response.text = json.dumps(ai_response_dict)
    mock_model_instance = MagicMock()
    mock_model_instance.generate_content.return_value = mock_response
    mock_generative_model.return_value = mock_model_instance

    original_memo = "Some memo"
    expected_category = "UNCATEGORIZED" # Fallback category
    expected_memo = "AI generated memo" # Keep AI memo even if category is forbidden

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo

def test_categorize_transaction_no_vertex_init(monkeypatch):
    """Test behavior when Vertex AI was not initialized."""
    # Arrange
    monkeypatch.setattr(categorizer, "PROJECT_ID_INITIALIZED", False) # Simulate init failure
    original_memo = "Test memo"
    expected_category = "UNCATEGORIZED"
    expected_memo = original_memo # Fallback memo

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo

def test_categorize_transaction_empty_original_memo():
    """Test behavior when the original memo is empty."""
    original_memo = ""
    expected_category = "UNCATEGORIZED"
    expected_memo = ""

    # Act
    actual_category, actual_memo = categorizer.categorize_transaction(original_memo)

    # Assert
    assert actual_category == expected_category
    assert actual_memo == expected_memo 