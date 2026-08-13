$ErrorActionPreference = "Stop"
$cfg = Get-Content "$env:USERPROFILE\.render\cli.yaml" -Raw
if ($cfg -notmatch '(?m)^\s+key:\s+(\S+)') { throw "Render CLI is not logged in" }
$headers = @{
  Authorization = "Bearer $($Matches[1])"
  Accept = "application/json"
  "Content-Type" = "application/json"
}

$body = @{
  type = "web_service"
  name = "dockline"
  ownerId = "tea-d9uk9knlk1mc73dtlm20"
  repo = "https://github.com/BigFiiish/dockline"
  autoDeploy = "yes"
  branch = "main"
  envVars = @(
    @{ key = "CLEARBAY_BASE_URL"; value = "https://clearbay.onrender.com" }
    @{ key = "PYTHONUNBUFFERED"; value = "1" }
  )
  serviceDetails = @{
    runtime = "docker"
    plan = "free"
    region = "oregon"
    healthCheckPath = "/api/health"
    envSpecificDetails = @{
      dockerContext = "."
      dockerfilePath = "./Dockerfile"
    }
  }
} | ConvertTo-Json -Depth 8

$result = Invoke-RestMethod -Method Post -Uri "https://api.render.com/v1/services" -Headers $headers -Body $body
$s = $result.service
Write-Output "id=$($s.id)"
Write-Output "name=$($s.name)"
Write-Output "url=$($s.serviceDetails.url)"
Write-Output "dashboard=$($s.dashboardUrl)"
Write-Output "deployId=$($result.deployId)"
Write-Output "status=$($result.deploy.status)"
