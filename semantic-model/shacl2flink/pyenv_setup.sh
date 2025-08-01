#! /bin/bash

#Install UV with python 3.10 version
# Install UV
curl -LsSf https://astral.sh/uv/0.8.4/install.sh | sh

# Add UV to PATH permanently
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/.cargo/bin:$PATH"

# Install Python 3.10
uv python install 3.10
echo "UV installation complete. Python environments will be created automatically per project."