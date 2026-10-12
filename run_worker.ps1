param(
    [string]$Role = "startup",
    [int]$Quota = 0,
    [switch]$NoPush
)

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

$argsList = @("-m", "src.task_worker", "--role", $Role)
if ($Quota -gt 0) {
    $argsList += @("--quota", "$Quota")
}
if ($NoPush) {
    $argsList += "--no-push"
}

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting GitHub-Synced Local LLM Worker (Role: $Role) in $PSScriptRoot..." -ForegroundColor Cyan
python @argsList
