@echo off
echo [MATCHANEE] Memeriksa dan memasang dependensi...
python -m pip install --upgrade pip
if exist requirements.txt (
    python -m pip install -r requirements.txt
) else (
    python -m pip install flask requests jinja2
)
echo [MATCHANEE] Instalasi selesai. Menghapus requirements.bat...
(goto) 2>nul & del "%~f0"
