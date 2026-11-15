@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "ENTRY=launcher.py"
if not exist "%~dp0launcher.py" set "ENTRY=overlay_hud.py"

set "PYC="
if exist "%~dp0python\python.exe" set "PYC=%~dp0python\python.exe"
if not defined PYC for /f "delims=" %%I in ('where python.exe 2^>nul') do call :pick_pyc "%%~I"

if not defined PYC for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "C:\Python3*") do (
    if exist "%%~fD\python.exe" if not defined PYC set "PYC=%%~fD\python.exe"
)

if not defined PYC (
    where py.exe >nul 2>nul
    if not errorlevel 1 (
        py -3 -u "%~dp0%ENTRY%" %*
        if errorlevel 1 pause
        exit /b %errorlevel%
    )
    echo [错误] 未检测到 Python 3，请先安装 Python 3.10+。
    pause
    exit /b 1
)

echo 正在启动时之笛进度助手（调试日志模式）...
"%PYC%" -u "%~dp0%ENTRY%" %*
if errorlevel 1 (
    echo.
    echo 程序异常退出，错误码：%errorlevel%
    pause
)
exit /b %errorlevel%

:pick_pyc
if defined PYC goto :eof
echo "%~1" | findstr /i "WindowsApps" >nul
if errorlevel 1 set "PYC=%~1"
goto :eof
