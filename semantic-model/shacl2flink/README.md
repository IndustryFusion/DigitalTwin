# Digital Twin Shacl2Flink

## Requirements

- You need to have Python > 3.8
- Virtualenv needs to be installed
- Proxy needs to be setup if you are in Intel network
- `sqlite3` and `sqlite3-pcre` need to be installed

  ```bash
  sudo  apt install sqlite3 sqlite3-pcre
  ```

## Installation

```bash
python -m venv venv
```

Everytime you are starting a new shell you need to enable the Virtual Environment:

```bash
source venv/bin/activate
make setup
```

Then run:

```bash
make build
```

## VS Code

Normally VS Code should recognize the virtual environment and ask you if you want to use the virtual environment as you Python interpreter.
If not you can do it manually.
Press `Ctrl + Shift + p` and type `Python: Select Interpreter` and select the virtual environment in the _venv/_ folder.

## Development

Install the development dependencies:

```bash
source venv/bin/activate
pip install -r requirements-dev.txt
```

### Unittests

Run with

```bash
python -m pytest
```
## Linting

Run with

```bash
make lint
```