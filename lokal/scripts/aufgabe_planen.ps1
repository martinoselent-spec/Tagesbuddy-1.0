# Tagesbuddy Lokal – tägliche Aufgabe in der Windows-Aufgabenplanung anlegen
# Ausführen in PowerShell im Ordner "lokal" (normale Rechte genügen):
#   powershell -ExecutionPolicy Bypass -File scripts\aufgabe_planen.ps1 [-Uhrzeit 06:35]
param(
    [string]$Uhrzeit = "06:35",
    [string]$Name = "Tagesbuddy Morgen-Briefing"
)
$ErrorActionPreference = "Stop"
$Basis = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Basis ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Bitte zuerst scripts\einrichten.ps1 ausführen." }
if (-not (Test-Path (Join-Path $Basis "token.json"))) { throw "Bitte zuerst anmelden: .venv\Scripts\python.exe -m tagesbuddy anmelden" }

$Aktion   = New-ScheduledTaskAction -Execute $Python -Argument "-m tagesbuddy lauf" -WorkingDirectory $Basis
$Ausloeser = New-ScheduledTaskTrigger -Daily -At $Uhrzeit
# StartWhenAvailable: verpasste Läufe (PC war aus) werden beim nächsten Start nachgeholt.
$Einst = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries `
         -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
         -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
# S4U: läuft auch, wenn niemand angemeldet ist – ohne gespeichertes Passwort.
$Wer = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited

Register-ScheduledTask -TaskName $Name -Action $Aktion -Trigger $Ausloeser -Settings $Einst -Principal $Wer `
    -Description "Tagesbuddy Lokal: liest Mails/Kalender, erkennt Fristen mit Ollama, sendet Morgen-Briefing." -Force | Out-Null

Write-Host "✓ Aufgabe '$Name' angelegt: täglich um $Uhrzeit." -ForegroundColor Green
Write-Host "  Sofort testen:   Start-ScheduledTask -TaskName '$Name'"
Write-Host "  Protokoll:       $Basis\logs\tagesbuddy.log"
Write-Host "  Entfernen:       Unregister-ScheduledTask -TaskName '$Name'"
