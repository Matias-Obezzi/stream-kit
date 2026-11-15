@echo off
rem Instala el boton de delay en StreamDock. Desde el .exe o desde el codigo fuente.
if exist "%~dp0StreamKit.exe" ("%~dp0StreamKit.exe" --streamdock) else (python "%~dp0app.py" --streamdock)
echo Listo: cerra y abri StreamDock.
pause
