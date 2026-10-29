<#
.SYNOPSIS
  Configure the optional Gemini "Explain evidence" route on this computer.

.DESCRIPTION
  Stores GEMINI_API_KEY and GEMINI_MODEL as Windows user environment variables,
  so the key lives in your Windows profile and never in the project folder,
  never in git and never in a chat. The key is read from a hidden prompt, so it
  does not reach your PowerShell history either.

  The script refuses an OAuth access token (ya29... or AQ...). protection/api.py
  sends the credential as x-goog-api-key, which accepts an AI Studio API key
  (AIza...) only; an OAuth token needs an Authorization: Bearer header and
  expires within the hour, so it would only ever produce 401 and a silent fall
  back to the local explanation.

  The key is then used once against the models endpoint. That proves the key
  works and lists the models the account can actually call, so GEMINI_MODEL is
  chosen from the account rather than guessed.

  Create a key at https://aistudio.google.com/apikey

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File protection\setup-ai.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File protection\setup-ai.ps1 -Model gemini-flash-latest

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File protection\setup-ai.ps1 -Check
#>
param(
  [string]$Model,
  [switch]$Check
)
$ErrorActionPreference = "Stop"

function Get-Shape([string]$value) {
  # Mirrors credential_shape() in protection/api.py. Keep the two in step.
  if ([string]::IsNullOrEmpty($value)) { return $null }
  if ($value.StartsWith("AIza")) { return "api_key" }
  if ($value.StartsWith("ya29.") -or $value.StartsWith("AQ.")) { return "oauth_token_wrong_type" }
  return "unrecognised"
}

if ($Check) {
  $k = [Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "User")
  $m = [Environment]::GetEnvironmentVariable("GEMINI_MODEL", "User")
  # Length and shape only: printing the key would defeat the point of the prompt.
  Write-Host "GEMINI_API_KEY : $(if ($k) { "set, $($k.Length) chars, shape=$(Get-Shape $k)" } else { 'not set' })"
  Write-Host "GEMINI_MODEL   : $(if ($m) { $m } else { 'not set' })"
  if ((Get-Shape $k) -eq "oauth_token_wrong_type") {
    Write-Host "  That is an OAuth token, not an API key. Run this script without -Check to replace it." -ForegroundColor Yellow
  }
  return
}

$secure = Read-Host "Paste your AI Studio API key (hidden, starts with AIza)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

$shape = Get-Shape $key
if (-not $key) { throw "Nothing pasted." }
if ($shape -eq "oauth_token_wrong_type") {
  throw ("That is an OAuth access token, not an API key. It would be sent as " +
         "x-goog-api-key and rejected, and it expires within the hour. " +
         "Create a key at https://aistudio.google.com/apikey - it starts with AIza.")
}
if ($shape -ne "api_key") {
  Write-Host "Warning: an AI Studio key normally starts with AIza. Continuing, because Google may change the format." -ForegroundColor Yellow
}

Write-Host "Asking Google which models this key can call..."
try {
  $available = (Invoke-RestMethod -Method Get -TimeoutSec 20 `
    -Uri "https://generativelanguage.googleapis.com/v1beta/models" `
    -Headers @{ "x-goog-api-key" = $key }).models |
    Where-Object { $_.supportedGenerationMethods -contains "generateContent" } |
    ForEach-Object { $_.name -replace '^models/', '' }
} catch {
  # Deliberately not echoing the response: an error body can quote the request URL.
  throw "The key was rejected or unreachable. Check the key and your connection, then run this again."
}
if (-not $available) { throw "The key works but no model on it supports generateContent." }

if ($Model) {
  if ($available -notcontains $Model) {
    throw "This key cannot call '$Model'. Available: $($available -join ', ')"
  }
} else {
  Write-Host "Models available to this key:"
  for ($i = 0; $i -lt $available.Count; $i++) { Write-Host "  [$i] $($available[$i])" }
  $pick = Read-Host "Number of the model to use"
  $index = 0
  if (-not [int]::TryParse($pick, [ref]$index) -or $index -lt 0 -or $index -ge $available.Count) {
    throw "Not one of the listed numbers."
  }
  $Model = $available[$index]
}

[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", $key, "User")
[Environment]::SetEnvironmentVariable("GEMINI_MODEL", $Model, "User")
Write-Host ""
Write-Host "Stored in your Windows user profile (not in this project folder):" -ForegroundColor Green
Write-Host "  GEMINI_API_KEY = (hidden, $($key.Length) chars, verified against Google)"
Write-Host "  GEMINI_MODEL   = $Model"
Write-Host ""
Write-Host "User variables only reach new processes, so now:"
Write-Host "  1. open a new terminal"
Write-Host "  2. start the service again"
Write-Host "  3. check it:  protection\setup-ai.ps1 -Check"
Write-Host "     and on the running service, /health should report ai_configured true"
Write-Host "       and ai_key_shape api_key"
Write-Host ""
Write-Host "In Guard Settings, tick 'Send only selected signal types...' and save."
Write-Host "Explanations stay advisory: no AI output changes enforcement."
