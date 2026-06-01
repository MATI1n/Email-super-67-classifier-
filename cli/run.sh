#!/bin/bash
if ! command -v python3 &> /dev/null; then
    echo "Error: 'python3' is not installed."
    exit 1
fi

if [ ! -f "classifier.py" ]; then
    echo "Error: 'classifier.py' not found in the current directory."
    exit 1
fi

LOG_FILE="app.log"
echo "Running email classifier (logging to $LOG_FILE)..."

python3 classifier.py "$@" >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "Success: Classification completed successfully."
else
    echo "Error: Classifier failed. Check $LOG_FILE for details."
    exit 1
fi
