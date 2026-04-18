#!/bin/bash
# setup.sh
# --------
# Run this once to initialize git and push to GitHub.
# Usage: bash setup.sh <your-github-username> <repo-name>
#
# Example: bash setup.sh john123 keystroke-auth

set -e

USERNAME=${1:-"your-github-username"}
REPO=${2:-"keystroke-auth"}

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   KeyAuth — GitHub Setup Script      ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Create required directories
mkdir -p data/ikdd users/profiles model

echo "[1/4] Initializing git..."
git init
git add .
git commit -m "Initial commit: KeyAuth keystroke authentication project"

echo ""
echo "[2/4] Creating GitHub repository..."
echo "  → Go to https://github.com/new"
echo "  → Create a NEW repo named: $REPO"
echo "  → Do NOT add README or .gitignore (we have those)"
echo ""
read -p "Press ENTER once you've created the GitHub repo..."

echo ""
echo "[3/4] Pushing to GitHub..."
git remote add origin "https://github.com/$USERNAME/$REPO.git"
git branch -M main
git push -u origin main

echo ""
echo "[4/4] Deploy on Render:"
echo "  → Go to https://render.com"
echo "  → Click 'New +' → 'Web Service'"
echo "  → Connect your GitHub repo: $USERNAME/$REPO"
echo "  → Render auto-detects render.yaml — click Deploy!"
echo ""
echo "✅ Done! Your app will be live at:"
echo "   https://$REPO.onrender.com"
echo ""