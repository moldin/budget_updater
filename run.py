#!/usr/bin/env python3
"""
Simple runner script for the budget_updater package.
This allows running the application without needing to install it.
"""

import sys
from src.budget_updater.main import main

if __name__ == "__main__":
    sys.exit(main()) 