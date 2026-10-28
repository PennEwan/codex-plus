@echo off
setlocal
set "PYTHONPATH=%~dp0plugins\codex-cdk-recharge\lib"
set "PYTHONIOENCODING=utf-8"
python -m cdkr %*
exit /b %ERRORLEVEL%
