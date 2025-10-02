# Running Tests

It is recommended to use Windows Subsystem for Linux (WSL) to run the tests for compatibility reasons.

## Environment Setup

1.  **Clone the repository in WSL:**
    If you haven't already, clone the repository inside your WSL home directory (e.g., `~/projects/*`), not on the Windows filesystem (`/mnt/c/...`), to avoid performance and permission issues.

2.  **Install Python and venv:**
    Make sure you have Python 3.10 or newer and `python3-venv` installed.
    ```bash
    sudo apt update
    sudo apt install python3.10 python3.10-venv python3-pip
    ```

3.  **Create and activate a virtual environment:**
    Navigate to the project's root directory and create a virtual environment.
    ```bash
    cd /path/to/your/project
    python3 -m venv .venv
    source .venv/bin/activate
    ```

4.  **Install dependencies:**
    Install the required dependencies for testing from the project's root directory.
    ```bash
    pip install -r requirements.test.txt
    ```

## Running Tests

After setting up the environment, you can run the tests using `pytest` from the project's root directory.

```bash
pytest
```

The tests should automatically discover and load the `sun_allocator` integration. If you encounter an `Integration 'sun_allocator' not found` error, ensure you are running `pytest` from the project's root directory and that your directory structure is correct:

```
your_project_root/
├── custom_components/
│   └── sun_allocator/
│       ├── __init__.py
│       └── ...
└── tests/
    ├── test_*.py
    └── ...
```
