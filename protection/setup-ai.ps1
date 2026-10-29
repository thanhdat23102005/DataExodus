<#
.SYNOPSIS
  Configure the optional Gemini "Explain evidence" route on this computer.

.DESCRIPTION
  Stores GEMINI_API_KEY and GEMINI_MODEL as Windows user environment variables,
  so the key lives in your Windows profile and never in the project folder,
  never in git and never in a chat. The key is read from a hidden prompt, so it
  does not reach your PowerShell history either.

  Whether the key works is decided by Google, not by this script: the key is
  used once against the models endpoint, which both proves it and lists the
  models the account can actually call, so GEMINI_MODEL is chosen from the
  account rather than guessed. The script does not reject a key for its shape.
  AI Studio has issued keys beginning AIza... and, more recently, AQ...; a
  script that enforced the older prefix would have refused a valid key.

  It does warn about an OAuth access token (ya29...), which is a different kind
  of credential: it needs an Authorization: Bearer header and expires within the
  hour, so protection/api.py would get a 401 and fall back silently.

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
  # A hint only - the models call below is what actually decides.
  if ([string]::IsNullOrEmpty($value)) { return $null }
  if ($value.StartsWith("AIza") -or $value.StartsWith("AQ.")) { return "api_key" }
  if ($value.StartsWith("ya29.")) { return "oauth_token_wrong_type" }
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

$secure = Read-Host "Paste your AI Studio API key (hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

if (-not $key) { throw "Nothing pasted." }
if ((Get-Shape $key) -eq "oauth_token_wrong_type") {
  # Warn, do not refuse: the call below is the real test, and a credential this
  # script has never seen before is not the same thing as a broken one.
  Write-Host ("Warning: that looks like an OAuth access token, which needs an " +
              "Authorization: Bearer header and expires within the hour. " +
              "Get an API key at https://aistudio.google.com/apikey if the check fails.") -ForegroundColor Yellow
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

# The listing is not authority either. A key here listed gemini-2.5-flash under
# generateContent and then answered 404 "no longer available to new users", and
# another model answered but took 103s against a 15s read timeout in api.py. So
# call the chosen model once, for real, and time it.
Write-Host "Calling $Model once to check it answers in time..."
$body = @{ contents = @(@{ role = "user"; parts = @(@{ text = "hi" }) })
           generationConfig = @{ maxOutputTokens = 5 } } | ConvertTo-Json -Depth 6
$started = Get-Date
try {
  $null = Invoke-RestMethod -Method Post -TimeoutSec 30 `
    -Uri "https://generativelanguage.googleapis.com/v1beta/models/$Model`:generateContent" `
    -Headers @{ "x-goog-api-key" = $key } -ContentType "application/json" -Body $body
} catch {
  throw ("$Model is listed but did not answer: $($_.Exception.Message). " +
         "Run this again and choose another model.")
}
$seconds = ((Get-Date) - $started).TotalSeconds
Write-Host ("  answered in {0:N1}s" -f $seconds)
if ($seconds -gt 10) {
  Write-Host ("  Warning: protection/api.py gives the provider a 15 s read timeout, so this " +
              "model will often time out and fall back to the local explanation. " +
              "A -lite or -flash model is the better choice here.") -ForegroundColor Yellow
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
