# Budget Updater

A Python application designed to automate the process of importing bank transactions into an Aspire Budget Google Sheet. The application reads transaction export files from various banks, parses them, categorizes transactions using Google Gemini AI, formats the data according to the budget sheet's structure, and uploads the formatted transactions to a specific tab for review.

## Supported Banks

- SEB
- First Card
- Revolut
- Strawberry Card

## Setup

### Prerequisites

- Python 3.8 or later
- A Google Cloud Platform (GCP) project with the following APIs enabled:
  - Google Sheets API
  - Vertex AI API
- OAuth 2.0 credentials for Google Sheets API access

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/moldin/budget_updater.git
   cd budget_updater
   ```

2. Create and activate a virtual environment (recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the package:
   ```
   pip install -e .
   ```

4. Set up authentication:
   - Download OAuth 2.0 credentials from GCP Console and save as `credentials.json` in the project root
   - On first run, you'll be prompted to authenticate with your Google account

## Usage

Basic command to process a bank export file:

```
budget-updater --file <path_to_export_file> --account <account_name>
```

For more details, run:

```
budget-updater --help
```

## Development

### Installing development dependencies

```
pip install -e ".[dev]"
```

### Running tests

```
pytest
```

## License

[MIT](LICENSE) 