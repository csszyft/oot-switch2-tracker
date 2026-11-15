@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "ENTRY=launcher.py"
if not exist "%~dp0launcher.py" set "ENTRY=overlay_hud.py"

set "PYW="
set "PYC="

if exist "%~dp0python\pythonw.exe" set "PYW=%~dp0python\pythonw.exe"
if exist "%~dp0python\python.exe" set "PYC=%~dp0python\python.exe"

if not defined PYW for /f "delims=" %%I in ('where pythonw.exe 2^>nul') do call :pick_pyw "%%~I"
if not defined PYC for /f "delims=" %%I in ('where python.exe 2^>nul') do call :pick_pyc "%%~I"

if not defined PYW for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "C:\Python3*") do (
    if exist "%%~fD\pythonw.exe" if not defined PYW set "PYW=%%~fD\pythonw.exe"
    if exist "%%~fD\python.exe" if not defined PYC set "PYC=%%~fD\python.exe"
)

if not defined PYW (
    where pyw.exe >nul 2>nul
    if not errorlevel 1 (
        start "" pyw -3 "%~dp0%ENTRY%" %*
        exit /b 0
    )
    echo [错误] 未在本机检测到 Python 3。
    echo 请先安装 Python 3.10 或更高版本（https://www.python.org/downloads/），
    echo 安装时请勾选 "Add Python to PATH" 与 "tcl/tk" 组件。
    echo 本工具不依赖任何第三方 pip 包，装好标准版 Python 即可直接双击启动。
    pause
    exit /b 1
)

if defined PYC (
    "%PYC%" -c "import tkinter" >nul 2>nul
    if errorlevel 1 (
        echo [错误] 当前 Python 缺少 tkinter 图形界面组件。
        echo 请在控制面板修复 Python 安装，确保勾选 "tcl/tk and IDLE"。
        pause
        exit /b 1
    )
)

start "" "%PYW%" "%~dp0%ENTRY%" %*
exit /b 0

:pick_pyw
if defined PYW goto :eof
echo "%~1" | findstr /i "WindowsApps" >nul
if errorlevel 1 set "PYW=%~1"
goto :eof

:pick_pyc
if defined PYC goto :eof
echo "%~1" | findstr /i "WindowsApps" >nul
if errorlevel 1 set "PYC=%~1"
goto :eof
