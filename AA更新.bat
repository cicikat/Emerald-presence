@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在更新...
git pull
echo 更新完成，重新同步依赖中...

set "UV_EXE=%~dp0tools\uv.exe"
if not exist "%UV_EXE%" (
    where uv >nul 2>nul
    if %errorlevel%==0 (
        set "UV_EXE=uv"
    ) else (
        set "UV_EXE="
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo 未找到 .venv，请先运行 "AA1安装并启动.bat"
    pause
    exit /b 1
)

if not "%UV_EXE%"=="" (
    "%UV_EXE%" pip sync requirements.lock --python .venv\Scripts\python.exe
) else (
    ".venv\Scripts\python.exe" -m pip install -r requirements.lock
)
echo 完成，按任意键退出
pause
