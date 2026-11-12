@echo off
REM Instalador de un solo paso para Windows. Ver scripts\install.py para el detalle.
cd /d "%~dp0"
python scripts\install.py %*
