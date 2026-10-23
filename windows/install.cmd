@echo off
rem Double-click launcher: runs install.ps1 regardless of the PowerShell execution policy.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
