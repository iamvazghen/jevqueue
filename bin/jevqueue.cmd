@echo off
rem jevqueue -- the decision queue in front of your agent's tools.
setlocal
set "JEVQUEUE_ROOT=%~dp0.."
if "%JEVQUEUE_PYTHON%"=="" set "JEVQUEUE_PYTHON=python"
"%JEVQUEUE_PYTHON%" "%JEVQUEUE_ROOT%\scripts\jevqueue.py" %*
