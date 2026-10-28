@echo off
setlocal
set "PYTHONPATH=%~dp0plugins\codex-task-recorder\lib"
set "PYTHONIOENCODING=utf-8"
python -m ctr %*
exit /b %ERRORLEVEL%
