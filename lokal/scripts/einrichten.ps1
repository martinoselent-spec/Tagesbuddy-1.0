# Tagesbuddy Lokal – Einrichtung unter Windows
# Ausführen in PowerShell im Ordner "lokal":
#   powershell -ExecutionPolicy Bypass -File scripts\einrichten.ps1
$ErrorActionPreference = "Stop"
$Basis = Split-Path -Parent $PSScriptRoot
Set-Location $Basis

Write-Host "== Tagesbuddy Lokal einrichten in $Basis" -ForegroundColor Cyan

# 1) Python prüfen (3.11 oder neuer wegen tomllib)
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) { $PythonCmd = "py"; $PythonArgs = @("-3") } else { $PythonCmd = "python"; $PythonArgs = @() }
$Version = & $PythonCmd @PythonArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$Version -lt [version]"3.11") {
    throw "Python $Version gefunden – benötigt wird 3.11 oder neuer (https://www.python.org/downloads/)."
}
Write-Host "Python $Version gefunden"

# 2) Virtuelle Umgebung + Pakete
if (-not (Test-Path ".venv")) { & $PythonCmd @PythonArgs -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
Write-Host "Pakete installiert"

# 3) Konfiguration anlegen
if (-not (Test-Path "config.toml")) {
    Copy-Item config.example.toml config.toml
    Write-Host "config.toml angelegt – bitte jetzt öffnen und ausfüllen (E-Mail, Modell, Ordner-ID)." -ForegroundColor Yellow
    notepad config.toml
}

# 4) Ollama prüfen
try {
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
    Write-Host ("Ollama läuft. Installierte Modelle: " + (($tags.models | ForEach-Object { $_.name }) -join ", "))
} catch {
    Write-Host "Ollama antwortet nicht auf localhost:11434 – ist Ollama gestartet?" -ForegroundColor Yellow
}

if (-not (Test-Path "credentials.json")) {
    Write-Host "credentials.json fehlt noch – siehe Anleitung Schritt 3 (Google Cloud)." -ForegroundColor Yellow
} else {
    Write-Host "Starte Google-Anmeldung im Browser ..."
    & .\.venv\Scripts\python.exe -m tagesbuddy anmelden
    & .\.venv\Scripts\python.exe -m tagesbuddy pruefen
}
Write-Host "Fertig. Nächste Schritte: 'lauf --trocken' testen, dann scripts\aufgabe_planen.ps1" -ForegroundColor Green
