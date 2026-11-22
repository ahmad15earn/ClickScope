@echo off
REM Opens ClickScope in a throw-away demo folder (your real index and blueprints are not touched).
cd /d "%~dp0"
if exist "ClickScope.exe" ( start "" "ClickScope.exe" --demo ) else if exist "dist\ClickScope.exe" ( start "" "dist\ClickScope.exe" --demo ) else ( python src\main.py --demo )
