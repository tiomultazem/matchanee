@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [MATCHANEE] Membuat virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Gagal membuat virtual environment.
        pause
        exit /b 1
    )
    echo [MATCHANEE] Mengaktifkan venv dan memasang dependensi...
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    if exist requirements.txt (
        python -m pip install -r requirements.txt
    ) else (
        python -m pip install flask requests jinja2
    )
) else (
    call .venv\Scripts\activate.bat
)

echo [MATCHANEE] Menjalankan server...
python server.py
pause
