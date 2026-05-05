@echo off
echo Installing Suear Viewer dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Installation failed. Make sure Python and pip are installed.
    pause
    exit /b 1
)
echo Done. Run "python app.py" to start.
pause
