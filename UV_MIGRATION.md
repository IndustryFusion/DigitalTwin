# UV Migration Guide

This workspace has been migrated to use [UV](https://docs.astral.sh/uv/) - a modern, fast Python package manager for dependency management and virtual environments.

## What Changed

### 🚀 Benefits of UV
- **10-100x faster** than pip
- **Better dependency resolution** 
- **Automatic virtual environment management**
- **Modern Python packaging standards**
- **Lockfile support** for reproducible builds

### 📁 Migrated Projects
- `semantic-model/shacl2flink/` - SHACL to Flink transformation
- `semantic-model/dataservice/` - Data service components  
- `semantic-model/opcua/` - OPC UA tools
- `semantic-model/datamodel/tools/` - Data model tools

### 📁 Docker-Based Projects (No UV Migration Needed)
- `FlinkSqlServicesOperator/` - Kubernetes operator (Docker-based deployment)

## Quick Start

### Prerequisites
```bash
# UV version 0.8.4 is automatically installed by prepare-platform.sh
# Or install manually:
curl -LsSf https://astral.sh/uv/0.8.4/install.sh | sh

# Verify installation
uv --version
# Should show: uv 0.8.4
```

### Setup Development Environment
```bash
# For any Python project in this workspace:
cd semantic-model/shacl2flink/  # or any other Python project
uv venv --python 3.10 .venv
source .venv/bin/activate
make setup
```

## Common Commands

### Installing Dependencies
```bash
# Install production dependencies
uv sync

# Install with development dependencies  
uv sync --dev

# Add new dependency
make add-dep DEP=package-name

# Add new dev dependency
make add-dev-dep DEP=package-name
```

### Setting Up Development Environment
```bash
# For development (includes testing and linting tools)
make setup-dev

# For production dependencies only
make setup
```

### Running Code
```bash
# Run Python scripts
uv run python script.py

# Run tests
make test

# Run linting
make lint
```

## Project Structure

Each migrated Python project now contains:
- `pyproject.toml` - Modern Python project configuration
- `Makefile` - Updated with UV commands
- `.gitignore` - Ignores UV-specific files

## Migration from Old Setup

### Old Way (deprecated)
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
python script.py
```

### New Way (UV)
```bash
uv sync --dev
uv run python script.py
```

## Troubleshooting

### Check UV Version
```bash
# Ensure you're using the correct UV version
uv --version
# Should show: uv 0.8.4

# Update UV to version 0.8.4 if needed
curl -LsSf https://astral.sh/uv/0.8.4/install.sh | sh
```

### Virtual Environment Issues
```bash
# Recreate virtual environment
rm -rf .venv
uv venv --python 3.10 .venv
source .venv/bin/activate
make setup
```

### Dependency Conflicts
```bash
# Clear UV cache
uv cache clean

# Force reinstall
uv sync --reinstall
```

## GitHub Workflows

All CI/CD workflows have been updated to use UV:
- Faster build times
- Consistent environments
- Better caching

## Legacy Files

The following files are kept for compatibility but are no longer used:
- `requirements.txt` 
- `requirements-dev.txt`

Consider removing them once you've verified the migration works correctly.

## More Information

- [UV Documentation](https://docs.astral.sh/uv/)
- [Python Project Configuration](https://docs.astral.sh/uv/concepts/projects/)
- [UV vs pip performance](https://astral.sh/blog/uv)
