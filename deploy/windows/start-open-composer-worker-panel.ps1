#!/usr/bin/env pwsh
[CmdletBinding()]
param([int]$Port = 8765)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath("C:\paseo")
$panel = Join-Path $root "open-composer-worker-web.ps1"
if (-not (Test-Path -LiteralPath $panel)) {
    throw "Worker panel not found: $panel"
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    exit 0
}

& $panel -Port $Port -WorkerRoot $root
