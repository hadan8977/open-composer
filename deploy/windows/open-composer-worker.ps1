#!/usr/bin/env pwsh
# Open Composer Windows worker controls.
#
# This script is deliberately local-only. It gives the owner an immediate
# switch for accepting work; the research runner must check the worker state
# before claiming a job. It does not contain credentials or start broker activity.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("status", "pause", "resume", "hard-off", "hard-on", "cleanup")]
    [string]$Action,

    [Parameter(Position = 1)]
    [string]$JobId
)

$ErrorActionPreference = "Stop"
$expectedRoot = [System.IO.Path]::GetFullPath("C:\paseo")
$requestedRoot = if ($env:OC_WORKER_ROOT) {
    [System.IO.Path]::GetFullPath($env:OC_WORKER_ROOT)
} else {
    $expectedRoot
}
if (-not [string]::Equals($requestedRoot, $expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Worker root is fixed at $expectedRoot; refusing to use $requestedRoot."
}
$root = $expectedRoot
$scratch = Join-Path $root "scratch"
$pauseFile = Join-Path $root "worker.pause"
$hardOffFile = Join-Path $root "worker.hard-off"
$stateFile = Join-Path $root "worker-state.json"
$maxUsageBytes = [int64](50 * 1GB)
$maxUsageGiB = 50

function Ensure-Directories {
    New-Item -ItemType Directory -Force -Path $root, $scratch | Out-Null
}

function Get-FreeGiB {
    $driveName = $root.Substring(0, 1)
    $drive = Get-PSDrive -Name $driveName
    return [math]::Round($drive.Free / 1GB, 2)
}

function Get-UsageBytes {
    if (-not (Test-Path -LiteralPath $root)) {
        return [int64]0
    }
    $sum = (Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    if ($null -eq $sum) {
        return [int64]0
    }
    return [int64]$sum
}

function Get-EffectiveStatus {
    if (Test-Path -LiteralPath $hardOffFile) {
        return "hard_off"
    }
    if (Test-Path -LiteralPath $pauseFile) {
        return "paused"
    }
    if ((Get-UsageBytes) -ge $maxUsageBytes) {
        return "over_limit"
    }
    return "ready"
}

function Write-State([string]$Status) {
    Ensure-Directories
    $usageBytes = Get-UsageBytes
    $state = [ordered]@{
        status = $Status
        paused = Test-Path -LiteralPath $pauseFile
        hard_off = Test-Path -LiteralPath $hardOffFile
        root = $root
        scratch = $scratch
        usage_bytes = $usageBytes
        usage_gib = [math]::Round($usageBytes / 1GB, 2)
        usage_limit_gib = $maxUsageGiB
        usage_ok = $usageBytes -lt $maxUsageBytes
        free_gib = Get-FreeGiB
        updated_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $stateFile
}

function Get-PaseoExecutable {
    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles "Paseo\Paseo.exe")
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Paseo\Paseo.exe")
    }
    return $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Stop-PaseoProcess {
    Get-Process -Name "Paseo" -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
}

function Start-PaseoProcess {
    if (Get-Process -Name "Paseo" -ErrorAction SilentlyContinue) {
        return "already running"
    }
    $executable = Get-PaseoExecutable
    if (-not $executable) {
        throw "Paseo.exe was not found in the standard installation locations; start Paseo locally, then retry."
    }
    Start-Process -FilePath $executable -WorkingDirectory $root | Out-Null
    return "started"
}

function Assert-JobId([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch "^[A-Za-z0-9._-]+$") {
        throw "JobId must contain only ASCII letters, digits, dot, underscore, or dash."
    }
}

switch ($Action) {
    "status" {
        Ensure-Directories
        $status = Get-EffectiveStatus
        Write-State $status
        Get-Content -Raw -Path $stateFile
    }
    "pause" {
        Ensure-Directories
        "paused_at_utc=$([DateTime]::UtcNow.ToString('o'))" | Set-Content -Encoding UTF8 -Path $pauseFile
        Write-State "paused"
        Write-Output "worker paused: new jobs will be refused after the caller checks status"
    }
    "resume" {
        Ensure-Directories
        if (Test-Path -LiteralPath $hardOffFile) {
            throw "Worker is hard-off; run hard-on locally to restart the Paseo daemon before resuming."
        }
        if ((Get-UsageBytes) -ge $maxUsageBytes) {
            throw "Worker usage reaches the fixed $maxUsageGiB GiB limit; clean C:\paseo before resuming."
        }
        Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $pauseFile
        Write-State "ready"
        Write-Output "worker resumed"
    }
    "hard-off" {
        Ensure-Directories
        "hard_off_at_utc=$([DateTime]::UtcNow.ToString('o'))" | Set-Content -Encoding UTF8 -Path $hardOffFile
        "paused_at_utc=$([DateTime]::UtcNow.ToString('o'))" | Set-Content -Encoding UTF8 -Path $pauseFile
        Write-State "hard_off"
        Stop-PaseoProcess
        Write-Output "Paseo daemon stopped; run hard-on locally to restart it"
    }
    "hard-on" {
        Ensure-Directories
        Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $hardOffFile, $pauseFile
        $paseoState = Start-PaseoProcess
        Write-State (Get-EffectiveStatus)
        Write-Output "Paseo daemon $paseoState; worker resumed"
    }
    "cleanup" {
        Assert-JobId $JobId
        $jobPath = [System.IO.Path]::GetFullPath((Join-Path $scratch $JobId))
        $scratchPrefix = $scratch.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        if (-not $jobPath.StartsWith($scratchPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a path outside the worker scratch directory."
        }
        if (Test-Path -LiteralPath $jobPath) {
            Remove-Item -Recurse -Force -LiteralPath $jobPath
        }
        Write-State (Get-EffectiveStatus)
        Write-Output "cleaned $JobId"
    }
}
