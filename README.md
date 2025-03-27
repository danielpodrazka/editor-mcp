# How to Run the Tests

Follow these steps to run the tests for the Text Editor MCP server:

## Prerequisites

Ensure you have the following packages installed:

```bash
pip install pytest pytest-asyncio
```

## Setting Up the Test Environment

1. Save the main server code to `text_editor_server.py`
2. Save the test code to `test_text_editor_server.py`
3. Save the conftest.py file in the same directory

## Running the Tests

Execute the following command from the directory containing the test files:

```bash
pytest -v
```

For more detailed output including test coverage:

```bash
pytest -v --cov=text_editor_server
```

## Test Structure

The test suite covers:

1. **set_file tool**
   - Setting valid files
   - Setting non-existent files
   
2. **get_text tool**
   - File state validation
   - Reading entire files
   - Reading specific line ranges
   - Edge cases like empty files
   - Invalid range handling

## Understanding Test Results

- Each test provides a detailed message when it fails
- Success means the tools work as expected for the tested scenarios
- Failed tests indicate where the implementation needs fixing

## Troubleshooting

If tests fail, check:

1. File permissions on temporary files
2. Line endings in test fixtures
3. Python version compatibility (3.7+ recommended)
4. Correct import paths based on your project structure