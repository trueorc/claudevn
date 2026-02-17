# ClaudeVN Demo Data

This directory contains sample data files for running ClaudeVN demo scenarios.

## Files

### sales_q4_2024.csv

Sample sales data for Scenario 1 (Sales Data Analysis & Reporting).

- **Rows**: 95 transactions
- **Columns**: date, product_id, product_name, category, quantity, price, region, customer_id
- **Date Range**: October 1 - December 31, 2024
- **Products**: 6 different products (electronics and tools)
- **Regions**: West, East, Central, South
- **Total Revenue**: ~$24,000

### sample_codebase/

Sample Python codebase for Scenario 3 (Code Analysis & Refactoring).

**Files:**
- `app.py` - Main application with long functions and multiple responsibilities
- `models.py` - Data models with circular import issue
- `utils.py` - Utility functions with duplicate code and missing error handling
- `tests.py` - Unit tests with incomplete coverage

**Intentional Issues:**
- Long function (75+ lines) in app.py
- Circular import between app.py and models.py
- Missing error handling in utils.py
- Duplicate validation logic
- Low test coverage (~60%)

## Usage

These files are referenced in `docs/demo-scenarios.md` and are used by the demo scenarios to showcase ClaudeVN capabilities.

### Scenario 1: Sales Analysis

```bash
# Upload CSV file
curl -X POST http://localhost:8002/api/storage/upload \
  -F "file=@examples/demo-data/sales_q4_2024.csv" \
  -F "session_id=demo-sales-001"
```

### Scenario 3: Code Analysis

```bash
# Create zip of codebase
cd examples/demo-data
zip -r sample_codebase.zip sample_codebase/

# Upload
curl -X POST http://localhost:8002/api/storage/upload \
  -F "file=@sample_codebase.zip" \
  -F "session_id=demo-code-001"
```

## Note

The `.gitignore` in the root directory is configured to allow these demo files while excluding other CSV and data files.

