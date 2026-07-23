@echo off
cd /d "%~dp0"
echo elixir static server starting at http://localhost:80
python -m http.server 80
pause
