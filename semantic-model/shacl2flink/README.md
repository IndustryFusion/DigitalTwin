# Digital Twin Shacl2Flink

## Requirements

- You need to have Python  3.10
- Virtualenv needs to be installed
- `sqlite3` and `pcre2` need to be installed

  ```bash
  sudo  apt install sqlite3 libsqlite3-dev libpcre2-dev
  ```

## Installation

If miniconda installed with python3.10 environment (using prepare-platform.sh), move to step 2 else use below script to install and create python env
### Step 1 :
```bash
bash pyenv_setup.sh
source ./miniconda3/bin/activate
conda create -n py310 python=3.10 -y
```
### Step 2 :
Everytime you are starting a new shell you need to enable the miniconda Virtual Environment which runs python 3.10 sourcing miniconda installation path:

```bash
source ./miniconda3/bin/activate
conda activate py310
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