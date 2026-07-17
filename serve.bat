@echo off
cd /d "%~dp0"
echo.
echo  elixer - starting local server...
echo  open:  http://localhost:8080
echo  (proxy only works over http, not file://)
echo.
python -m http.server 8080
pause
