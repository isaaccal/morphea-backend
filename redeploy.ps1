# redeploy.ps1
# Dispara un redeploy en Render para tu servicio morphea-backend

param()

# Asegúrate de que la CLI de Render esté instalada, autenticada y en tu PATH
$serviceId = "srv-d0rn6tripnbc73egj8i0"

Write-Host "🚀 Redeploying service $serviceId on Render..."
render services redeploy $serviceId --confirm --output json
