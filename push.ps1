# Empuja la rama actual al remoto origin
$branch = git rev-parse --abbrev-ref HEAD
Write-Host "⬆️  Haciendo push de la rama '$branch' a origin..."
git push origin $branch
