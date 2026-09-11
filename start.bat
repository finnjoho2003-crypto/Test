@echo off
REM Bewerbungsassistent starten - Windows. Einfach doppelklicken.
REM
REM Der Assistent laeuft danach auf diesem Rechner unter
REM http://127.0.0.1:8765 - ohne GitHub, ohne Codespace. Die Daten
REM (Profil, Bewerbungen, Schluessel) liegen im Unterordner "bewerbung".
setlocal
cd /d "%~dp0"

REM Deutsche Windows-Konsolen rechnen in cp1252. Umlaute in Meldungen wuerden
REM dort einen Absturz ausloesen, sobald die Ausgabe umgeleitet wird.
set "PYTHONIOENCODING=utf-8"

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
  echo.
  echo   Einmalig installieren:  https://www.python.org/downloads/
  echo   WICHTIG: Beim Installieren unten den Haken bei
  echo   "Add python.exe to PATH" setzen - sonst wird es nachher
  echo   nicht gefunden und diese Meldung kommt wieder.
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

REM --- Browser fuer die PDF-Ausgabe pruefen ----------------------------------
REM Edge zaehlt mit: Er ist auf jedem Windows vorinstalliert und beruht auf
REM derselben Grundlage wie Chrome. Fehlt beides, laeuft alles andere trotzdem.
set "HAT_BROWSER="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "HAT_BROWSER=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "HAT_BROWSER=1"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "HAT_BROWSER=1"
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "HAT_BROWSER=1"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "HAT_BROWSER=1"
if not defined HAT_BROWSER (
  echo   Hinweis: Weder Chrome noch Edge gefunden.
  echo   Alles funktioniert, nur die PDF-Ausgabe braucht einen davon.
  echo.
)

echo   Der Assistent startet. Das Fenster bitte offen lassen -
echo   es schliessen beendet den Assistenten.
echo.

%PY% webapp\server.py %*

REM Bei einem Fehler bleibt das Fenster offen, damit die Meldung lesbar ist.
if errorlevel 1 (
  echo.
  echo   Der Assistent wurde beendet ^(siehe Meldung oben^).
  pause
)
endlocal
