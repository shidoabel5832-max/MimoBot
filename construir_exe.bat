@echo off
cd /d "%~dp0server"
echo === Instalando PyInstaller ===
..\.venv\Scripts\python -m pip install -U pyinstaller
echo.
echo === Construyendo el ejecutable (tarda uno o dos minutos) ===
..\.venv\Scripts\python -m PyInstaller --onefile --name RobotEscritorio --add-data "..\web;web" --collect-submodules uvicorn main.py
echo.
echo Si todo salio bien, el programa esta en: server\dist\RobotEscritorio.exe
pause
