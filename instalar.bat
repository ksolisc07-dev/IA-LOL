@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Instalador - Coach de IA para LoL

echo ============================================================
echo   Instalador del Coach de IA para League of Legends
echo ============================================================
echo.

rem --- 1. Buscar Python ---------------------------------------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo No se encontro Python. Intentando instalarlo con winget...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo No se pudo instalar Python automaticamente.
        echo Descargalo de https://www.python.org/downloads/ ^(marca "Add Python to PATH"^)
        echo y vuelve a ejecutar este instalador.
        pause
        exit /b 1
    )
    echo.
    echo Python instalado. Cierra esta ventana y vuelve a ejecutar instalar.bat
    pause
    exit /b 0
)
echo [1/4] Python encontrado: 
%PY% --version

rem --- 2. Entorno virtual y dependencias ----------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creando entorno virtual...
    %PY% -m venv .venv || goto :error
) else (
    echo [2/4] Entorno virtual ya existe.
)
echo [3/4] Instalando dependencias ^(puede tardar un minuto^)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :error

rem --- 3. API key -----------------------------------------------------------
echo [4/4] Configuracion...
".venv\Scripts\python.exe" -c "from lol_coach.config import first_run_setup; first_run_setup()"

rem --- 4. Lanzador y acceso directo ----------------------------------------
> "iniciar.bat" (
    echo @echo off
    echo chcp 65001 ^>nul
    echo cd /d "%%~dp0"
    echo ".venv\Scripts\python.exe" -m lol_coach menu
    echo pause
)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\LoL Coach IA.lnk');" ^
  "$s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.Description='Coach de IA para LoL'; $s.Save()"

echo.
echo ============================================================
echo   Listo. Abre "LoL Coach IA" desde tu escritorio
echo   ^(o ejecuta iniciar.bat en esta carpeta^).
echo ============================================================
pause
exit /b 0

:error
echo.
echo Hubo un error durante la instalacion. Revisa los mensajes de arriba.
pause
exit /b 1
