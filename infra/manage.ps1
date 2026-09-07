<#
.SYNOPSIS
  Start / stop / check the RiskLens Azure stack to avoid paying for it while idle.

.DESCRIPTION
  stop   - stops Postgres Flexible Server, scales core-service + agent-service to 0.
  start  - starts Postgres, waits until it's Ready, sets agent-service back to 1
           warm replica (core-service stays scale-to-zero, it cold-starts fast).
  status - prints Postgres state, per-app min/live replicas, and the app URLs.

  Not touched by any action (all ~$0 or trivial at rest):
    frontend (Azure Static Web App - always served from the CDN, nothing to stop),
    risklens-ai-foundry (pay-per-token), ACR acrrisklens (~$5/mo, holds images),
    Key Vault, VNet, Log Analytics.

.EXAMPLE
  ./infra/manage.ps1 stop
  ./infra/manage.ps1 start
  ./infra/manage.ps1 status
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory, Position = 0)]
  [ValidateSet('start', 'stop', 'status')]
  [string]$Action
)

$ErrorActionPreference = 'Stop'

# --- config -------------------------------------------------------------------
$ResourceGroup  = 'rg-risklens'
$PostgresServer = 'psql-risklens'
$StaticWebApp   = 'risklens-frontend'
$Apps           = @('core-service', 'agent-service')   # container apps only; frontend is a SWA
$WarmApp        = 'agent-service'   # kept at 1 replica on start (torch cold start is slow)
# ---------------------------------------------------------------------------- --

# az is az.cmd on Windows; JMESPath with () or @ breaks cmd arg parsing, so
# every call below fetches -o json and PowerShell does the querying.

# PowerShell 5.1 with EAP=Stop turns any native-command stderr line into a
# terminating NativeCommandError. `az` writes progress/warnings to stderr even
# with --only-show-errors, so every az call is run with EAP relaxed and its
# success judged by $LASTEXITCODE instead.

function Invoke-Az {
  param([string[]]$CliArgs)
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  $json = & az @CliArgs -o json --only-show-errors 2>$null
  $code = $LASTEXITCODE
  $ErrorActionPreference = $prev
  if ($code -ne 0 -or -not $json) { return $null }
  return $json | ConvertFrom-Json
}

function Invoke-AzVoid {
  param([string[]]$CliArgs)
  $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
  & az @CliArgs --only-show-errors 2>&1 | Out-Null
  $code = $LASTEXITCODE
  $ErrorActionPreference = $prev
  return $code
}

function Assert-AzLogin {
  if (-not (Invoke-Az @('account', 'show'))) { throw "Not logged in. Run: az login" }
}

function Get-PgState {
  $s = Invoke-Az @('postgres', 'flexible-server', 'show', '-g', $ResourceGroup, '-n', $PostgresServer)
  if ($s) { return $s.state } else { return 'unknown' }
}

function Set-AppMinReplicas {
  param([string]$App, [int]$Min)
  $code = Invoke-AzVoid @('containerapp', 'update', '-g', $ResourceGroup, '-n', $App, '--min-replicas', "$Min")
  if ($code -ne 0) { Write-Warning "  update failed for '$App' (exit $code)" }
}

function Invoke-Stop {
  Write-Host "Stopping Postgres '$PostgresServer'..." -ForegroundColor Cyan
  if ((Get-PgState) -eq 'Stopped') {
    Write-Host "  already Stopped"
  }
  else {
    Invoke-AzVoid @('postgres', 'flexible-server', 'stop', '-g', $ResourceGroup, '-n', $PostgresServer) | Out-Null
    Write-Host "  stop requested (auto-restarts after 7 days if left)"
  }

  foreach ($app in $Apps) {
    Write-Host "Scaling '$app' to 0..." -ForegroundColor Cyan
    Set-AppMinReplicas $app 0
  }
  Write-Host "`nStopped. Container Apps drain to 0 replicas within ~5 min (cooldown)." -ForegroundColor Green
  Write-Host "frontend (Static Web App) is not touched -- it has no compute and no idle cost." -ForegroundColor DarkGray
}

function Get-SwaLine {
  $swa = Invoke-Az @('staticwebapp', 'show', '-g', $ResourceGroup, '-n', $StaticWebApp)
  if (-not $swa) { return "  {0,-14} not found" -f 'frontend' }
  $swaHost = $swa.defaultHostname
  # Is it actually serving the app, or still the placeholder / unreachable?
  $served = 'unknown'
  try {
    $prev = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
    $r = Invoke-WebRequest -Uri "https://$swaHost" -Method Head -TimeoutSec 10 -UseBasicParsing
    $ProgressPreference = $prev
    $served = if ($r.StatusCode -eq 200) { 'serving (HTTP 200)' } else { "HTTP $($r.StatusCode)" }
  }
  catch { $served = 'unreachable' }
  return "  {0,-14} https://{1}  [{2}]" -f 'frontend', $swaHost, $served
}

function Invoke-Start {
  Write-Host "Starting Postgres '$PostgresServer'..." -ForegroundColor Cyan
  if ((Get-PgState) -eq 'Ready') {
    Write-Host "  already Ready"
  }
  else {
    Invoke-AzVoid @('postgres', 'flexible-server', 'start', '-g', $ResourceGroup, '-n', $PostgresServer) | Out-Null
    Write-Host -NoNewline "  waiting for Ready"
    do {
      Start-Sleep 15
      Write-Host -NoNewline "."
    } while ((Get-PgState) -ne 'Ready')
    Write-Host " done"
  }

  foreach ($app in $Apps) {
    $min = if ($app -eq $WarmApp) { 1 } else { 0 }
    Write-Host "Setting '$app' min replicas to $min..." -ForegroundColor Cyan
    Set-AppMinReplicas $app $min
  }
  Write-Host "`nStarted. '$WarmApp' is warming (~40-60s for the first boot)." -ForegroundColor Green
}

function Invoke-Status {
  Write-Host "Postgres '$PostgresServer': " -NoNewline
  Write-Host (Get-PgState) -ForegroundColor Yellow

  Write-Host "`nContainer Apps:" -ForegroundColor Cyan
  foreach ($app in $Apps) {
    $show = Invoke-Az @('containerapp', 'show', '-g', $ResourceGroup, '-n', $app)
    $min = if ($null -ne $show.properties.template.scale.minReplicas) { $show.properties.template.scale.minReplicas } else { 0 }
    $reps = Invoke-Az @('containerapp', 'replica', 'list', '-g', $ResourceGroup, '-n', $app)
    $live = if ($reps) { @($reps).Count } else { 0 }
    Write-Host ("  {0,-14} min={1}  live replicas={2}  status={3}" -f $app, $min, $live, $show.properties.runningStatus)
  }

  Write-Host "`nURLs:" -ForegroundColor Cyan
  Write-Host (Get-SwaLine)
  foreach ($app in $Apps) {
    $show = Invoke-Az @('containerapp', 'show', '-g', $ResourceGroup, '-n', $app)
    $fqdn = $show.properties.configuration.ingress.fqdn
    if ($fqdn) { Write-Host ("  {0,-14} https://{1}" -f $app, $fqdn) }
    else { Write-Host ("  {0,-14} (internal ingress -- no public URL)" -f $app) }
  }
}

Assert-AzLogin
switch ($Action) {
  'stop' { Invoke-Stop }
  'start' { Invoke-Start }
  'status' { Invoke-Status }
}
