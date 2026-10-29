@echo off
REM Opens ClickScope with 30 days of SAMPLE data (your real data is never touched, nothing is tracked).
cd /d "%~dp0"
if exist "ClickScope.exe" ( start "" "ClickScope.exe" --demo ) else if exist "dist\ClickScope.exe" ( start "" "dist\ClickScope.exe" --demo ) else ( python src\main.py --demo )
