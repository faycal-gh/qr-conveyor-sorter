$ErrorActionPreference = "Stop"

$Owner = "faycal-gh"
$Repo = "qr-conveyor-sorter"

Write-Host "Preparing Git repository $Owner/$Repo ..."

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or not available in PATH. Install Git for Windows first."
}

if (-not (Test-Path ".git")) {
    git init
}

git branch -M main
git add .

$hasCommit = $false
git rev-parse --verify HEAD *> $null
if ($LASTEXITCODE -eq 0) { $hasCommit = $true }

if (-not $hasCommit) {
    git commit -m "Initial QR conveyor sorter project"
} else {
    git commit -m "Update QR conveyor sorter project"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No new changes to commit."
    }
}

if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Host "GitHub CLI detected. Checking authentication..."
    gh auth status

    $remoteExists = git remote get-url origin 2>$null
    if ($LASTEXITCODE -eq 0 -and $remoteExists) {
        Write-Host "Origin already exists: $remoteExists"
        git push -u origin main
    } else {
        Write-Host "Creating GitHub repository $Owner/$Repo and pushing main..."
        gh repo create "$Owner/$Repo" --source=. --remote=origin --push
    }
} else {
    Write-Host ""
    Write-Host "GitHub CLI (gh) is not installed. Local Git repository is ready."
    Write-Host "Install GitHub CLI, then run this script again, or create the repo on GitHub and run:"
    Write-Host "  git remote add origin https://github.com/$Owner/$Repo.git"
    Write-Host "  git push -u origin main"
}
