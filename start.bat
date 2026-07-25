@echo off
REM Bewerbungsassistent starten - Windows. Einfach doppelklicken.
setlocal
cd /d "%~dp0"

echo.
echo   Bewerbungsassistent
echo   ===================
echo.

REM --- Python finden ---------------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo   Python 3 wurde nicht gefunden.
  echo   Bitte einmalig installieren: https://www.python.org/downloads/
  echo   Wichtig: beim Installieren "Add Python to PATH" ankreuzen.
  echo.
  pause
  exit /b 1
)

REM --- Abhaengigkeit sicherstellen -------------------------------------------
REM Nur beim ersten Start noetig; danach laeuft der Aufruf still durch.
%PY% -c "import anthropic" >nul 2>&1
if errorlevel 1 (
  echo   Einmalige Einrichtung laeuft ^(das dauert einen Moment^) ...
  %PY% -m pip install --quiet anthropic
  if errorlevel 1 (
    echo.
    echo   Die Installation ist fehlgeschlagen. Bitte von Hand ausfuehren:
    echo       %PY% -m pip install anthropic
    echo.
    pause
    exit /b 1
  )
  echo   Fertig eingerichtet.
  echo.
)

%PY% webapp\server.py %*

REM Bei einem Fehler bleibt das Fenster offen, damit die Meldung lesbar ist.
if errorlevel 1 pause
endlocal
