@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Сборка одного exe-файла (нужен Python 3.9+ с pip)
py -3 -m pip install -q pygame pyinstaller
py -3 -m PyInstaller --noconfirm --onefile --windowed --name PixelPisun --icon icon.ico --add-data "icon.png;." main.py
echo.
echo Готово: dist\PixelPisun.exe
pause
