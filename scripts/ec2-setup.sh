#!/bin/bash
# =============================================================================
# Email Scraper - EC2 Initial Setup Script
# =============================================================================
# Run this script once on a fresh EC2 Ubuntu instance
# Usage: bash ec2-setup.sh
# =============================================================================

set -e  # Exit on error

echo "=========================================="
echo "Email Scraper - EC2 Setup"
echo "=========================================="

# Update system
echo "[1/7] Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
echo "[2/7] Installing Docker..."
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Install Docker Compose
echo "[3/7] Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add current user to docker group
echo "[4/7] Configuring Docker permissions..."
sudo usermod -aG docker $USER

# Install Git
echo "[5/7] Installing Git..."
sudo apt-get install -y git

# Create app directory
echo "[6/7] Setting up application directory..."
mkdir -p ~/email-scraper
cd ~/email-scraper

# Clone repository (replace with your repo URL)
echo "[7/7] Cloning repository..."
echo "Please run: git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git ."

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Log out and log back in (for docker group to take effect)"
echo "2. cd ~/email-scraper"
echo "3. git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git ."
echo "4. Create .env file with your configuration"
echo "5. Run: docker-compose up -d"
echo ""
echo "See AWS_SETUP.md for detailed instructions."
