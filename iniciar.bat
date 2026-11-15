@echo off
rem Abre Stream Kit sin ventana desde el codigo fuente (guardian, delay y bot; queda el icono en la bandeja).
for /f "delims=" %%i in ('python -c "import os,sys;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do start "" "%%i" "%~dp0app.py"
