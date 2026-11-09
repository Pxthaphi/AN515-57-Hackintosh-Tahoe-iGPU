@echo off
rem Download the full macOS Sequoia 15.8.2 installer to the Seagate INSTALLER partition.
rem Double-click, or run from cmd. Safe to close and run again: it resumes where it stopped.
title macOS Sequoia downloader
python -I "%~dp0fetch_installer.py" download 142-50013 auto --fancy
echo.
pause
