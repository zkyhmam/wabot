#!/bin/bash

# Create base directory if it doesn't exist
mkdir -p akwam_bot

# Change into the directory
cd akwam_bot || exit

# Create files
touch .env # Optional
touch requirements.txt
touch main.py
touch config.py
touch translations.py
touch database.py
touch state.py
touch scraper.py
touch helpers.py
touch download.py

# Create handlers directory and files
mkdir -p handlers
touch handlers/__init__.py
touch handlers/user.py
touch handlers/admin.py
touch handlers/inline.py
touch handlers/common.py

echo "Directory structure created successfully in akwam_bot/"

# Make the script executable (run this command once in your terminal)
# chmod +x create_structure.sh
