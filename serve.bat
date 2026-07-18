@echo off
cd /d "%~dp0"
echo.
echo  elixer - starting server...
echo  open:  http://localhost:80
echo  (proxy only works over http, not file://)
echo.
python server.py
pause
