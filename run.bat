@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   3SOC - He Thong Phat Hien Vi Pham Giao Thong
echo   Traffic Violation Detection System
echo ============================================================
echo.

:: ============================================================
:: KIEM TRA PYTHON
:: ============================================================
echo [*] Kiem tra Python...
python --version > nul 2>&1
if errorlevel 1 (
    echo.
    echo [LOI] Khong tim thay Python!
    echo       Vui long cai dat Python 3.10+ tai: https://python.org
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Phat hien Python %PY_VER%

:: ============================================================
:: KIEM TRA VA TAO VIRTUAL ENVIRONMENT
:: ============================================================
echo.
if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Khong tim thay virtual environment. Dang tao moi...
    python -m venv venv
    if errorlevel 1 (
        echo [LOI] Tao virtual environment that bai!
        pause
        exit /b 1
    )
    echo [SETUP] Kich hoat virtual environment...
    call venv\Scripts\activate.bat
    echo [SETUP] Nang cap pip...
    python -m pip install --upgrade pip --quiet
    echo [SETUP] Cai dat cac thu vien tu requirements.txt...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [LOI] Cai dat thu vien that bai! Kiem tra lai requirements.txt
        pause
        exit /b 1
    )
    echo [OK] Cai dat hoan tat!
) else (
    echo [OK] Tim thay virtual environment. Dang kich hoat...
    call venv\Scripts\activate.bat
)

:: ============================================================
:: TAO THU MUC CAN THIET
:: ============================================================
echo.
echo [*] Kiem tra thu muc du lieu...
set DIRS=uploads uploads\temp uploads\violations logs
for %%d in (%DIRS%) do (
    if not exist "%%d" (
        mkdir "%%d"
        echo [SETUP] Da tao thu muc: %%d
    )
)
echo [OK] Thu muc du lieu san sang.

:: ============================================================
:: KIEM TRA THU MUC MODELS
:: ============================================================
echo.
echo [*] Kiem tra thu muc models...
if not exist "models" (
    mkdir models
    echo [CANH BAO] Thu muc models/ khong ton tai, da tao moi.
    echo            Vui long dat cac file mo hinh vao thu muc models/:
    echo              - models\3soc.pt
    echo              - models\duongluoibo.pt
    echo              - models\vnmap.pt
    echo.
) else (
    set MODEL_OK=1
    for %%m in (3soc.pt duongluoibo.pt vnmap.pt) do (
        if not exist "models\%%m" (
            echo [CANH BAO] Thieu file mo hinh: models\%%m
            set MODEL_OK=0
        )
    )
    if "!MODEL_OK!"=="1" (
        echo [OK] Tat ca file mo hinh da co mat.
    )
)

:: ============================================================
:: THIET LAP FILE .ENV
:: ============================================================
echo.
echo [*] Kiem tra file cau hinh .env...
if not exist ".env" (
    echo [SETUP] Tao file .env mac dinh...
    (
        echo # =============================================
        echo # Cau hinh co so du lieu
        echo # =============================================
        echo DATABASE_URL=mysql+pymysql://root:password@localhost/detect_3soc
        echo.
        echo # =============================================
        echo # Khoa bi mat ^(BAT BUOC doi truoc khi deploy^)
        echo # =============================================
        echo SECRET_KEY=change-this-to-a-very-strong-random-secret-key-in-production
        echo.
        echo # =============================================
        echo # Cau hinh ung dung
        echo # =============================================
        echo APP_ENV=development
        echo DEBUG=True
    ) > .env
    echo [OK] Da tao file .env
    echo.
    echo [CANH BAO] ^^!^^! Vui long cap nhat file .env truoc khi chay ^^!^^!
    echo            Dac biet la DATABASE_URL va SECRET_KEY
    echo.
    pause
) else (
    echo [OK] File .env da ton tai.
)

:: ============================================================
:: KHOI DONG SERVER
:: ============================================================
echo.
echo ============================================================
echo   Dang khoi dong FastAPI Server...
echo ============================================================
echo   URL:      http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   ReDoc:    http://localhost:8000/redoc
echo   Nhan Ctrl+C de dung server
echo ============================================================
echo.

:: Goi Python truc tiep tu venv de tranh loi launcher PATH
set PYTHON=%~dp0venv\Scripts\python.exe
if not exist "%PYTHON%" (
    echo [LOI] Khong tim thay Python trong venv!
    echo       Xoa thu muc venv\ va chay lai script nay.
    pause
    exit /b 1
)
"%PYTHON%" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

:: ============================================================
:: KET THUC
:: ============================================================
echo.
echo [*] Server da dung.
pause
endlocal
