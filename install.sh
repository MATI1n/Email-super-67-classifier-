#!/bin/bash
set -e

if ! command -v python3 &> /dev/null; then
    echo "Error: 'python3' is not installed."
    exit 1
fi

echo "Installing email-classifier..."
python3 -m pip install .

GLOBAL_ENV="$HOME/.email-classifier.env"
if [ ! -f "$GLOBAL_ENV" ]; then
    echo "Creating default global configuration at $GLOBAL_ENV..."
    cat <<EOF > "$GLOBAL_ENV"
EOF
else
    echo "Global configuration already exists at $GLOBAL_ENV."
fi

echo "----------------------------------------"
echo "Installation successful!"
echo "Global settings are located at: $GLOBAL_ENV"
echo "If your Python bin directory is in your PATH, you can now run the classifier from anywhere using the command:"
echo ""
echo "  email-classifier --help"
echo "----------------------------------------"