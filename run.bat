@echo off
chcp 65001 > nul
echo ============================================================
echo   3SOC - Traffic Violation Detection System
echo ============================================================
echo.

:: Kiem tra Python da cai chua
python --version > nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Vui long cai Python 3.10+ tu https://python.org
    pause
    exit /b 1
)

:: Kiem tra virtual environment ton tai chua
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Tao virtual environment...
    python -m venv venv
    echo [SETUP] Cai dat thu vien tu requirements.txt...
    call venv\Scripts\activate.bat
    pip install --upgrade pip
    pip install -r requirements.txt
    echo [OK] Cai dat hoan tat!
) else (
    call venv\Scripts\activate.bat
)

:: Kiem tra thu muc uploads ton tai
if not exist "uploads" mkdir uploads
if not exist "uploads\temp" mkdir uploads\temp
if not exist "uploads\violations" mkdir uploads\violations

:: Kiem tra thu muc models ton tai
if not exist "models" (
    echo [CANH BAO] Thu muc models/ khong ton tai!
    echo            Vui long dat cac file .pt vao thu muc models/
    echo            - models/3soc.pt
    echo            - models/duongluoibo.pt
    echo            - models/vnmap.pt
    echo.
)

:: Thiet lap bien moi truong neu chua co .env
if not exist ".env" (
    echo [SETUP] Tao file .env mac dinh...
    echo DATABASE_URL=mysql+pymysql://root:1234567890@localhost/detect_3soc > .env
    echo SECRET_KEY=change-this-to-a-very-strong-random-secret-key-in-production >> .env
    echo.
    echo [CANH BAO] Vui long chinh sua file .env cho dung voi cai dat cua ban!
    echo.
)

:: Chay server FastAPI
echo [RUN] Khoi dong server tai http://localhost:8000
echo [RUN] API Docs: http://localhost:8000/docs
echo [RUN] Nhan Ctrl+C de dung server
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
