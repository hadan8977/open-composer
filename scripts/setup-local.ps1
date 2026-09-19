#!/usr/bin/env pwsh
# Open Composer — Local Setup (Windows)
#
# Usage:
#   .\scripts\setup-local.ps1                # full run
#   .\scripts\setup-local.ps1 -DryRun        # show what would run, change nothing
#
# Behaviour:
#   - Runs 6 ordered steps, prints [N/6] <title>  <status> for each.
#   - Skips already-done steps (idempotent).
#   - Stops at the first hard failure with an actionable hint.
#   - At the end prints what's still optional (env keys, etc.) and how to fix it.
#
# Sister script: scripts/setup-local.sh (Linux/macOS).
# Full guide:    docs/setup-local.zh.md

[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
# Force UTF-8 console output so non-ASCII characters render correctly on
# Windows PowerShell 5.1 (which defaults to GBK / cp936 on Chinese systems).
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot

# ---------- helpers ----------
$Total = 6
$Warnings = New-Object System.Collections.Generic.List[string]
$NextActions = New-Object System.Collections.Generic.List[string]
$Failed = $false

function Write-Step([int]$num, [string]$title) {
    $prefix = "[{0,2}/{1}] " -f $num, $Total
    Write-Host $prefix -NoNewline -ForegroundColor Cyan
    Write-Host $title.PadRight(34) -NoNewline
}
function Write-Ok($detail)   { Write-Host "  OK   $detail" -ForegroundColor Green }
function Write-Warn($detail) { Write-Host "  WARN $detail" -ForegroundColor Yellow }
function Write-Fail($detail) { Write-Host "  FAIL $detail" -ForegroundColor Red }
function Write-Skip($detail) { Write-Host "  SKIP $detail" -ForegroundColor DarkGray }
function Write-Sub($line)    { Write-Host "        $line" -ForegroundColor DarkGray }

function Invoke-Cmd($description, $scriptBlock) {
    if ($DryRun) {
        Write-Skip "(dry-run) would: $description"
        return $null
    }
    & $scriptBlock
}

# ---------- Step 1: uv ----------
Write-Step 1 "uv toolchain"
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    $uvVersion = (& uv --version) -replace 'uv ', '' -split ' ' | Select-Object -First 1
    Write-Ok "uv $uvVersion"
} else {
    Write-Fail "uv not found in PATH"
    Write-Sub "Install: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
    Write-Sub "Then close and reopen PowerShell so PATH refreshes."
    exit 1
}

# ---------- Step 2: Python deps ----------
Write-Step 2 "Python deps (.venv)"
$venvOk = (Test-Path .venv) -and (Test-Path .venv\Scripts\python.exe)
if ($venvOk) {
    # Quick check: confirm pyproject.toml hasn't drifted from lockfile
    Invoke-Cmd "uv sync (idempotent)" { & uv sync 2>&1 | Out-Null }
    Write-Ok ".venv synced"
} else {
    Write-Sub "First-time install can take 5-10 minutes."
    Invoke-Cmd "uv sync (first time)" { & uv sync 2>&1 | Out-Null }
    if ((Test-Path .venv\Scripts\python.exe) -or $DryRun) {
        Write-Ok "installed"
    } else {
        Write-Fail "uv sync failed"
        $Failed = $true
    }
}

if ($Failed) {
    Write-Host ""
    Write-Host "Setup stopped at step 2. Fix dep install and re-run." -ForegroundColor Yellow
    exit 1
}

# ---------- Step 3: repo consistency ----------
Write-Step 3 "Repo consistency check"
if ($DryRun) {
    Write-Skip "(dry-run)"
} else {
    $repoOut = & uv run oc repo check 2>&1
    $repoStr = $repoOut -join "`n"
    if ($repoStr -match "status=ok ready=yes") {
        Write-Ok "all checks passed"
    } else {
        Write-Warn "blocked / warning - see reports/repo/repo-check.md"
        $blockedLines = $repoOut | Select-String "blocked" | Select-Object -First 3
        foreach ($line in $blockedLines) { Write-Sub $line.ToString().Trim() }
        $Warnings.Add("repo check has blocked items - see reports/repo/repo-check.md") | Out-Null
        $NextActions.Add("Resolve repo blocks: open reports/repo/repo-check.md and follow 'Next action'") | Out-Null
    }
}

# ---------- Step 4: .env ----------
Write-Step 4 ".env file"
if (Test-Path .env) {
    $envLines = Get-Content .env -ErrorAction SilentlyContinue
    $configured = ($envLines | Where-Object { $_ -match '^[A-Z][A-Z_0-9]+=.+' -and $_ -notmatch '=$' -and $_ -notmatch '=<' -and $_ -notmatch '=YOUR_' }).Count
    Write-Ok "$configured keys configured"
} else {
    if (Test-Path .env.example) {
        Invoke-Cmd "copy .env.example .env" { Copy-Item .env.example .env }
        Write-Warn ".env created from example (placeholders only)"
        $Warnings.Add("Edit .env to add real API keys - see docs/setup-local.zh.md section 3") | Out-Null
        $NextActions.Add("Configure .env keys: docs/setup-local.zh.md section 3") | Out-Null
    } else {
        Write-Warn "no .env (running with fixtures only)"
    }
}

# ---------- Step 5: doctor ----------
Write-Step 5 "Doctor (env check)"
if ($DryRun) {
    Write-Skip "(dry-run)"
} else {
    $doctorOut = & uv run oc doctor 2>&1
    $missingCount = ($doctorOut | Select-String "\| missing\b").Count
    $okCount = ($doctorOut | Select-String "\| ok\b").Count
    if ($missingCount -gt 0) {
        Write-Warn "$okCount ok / $missingCount missing (missing are optional)"
        $Warnings.Add("$missingCount optional API keys missing - capabilities will use fixtures") | Out-Null
    } else {
        Write-Ok "$okCount checks ok, no missing"
    }
}

# ---------- Step 6: cockpit catalog ----------
Write-Step 6 "Cockpit catalog"
if ($DryRun) {
    Write-Skip "(dry-run)"
} else {
    $catOut = & uv run oc cockpit index 2>&1
    if (Test-Path reports\dashboard\catalog.json) {
        try {
            $catalog = Get-Content reports\dashboard\catalog.json -Raw | ConvertFrom-Json
            $s = $catalog.summary
            Write-Ok ("{0} strategies / {1} versions / {2} signals" -f $s.strategy_count, $s.version_count, $s.signal_count)
        } catch {
            Write-Ok "built (catalog.json present)"
        }
    } else {
        Write-Fail "catalog not generated"
        $Failed = $true
    }
}

# ---------- Summary ----------
Write-Host ""
Write-Host ("-" * 70) -ForegroundColor DarkCyan
if (-not $Failed) {
    Write-Host "Open Composer is ready locally." -ForegroundColor Green
} else {
    Write-Host "Setup completed with failures - see above." -ForegroundColor Red
}

if ($Warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Warnings (non-blocking):" -ForegroundColor Yellow
    foreach ($w in $Warnings) { Write-Host "  - $w" -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
if ($NextActions.Count -gt 0) {
    foreach ($a in $NextActions) { Write-Host "  - $a" }
} else {
    Write-Host "  - Read the cockpit catalog: reports/dashboard/catalog.json"
}
Write-Host "  - Configure env keys:  docs/setup-local.zh.md section 3"
Write-Host "  - Try a strategy:      uv run oc strategy draft --idea `"...`""
Write-Host ("-" * 70) -ForegroundColor DarkCyan

if ($Failed) { exit 1 } else { exit 0 }
