@echo off
rem jevqueue -- the decision queue in front of your agent's tools.
rem The CLI lives in the package, not next to this shim: a file named `jevqueue.py` inside
rem the repository would shadow the `jevqueue/` package for anything run from this folder.
setlocal
set "JEVQUEUE_ROOT=%~dp0.."
if "%JEVQUEUE_PYTHON%"=="" set "JEVQUEUE_PYTHON=python"
"%JEVQUEUE_PYTHON%" "%JEVQUEUE_ROOT%\scripts\jevqueue_cli.py" %*
