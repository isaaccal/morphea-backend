param([string]$msg)

if (-not $msg) {
  Write-Error "❌ Debes pasar un mensaje: .\commit.ps1 -msg 'Tu mensaje aquí'"
  exit 1
}

git add .
git commit -m $msg
