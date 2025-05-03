"""Vertex AI integration module for Gemini AI."""

import logging
import os

from google.cloud import aiplatform

logger = logging.getLogger(__name__)

# Vertex AI configuration
PROJECT_ID = "aspiro-budget-analysis"
LOCATION = "europe-west1"
MODEL_ID = "gemini-2.0-flash-001"


class VertexAI:
    """Vertex AI wrapper for transaction categorization using Gemini."""

    def __init__(self):
        """Initialize Vertex AI client."""
        try:
            # Set environment variables for Vertex AI
            os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
            os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
            
            # Initialize Vertex AI
            aiplatform.init(
                project=PROJECT_ID,
                location=LOCATION,
            )
            
            logger.info("Vertex AI initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing Vertex AI: {e}")
            raise

    def test_connection(self):
        """Test Vertex AI connection and model availability."""
        try:
            # List available models to verify connectivity
            models = aiplatform.Model.list()
            logger.debug(f"Available models: {[model.display_name for model in models]}")
            
            # Check if our target model is available
            model_available = any(
                MODEL_ID in model.display_name for model in models
            )
            
            if model_available:
                logger.info(f"Model {MODEL_ID} is available")
            else:
                logger.warning(f"Model {MODEL_ID} not found in available models")
                
            return model_available
            
        except Exception as e:
            logger.error(f"Error testing Vertex AI connection: {e}")
            return False

    def categorize_transaction(self, memo, categories):
        """
        Use Gemini AI to categorize a transaction.
        
        This is a placeholder - will be fully implemented in Iteration 3.
        
        Args:
            memo: Transaction description/memo
            categories: List of valid categories with descriptions
            
        Returns:
            Category name string or "UNCATEGORIZED" if unable to categorize
        """
        # This is a placeholder - full implementation in Iteration 3
        logger.debug(f"Placeholder for categorizing transaction: {memo}")
        return "PENDING_AI" 