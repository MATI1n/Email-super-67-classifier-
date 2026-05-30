#!/bin/bash
if ! command -v python3 &> /dev/null; then
    echo "Error: 'python3' is not installed."
    exit 1
fi

echo "Running email classifier..."
python3 classifier.py "$@"