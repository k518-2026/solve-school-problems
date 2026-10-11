param(
    [ValidateSet("blogger", "wordpress", "all")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Continue"
$RepoDir = "E:\GoogleAntigravity\books\solve-school-problems"
Set-Location -Path $RepoDir

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss JST"
$filesToCommit = @()

# 1. Update from remote
git pull --rebase origin main | Out-Null

if ($Target -eq "blogger" -or $Target -eq "all") {
    $triggerFile = "$RepoDir\.github\blogger_trigger.txt"
    "$timestamp Trigger Blogger publish from local scheduler" | Set-Content -Path $triggerFile -Encoding UTF8
    $filesToCommit += ".github/blogger_trigger.txt"
    Write-Host "[$timestamp] Triggered Blogger push event" -ForegroundColor Cyan
}

if ($Target -eq "wordpress" -or $Target -eq "all") {
    $triggerFile = "$RepoDir\.github\wp_trigger.txt"
    "$timestamp Trigger WordPress publish from local scheduler" | Set-Content -Path $triggerFile -Encoding UTF8
    $filesToCommit += ".github/wp_trigger.txt"
    Write-Host "[$timestamp] Triggered WordPress push event" -ForegroundColor Green
}

if ($filesToCommit.Count -gt 0) {
    git add $filesToCommit
    git commit -m "chore(trigger): Scheduled publish trigger at $timestamp [skip ci]"
    git push origin main
    Write-Host "[$timestamp] Pushed trigger to GitHub successfully." -ForegroundColor Magenta
}
