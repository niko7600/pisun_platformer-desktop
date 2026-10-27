#!/usr/bin/env bash
# Сборка одного исполняемого файла для Linux/macOS (нужен Python 3.9+)
cd "$(dirname "$0")"
python3 -m pip install -q pygame pyinstaller
python3 -m PyInstaller --noconfirm --onefile --windowed --name PixelPisun --add-data "icon.png:." main.py
echo "Готово: dist/PixelPisun"
