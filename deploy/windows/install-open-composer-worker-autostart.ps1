#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath("C:\paseo")
$launcher = Join-Path $root "start-open-composer-worker-panel.ps1"
$paseo = Join-Path $env:ProgramFiles "Paseo\Paseo.exe"
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Worker panel launcher not found: $launcher"
}
if (-not (Test-Path -LiteralPath $paseo)) {
    throw "Paseo.exe not found: $paseo"
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
New-Item -Path $runKey -Force | Out-Null
$command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""
Set-ItemProperty -Path $runKey -Name "OpenComposerWorkerPanel" -Value $command
$paseoCommand = "`"$paseo`""
Set-ItemProperty -Path $runKey -Name "Paseo" -Value $paseoCommand
Write-Output "autostart installed for current Windows user"
Write-Output $paseoCommand
Write-Output $command
