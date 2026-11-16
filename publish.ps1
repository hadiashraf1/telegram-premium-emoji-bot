# Run from the extracted project folder with Git for Windows installed.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$remote = 'https://github.com/hadiashraf1/telegram-premium-emoji-bot.git'
function Invoke-Git { & git @args; if ($LASTEXITCODE -ne 0) { throw 'Git command failed. Check authentication and output above.' } }
$heads = & git ls-remote --heads $remote
if ($LASTEXITCODE -ne 0) { throw 'Cannot check remote repository.' }
if ($heads) { throw 'Remote already has branches. Stop to avoid overwriting existing work.' }
if (-not (Test-Path .git)) {
    Invoke-Git init -b main
    Invoke-Git remote add origin $remote
} else {
    $actual = & git remote get-url origin
    if ($LASTEXITCODE -ne 0 -or $actual -ne $remote) { throw 'Existing origin does not match the project.' }
    $branch = & git branch --show-current
    if ($branch -ne 'main') { throw 'Expected main branch.' }
}
$name = & git config --get user.name
if (-not $name) { $name = Read-Host 'Git author name'; Invoke-Git config --local user.name $name }
$email = & git config --get user.email
if (-not $email) { $email = Read-Host 'Git author email (use your GitHub noreply email for privacy)'; Invoke-Git config --local user.email $email }
Invoke-Git add -- app.py catalog.py tests/test_bot.py README.md LICENSE Dockerfile compose.yaml .gitignore .dockerignore .env.example .github/workflows/tests.yml publish.ps1
& git diff --cached --quiet
if ($LASTEXITCODE -eq 1) { Invoke-Git commit -m 'Rebuild Telegram Premium Emoji Bot v0.3.0' }
elseif ($LASTEXITCODE -ne 0) { throw 'Could not inspect staged files.' }
Invoke-Git push -u origin main
Write-Host 'Published successfully.'
