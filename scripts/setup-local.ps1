#!/usr/bin/env pwsh
# Open Composer — Local Setup (Windows)
#
# Usage:
#   .\scripts\setup-local.ps1                # full run, ends with dashboard serve in background
#   .\scripts\setup-local.ps1 -SkipServe     # everything except the serve step
#   .\scripts\setup-local.ps1 -Port 8001     # use a different port
#   .\scripts\setup-local.ps1 -DryRun        # show what would run, change nothing
#
# Behaviour:
#   - Runs 10 ordered steps, prints [N/10] <title>  <status> for each.
#   - Skips already-done steps (idempotent).
#   - Stops at the first hard failure with an actionable hint.
#   - At the end prints what's still optional (env keys, etc.) and how to fix it.
#
# Sister script: scripts/setup-local.sh (Linux/macOS).
# Full guide:    docs/setup-local.zh.md
# Long-term replacement: `oc setup` CLI (see docs/setup-standardization-plan-2026-05-16.zh.md).

[CmdletBinding()]
param(
    [switch]$SkipServe,
    [switch]$DryRun,
    [int]$Port = 8000
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
$Total = 10
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

# ---------- Step 2: node + npm ----------
Write-Step 2 "node + npm"
$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($node -and $npm) {
    $nodeV = & node --version
    $npmV = & npm --version
    Write-Ok "$nodeV / npm $npmV"
} else {
    Write-Fail "node or npm not found"
    Write-Sub "Install: https://nodejs.org/ (LTS)"
    exit 1
}

# ---------- Step 3: Python deps ----------
Write-Step 3 "Python deps (.venv)"
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

# ---------- Step 4: dashboard node deps ----------
Write-Step 4 "Dashboard node deps"
if (Test-Path dashboard\node_modules) {
    Write-Ok "node_modules present"
} else {
    Write-Sub "First-time install can take 1-2 minutes."
    Invoke-Cmd "npm --prefix dashboard install" {
        Push-Location dashboard
        try { & npm install 2>&1 | Out-Null } finally { Pop-Location }
    }
    if ((Test-Path dashboard\node_modules) -or $DryRun) {
        Write-Ok "installed"
    } else {
        Write-Fail "npm install failed"
        $Failed = $true
    }
}

if ($Failed) {
    Write-Host ""
    Write-Host "Setup stopped at step 3 or 4. Fix dep install and re-run." -ForegroundColor Yellow
    exit 1
}

# ---------- Step 5: repo consistency ----------
Write-Step 5 "Repo consistency check"
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

# ---------- Step 6: .env ----------
Write-Step 6 ".env file"
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

# ---------- Step 7: doctor ----------
Write-Step 7 "Doctor (env check)"
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

# ---------- Step 8: dashboard catalog ----------
Write-Step 8 "Dashboard catalog"
if ($DryRun) {
    Write-Skip "(dry-run)"
} else {
    $catOut = & uv run oc dashboard catalog 2>&1
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

# ---------- Step 9: dashboard frontend ----------
Write-Step 9 "Dashboard frontend (Vite)"
$distOk = Test-Path dashboard\dist\index.html
if (-not $distOk -or $DryRun) {
    Invoke-Cmd "npm --prefix dashboard run build" {
        Push-Location dashboard
        try { & npm run build 2>&1 | Out-Null } finally { Pop-Location }
    }
    $distOk = Test-Path dashboard\dist\index.html
}
if ($distOk) {
    $jsBundle = Get-ChildItem dashboard\dist\assets -Filter "index-*.js" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($jsBundle) {
        $sizeKB = [math]::Round($jsBundle.Length / 1KB, 1)
        Write-Ok "built ($sizeKB KB JS)"
    } else {
        Write-Ok "built"
    }
} else {
    Write-Fail "vite build failed"
    $Failed = $true
}

if ($Failed) {
    Write-Host ""
    Write-Host "Setup stopped before dashboard serve. Fix above errors and re-run." -ForegroundColor Yellow
    exit 1
}

# ---------- Step 10: dashboard serve ----------
Write-Step 10 "Dashboard serve"
if ($SkipServe) {
    Write-Skip "skip (-SkipServe)"
    $NextActions.Add("Start manually: uv run oc dashboard serve --port $Port") | Out-Null
} elseif ($DryRun) {
    Write-Skip "(dry-run)"
} else {
    $portBusy = $null
    try { $portBusy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue -State Listen } catch {}
    if ($portBusy) {
        Write-Warn "port $Port already in use by PID $($portBusy.OwningProcess)"
        $Warnings.Add("Port $Port is busy. Stop the other process or pass -Port <other>") | Out-Null
    } else {
        $logPath = Join-Path $env:TEMP "oc-dashboard.log"
        $errPath = Join-Path $env:TEMP "oc-dashboard.err"
        $proc = Start-Process -FilePath "uv" `
            -ArgumentList @("run", "oc", "dashboard", "serve", "--host", "127.0.0.1", "--port", $Port) `
            -PassThru -WindowStyle Hidden `
            -RedirectStandardOutput $logPath -RedirectStandardError $errPath
        Start-Sleep -Seconds 3
        $ok = $false
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/dashboard/health" -TimeoutSec 5
            if ($health.status -eq "ok") { $ok = $true }
        } catch {}
        if ($ok) {
            Write-Ok "ready at http://127.0.0.1:$Port (PID $($proc.Id))"
            $NextActions.Add("Open: http://127.0.0.1:$Port") | Out-Null
            $NextActions.Add("Stop server: Stop-Process -Id $($proc.Id)") | Out-Null
        } else {
            Write-Fail "started but /api/dashboard/health did not respond"
            Write-Sub "log: $logPath"
            Write-Sub "err: $errPath"
            $Failed = $true
        }
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
    Write-Host "  - Open: http://127.0.0.1:$Port"
}
Write-Host "  - Configure env keys:  docs/setup-local.zh.md section 3"
Write-Host "  - Try a strategy:      uv run oc strategy draft `"...`""
Write-Host "  - VPS deployment:      docs/remote-dashboard-deploy.zh.md"
Write-Host ("-" * 70) -ForegroundColor DarkCyan

if ($Failed) { exit 1 } else { exit 0 }
