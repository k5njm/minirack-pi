# Conventions for This Python Project

This document outlines conventions and best practices for maintaining consistency across the project. It is designed to assist both human developers and AI coding assistants.

## 1. Code Style

- Follow **PEP 8** for general Python style.
- Use **black** for auto-formatting (`line-length=88`).
- Use **isort** for import sorting (`profile=black`).
- Docstrings must follow **PEP 257** and use Google-style formatting.

## 2. Project Structure

```
project_root/
├── src/                  # Source code
│   ├── module1.py
│   ├── module2.py
│   └── __init__.py
├── tests/                # Unit tests
│   ├── test_module1.py
│   ├── test_module2.py
│   └── conftest.py
├── requirements.txt      # Dependencies
├── pyproject.toml        # Configuration (if applicable)
├── README.md             # Project documentation
└── CONVENTIONS.md        # This file
```

## 3. Naming Conventions

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions & Variables**: `snake_case`
- **Constants**: `ALL_CAPS`
- **Test files**: `test_<module>.py`

## 4. Imports

- Standard library imports first.
- Third-party imports second.
- Local imports last.
- Use absolute imports whenever possible.
- Example:
  ```python
  import os
  import sys
  
  import requests
  
  from src.utils import helper_function
  ```

## 5. Type Hinting

- Use **explicit type hints** wherever applicable.
- Example:
  ```python
  def add_numbers(a: int, b: int) -> int:
      return a + b
  ```

## 6. Testing

- Use **pytest** for testing.
- Test functions should begin with `test_`.
- Use fixtures for setup (`conftest.py`).
- Ensure test coverage is **≥ 90%**.

## 7. Logging & Debugging

- Use Python’s `logging` module.
- Logs should be structured and written to a file.
- Example:
  ```python
  import logging

  logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
  ```

## 8. Exception Handling

- Catch **specific exceptions** instead of `Exception`.
- Use `raise` to propagate unexpected errors.
- Example:
  ```python
  try:
      result = 10 / divisor
  except ZeroDivisionError as e:
      logging.error("Division by zero attempted")
      raise
  ```

## 9. Dependencies

- Use `requirements.txt` for dependency management.
- Prefer `pip install -r requirements.txt` for installing dependencies.
- Use `pip freeze > requirements.txt` to update dependencies.

## 10. AI Coding Assistant Guidance

- Prefer existing helper functions over new redundant functions.
- Ensure all new code follows the naming and import conventions.
- Maintain test coverage for all added functionality.
- Prefer optimized, readable solutions over clever but obscure ones.
- Always add type hints and logging where applicable.

---
Following these conventions will help maintain a clean, readable, and scalable codebase.

