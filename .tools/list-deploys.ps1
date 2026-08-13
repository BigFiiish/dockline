$ErrorActionPreference = "Stop"
$cfg = Get-Content "$env:USERPROFILE\.render\cli.yaml" -Raw
if ($cfg -notmatch '(?m)^\s+key:\s+(\S+)') { throw "Render CLI is not logged in" }
$headers = @{ Authorization = "Bearer $($Matches[1])"; Accept = "application/json" }
$id = $args[0]
if (-not $id) { throw "service id required" }
$deploys = Invoke-RestMethod -Uri "https://api.render.com/v1/services/$id/deploys?limit=5" -Headers $headers
$deploys | ForEach-Object {
  $d = if ($_.deploy) { $_.deploy } else { $_ }
  "id=$($d.id) status=$($d.status) commit=$($d.commit.id) finished=$($d.finishedAt)"
}
