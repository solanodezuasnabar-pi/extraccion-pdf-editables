# Token Graph app-only con el certificado del store de Windows (mismo que verify_*.ps1).
# Escribe solo el access_token en stdout. El resto va a stderr.
param(
    [Parameter(Mandatory = $true)][string]$TenantId,
    [Parameter(Mandatory = $true)][string]$ClientId,
    [Parameter(Mandatory = $true)][string]$Thumbprint
)
$ErrorActionPreference = "Stop"
$msalRoot = Join-Path $env:TEMP "msal_nuget"
$abstractions = Join-Path $msalRoot "abstractions\lib\net462\Microsoft.IdentityModel.Abstractions.dll"
$msal = Join-Path $msalRoot "lib\net462\Microsoft.Identity.Client.dll"
if (-not (Test-Path $abstractions) -or -not (Test-Path $msal)) {
    [Console]::Error.WriteLine("No esta MSAL en $msalRoot. Usá --cert con un PEM, o prepará MSAL como en el runbook.")
    exit 2
}
[void][System.Reflection.Assembly]::LoadFrom((Resolve-Path $abstractions).Path)
[void][System.Reflection.Assembly]::LoadFrom((Resolve-Path $msal).Path)
$cert = Get-Item "Cert:\CurrentUser\My\$Thumbprint"
$app = [Microsoft.Identity.Client.ConfidentialClientApplicationBuilder]::Create($ClientId).
    WithAuthority("https://login.microsoftonline.com/$TenantId").
    WithCertificate($cert).
    Build()
$result = $app.AcquireTokenForClient(
    [string[]]@("https://graph.microsoft.com/.default")
).ExecuteAsync().GetAwaiter().GetResult()
[Console]::Out.Write($result.AccessToken)
