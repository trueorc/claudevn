#!/bin/bash

# ClaudeVN Environment Setup Script
# Sets up Python environment for all components

set -e

echo "========================================"
echo "ClaudeVN Environment Setup"
echo "========================================"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 is not installed"
    exit 1
fi

echo "✓ Using Python: $(python3 --version)"
echo ""

# Optional: Create virtual environment
read -p "Create a new virtual environment? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
    echo ""
    echo "To activate it, run:"
    echo "  source venv/bin/activate"
    echo ""
    read -p "Activate now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        source venv/bin/activate
        echo "✓ Virtual environment activated"
    fi
    echo ""
fi

# Install shared package first (in editable mode)
echo "========================================"
echo "Installing Shared Library"
echo "========================================"
cd shared
pip install -e .
cd ..
echo "✓ Shared library installed"
echo ""

# Install marketplace requirements
echo "========================================"
echo "Installing Marketplace Dependencies"
echo "========================================"
cd marketplace
pip install -r requirements.txt
cd ..
echo "✓ Marketplace dependencies installed"
echo ""

# Install serving requirements
echo "========================================"
echo "Installing Serving Dependencies"
echo "========================================"
cd serving
pip install -r requirements.txt
cd ..
echo "✓ Serving dependencies installed"
echo ""

# Install compute requirements
echo "========================================"
echo "Installing Compute Dependencies"
echo "========================================"
cd compute
pip install -r requirements.txt
cd ..
echo "✓ Compute dependencies installed"
echo ""

echo "========================================"
echo "✓ Environment Setup Complete!"
echo "========================================"
echo ""
echo "All components are ready to use."
echo ""
echo "To start services:"
echo "  - Marketplace: cd marketplace && ./start.sh"
echo "  - Serving:     cd serving && ./start.sh"
echo "  - Compute:     cd compute && ./start.sh"
echo ""

