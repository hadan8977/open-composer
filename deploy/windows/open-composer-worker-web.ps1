#!/usr/bin/env pwsh
# Local-only control panel for the Windows research worker.
# It binds to 127.0.0.1 only and delegates state changes to
# open-composer-worker.ps1. It does not expose a remote command surface.

[CmdletBinding()]
param(
    [int]$Port = 8765,
    [string]$WorkerRoot = "C:\paseo"
)

$ErrorActionPreference = "Stop"
$expectedRoot = [System.IO.Path]::GetFullPath("C:\paseo")
$requestedRoot = if ($env:OC_WORKER_ROOT) { $env:OC_WORKER_ROOT } else { $WorkerRoot }
$requestedRoot = [System.IO.Path]::GetFullPath($requestedRoot)
if (-not [string]::Equals($requestedRoot, $expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Worker root is fixed at $expectedRoot; refusing to use $requestedRoot."
}
$WorkerRoot = $expectedRoot
$worker = Join-Path $WorkerRoot "open-composer-worker.ps1"
if (-not (Test-Path -LiteralPath $worker)) {
    throw "Worker control script not found: $worker"
}

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://127.0.0.1:$Port/")

function Send-Response($Context, [int]$Status, [string]$ContentType, [string]$Body) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
    $Context.Response.StatusCode = $Status
    $Context.Response.ContentType = $ContentType
    $Context.Response.ContentEncoding = [System.Text.Encoding]::UTF8
    $Context.Response.ContentLength64 = $bytes.Length
    $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Context.Response.Close()
}

function Get-State {
    $raw = & $worker status | Out-String
    return ($raw | ConvertFrom-Json)
}

function Invoke-WorkerAction([string]$Action) {
    if ($Action -notin @("pause", "resume", "hard-off", "hard-on")) {
        throw "Unsupported action: $Action"
    }
    & $worker $Action | Out-Null
    return Get-State
}

$html = @'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Open Composer Worker</title>
<style>
body{font:16px system-ui,sans-serif;max-width:680px;margin:40px auto;padding:0 20px;color:#17202a}
button{font:inherit;margin:6px 6px 6px 0;padding:10px 14px;cursor:pointer}
pre{background:#f2f4f6;padding:14px;overflow:auto}
.danger{color:#9b1c1c}
</style>
</head>
<body>
<h1>Open Composer Worker</h1>
<p id="status">Loading...</p>
<button onclick="act('pause')">Pause</button>
<button onclick="act('resume')">Resume</button>
<button class="danger" onclick="confirmAct('hard-off')">Hard off</button>
<button onclick="act('hard-on')">Hard on</button>
<pre id="details"></pre>
<script>
async function load(){
  const r=await fetch('/api/status'); const s=await r.json();
  document.getElementById('status').textContent=(s.status||'unknown')+(s.paused?' (paused)':'');
  document.getElementById('details').textContent=JSON.stringify(s,null,2);
}
async function act(name){
  const r=await fetch('/api/action/'+encodeURIComponent(name),{method:'POST'});
  if(!r.ok) alert(await r.text());
  await load();
}
function confirmAct(name){if(confirm('Stop the Paseo daemon and disable worker intake until hard-on is run locally?')) act(name)}
load(); setInterval(load,5000);
</script>
</body>
</html>
'@

$listener.Start()
Write-Host "Worker panel: http://127.0.0.1:$Port/"
try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            $path = $context.Request.Url.AbsolutePath
            if ($context.Request.HttpMethod -eq "GET" -and $path -eq "/") {
                Send-Response $context 200 "text/html; charset=utf-8" $html
            } elseif ($context.Request.HttpMethod -eq "GET" -and $path -eq "/api/status") {
                Send-Response $context 200 "application/json; charset=utf-8" ((Get-State | ConvertTo-Json -Depth 5))
            } elseif ($context.Request.HttpMethod -eq "POST" -and $path -match "^/api/action/(.+)$") {
                Send-Response $context 200 "application/json; charset=utf-8" ((Invoke-WorkerAction $Matches[1] | ConvertTo-Json -Depth 5))
            } else {
                Send-Response $context 404 "text/plain; charset=utf-8" "not found"
            }
        } catch {
            try { Send-Response $context 500 "text/plain; charset=utf-8" $_.Exception.Message } catch {}
        }
    }
} finally {
    $listener.Stop()
    $listener.Close()
}
