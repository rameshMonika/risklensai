<#
.SYNOPSIS
  One-time setup so GitLab CI can deploy to Azure without a stored secret.

  Creates an Azure AD app registration + service principal, adds OIDC federated
  credentials for the main and dockerisation branches, and grants the two roles
  the pipeline needs (AcrPush on the registry, Contributor on rg-risklens).

  At the end it prints the values to paste into
  gitlab.com -> project -> Settings -> CI/CD -> Variables.

  Prereqs: `az login` done; the manual deploy is live (rg-risklens + acrrisklens exist).

.EXAMPLE
  ./infra/setup-gitlab-oidc.ps1
#>

$ErrorActionPreference = "Stop"

# --- config -------------------------------------------------------------------
$AppName       = "gitlab-risklens-cicd"
$ProjectPath   = "monikaramesh113/risklens"
$Branches      = @("main", "dockerisation")
$ResourceGroup = "rg-risklens"
$Acr           = "acrrisklens"
# ---------------------------------------------------------------------------- --

# NOTE: must NOT be called "az" -- PowerShell function names are case-insensitive,
# so a helper named Az would shadow the real az.cmd and recurse forever.
function RunAz {
    $out = & az @args 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') failed:`n$out" }
    return ($out | Out-String).Trim()
}

Write-Host "Checking prerequisites..." -ForegroundColor Cyan
$rgId   = RunAz group show -n $ResourceGroup --query id -o tsv
$acrId  = RunAz acr show -n $Acr --query id -o tsv
$sub    = RunAz account show --query id -o tsv
$tenant = RunAz account show --query tenantId -o tsv
Write-Host "  rg-risklens and acrrisklens found."

# --- 1. app registration + service principal -------------------------------- #
Write-Host "`n1. App registration..." -ForegroundColor Cyan
$clientId = RunAz ad app list --display-name $AppName --query "[0].appId" -o tsv
if ($clientId) {
    Write-Host "  reusing existing app: $clientId"
}
else {
    $clientId = RunAz ad app create --display-name $AppName --query appId -o tsv
    Write-Host "  created app: $clientId"
}

$spExists = RunAz ad sp list --filter "appId eq '$clientId'" --query "[0].id" -o tsv
if (-not $spExists) {
    RunAz ad sp create --id $clientId | Out-Null
    Write-Host "  created service principal"
}
$spId = RunAz ad sp show --id $clientId --query id -o tsv

# --- 2. federated credentials (one per branch) ----------------------------- #
Write-Host "`n2. Federated credentials..." -ForegroundColor Cyan
$haveNames = (RunAz ad app federated-credential list --id $clientId --query "[].name" -o tsv) -split "`n"
foreach ($branch in $Branches) {
    $name = "gitlab-$branch"
    if ($haveNames -contains $name) {
        Write-Host "  $name already exists, skipping"
        continue
    }
    $params = @{
        name      = $name
        issuer    = "https://gitlab.com"
        subject   = "project_path:${ProjectPath}:ref_type:branch:ref:$branch"
        audiences = @("api://AzureADTokenExchange")
    } | ConvertTo-Json -Compress
    $tmp = New-TemporaryFile
    Set-Content -Path $tmp -Value $params -Encoding ascii
    RunAz ad app federated-credential create --id $clientId --parameters $tmp | Out-Null
    Remove-Item $tmp
    Write-Host "  added $name"
}

# --- 3. role assignments -------------------------------------------------- #
Write-Host "`n3. Role assignments..." -ForegroundColor Cyan
foreach ($r in @(
        @{ role = "AcrPush";      scope = $acrId },
        @{ role = "Contributor";  scope = $rgId }
    )) {
    $out = & az role assignment create --assignee-object-id $spId --assignee-principal-type ServicePrincipal `
        --role $r.role --scope $r.scope 2>&1
    if ($LASTEXITCODE -ne 0 -and "$out" -notmatch "already exists|RoleAssignmentExists") {
        throw "role assignment ($($r.role)) failed:`n$out"
    }
    Write-Host "  $($r.role) granted"
}

# --- done: what to put in GitLab --------------------------------------------- #
Write-Host "`n============================================================" -ForegroundColor Green
Write-Host " GitLab -> Settings -> CI/CD -> Variables (add these):" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ("  AZURE_CLIENT_ID        = {0}" -f $clientId)
Write-Host ("  AZURE_TENANT_ID        = {0}" -f $tenant)
Write-Host ("  AZURE_SUBSCRIPTION_ID  = {0}" -f $sub)
Write-Host ""
Write-Host "  SWA_DEPLOY_TOKEN  (mark it 'Masked'):"
$token = & terraform "-chdir=$PSScriptRoot\env" output -raw frontend_deploy_token 2>$null
if ($LASTEXITCODE -eq 0 -and $token) {
    Write-Host ("    {0}" -f $token)
}
else {
    Write-Host "    run:  terraform -chdir=infra\env output -raw frontend_deploy_token"
}
