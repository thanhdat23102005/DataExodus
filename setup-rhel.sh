#!/bin/bash
# DataExodus — RHEL/CentOS/Rocky Setup Script
# Run once on a fresh VM

set -e

echo "[setup] Installing system dependencies..."
sudo dnf install -y python3 python3-pip python3-venv git unzip wget

# Playwright Chromium dependencies (RHEL-specific)
echo "[setup] Installing Playwright browser deps..."
sudo dnf install -y     alsa-lib atk at-spi2-atk at-spi2-core cairo cups-libs dbus-libs     expat fontconfig freetype gdk-pixbuf2 glib2 gtk3 libX11 libXcomposite     libXcursor libXdamage libXext libXfixes libXi libXrandr libXrender     libXtst libdrm libxcb libxkbcommon mesa-libgbm nspr nss pango     xorg-x11-fonts-Type1 xorg-x11-fonts-misc

echo "[setup] Creating Python venv..."
python3 -m venv venv
source venv/bin/activate

echo "[setup] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[setup] Installing Playwright browsers..."
playwright install chromium
playwright install-deps chromium

echo "[setup] Done. Activate with: source venv/bin/activate"
