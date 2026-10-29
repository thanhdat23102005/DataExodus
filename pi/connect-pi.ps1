<#
.SYNOPSIS
  Connect this Windows laptop to the DataExodus Box on the Raspberry Pi.

.DESCRIPTION
  Opens an SSH tunnel so that, on this laptop,
    http://127.0.0.1:8010  is the Pi's Guard service (sandbox previews, explanations)
    http://127.0.0.1:8020  is the Pi's dashboard
  Guard keeps talking to 127.0.0.1:8010, so nothing changes in the extension.
  The Pi's services listen on its loopback only; the tunnel is encrypted and
  authenticated by SSH. Leave this window open while you use them.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File pi\connect-pi.ps1 -PiHost dataexodus.local -User student -CopyToken
#>
param(
  [string]$PiHost = "dataexodus.local",
  [string]$User = $env:USERNAME,
  [switch]$CopyToken
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
  throw "OpenSSH client not found. Settings > System > Optional features > add 'OpenSSH Client'."
}
$busy = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8010, 8020 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
  throw "Port 8010 or 8020 is already in use on this laptop (a local DataExodus service?). Stop it, then run this again."
}

if ($CopyToken) {
  $token = ssh "$User@$PiHost" "grep '^DATAEXODUS_GUARD_TOKEN=' /etc/dataexodus/dataexodus.env | cut -d= -f2-"
  if (-not $token) {
    throw "Could not read the token. Log out and back in on the Pi once after installing, then try again."
  }
  ($token | Select-Object -First 1).Trim() | Set-Clipboard
  Write-Host "Guard token copied. Paste it into Guard Settings > Local service token, then Save." -ForegroundColor Green
}

Write-Host "Tunnel to $PiHost is open: Guard service http://127.0.0.1:8010, dashboard http://127.0.0.1:8020" -ForegroundColor Cyan
Write-Host "Keep this window open. Ctrl+C closes the tunnel." -ForegroundColor Cyan
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 `
  -L 127.0.0.1:8010:127.0.0.1:8010 -L 127.0.0.1:8020:127.0.0.1:8020 "$User@$PiHost"
