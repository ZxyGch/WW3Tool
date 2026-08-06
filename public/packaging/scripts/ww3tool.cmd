@echo off
rem WW3Tool Windows launcher (replaces the blocked ww3tool.exe console script).
rem Once run, removes the legacy exe launcher so `ww3tool` always hits this .cmd.
rem The exe is blocked by Windows app control policies on some machines; a .cmd
rem text script is not.
if exist "%~dp0ww3tool.exe" del /q "%~dp0ww3tool.exe"
python -m run %*
