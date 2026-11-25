[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $TargetHost,
    [switch] $Install
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($Install) {
    $action = New-ScheduledTaskAction -Execute "$PSHOME\powershell.exe" -WorkingDirectory $repo `
        -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -TargetHost "{1}"' -f $PSCommandPath, $TargetHost)
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddHours(2) -RepetitionInterval (New-TimeSpan -Hours 2)
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
    Register-ScheduledTask 'OpenComposer Research Digest' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName 'OpenComposer Research Digest'
    return
}

Set-Location -LiteralPath $repo
$snapshot = Join-Path $repo 'reports\owner\research-digest.json'
& '.\.venv\Scripts\python.exe' scripts/export_research_digest.py --edit-highlights --output $snapshot
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$remoteDir = '/root/codex-test/open-composer/reports/owner'
$identity = Join-Path $env:USERPROFILE '.ssh\opencomposer_migration'
$sshOptions = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i', $identity)
& scp.exe @sshOptions $snapshot "${TargetHost}:$remoteDir/.research-digest.json.upload"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& ssh.exe @sshOptions $TargetHost "mv -f -- $remoteDir/.research-digest.json.upload $remoteDir/research-digest.json"
exit $LASTEXITCODE
