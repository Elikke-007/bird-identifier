param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8008,
  [switch]$Reload
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$venvPython = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
  Write-Error "未找到后端虚拟环境 Python：$venvPython。请先在 backend 目录创建 .venv 并安装依赖。"
}

$arguments = @(
  "-m",
  "uvicorn",
  "app.main:app",
  "--host",
  $BindHost,
  "--port",
  $Port
)

if ($Reload) {
  $arguments += "--reload"
}

Write-Host "正在启动后端服务: http://$BindHost`:$Port" -ForegroundColor Cyan
Write-Host "使用解释器: $venvPython" -ForegroundColor DarkGray

Push-Location $backendRoot
try {
  & $venvPython @arguments
}
finally {
  Pop-Location
}
