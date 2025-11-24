# 重置数据库脚本 - PowerShell 版本
# 用于重新初始化数据库以使用新的用户名和密码
# 使用方法: .\scripts\reset_database.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "重置数据库配置" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "⚠️  警告：此操作将删除所有数据库数据！" -ForegroundColor Yellow
Write-Host ""

# 检查是否存在 .env 文件
if (-not (Test-Path .env)) {
    Write-Host "❌ 错误：未找到 .env 文件" -ForegroundColor Red
    Write-Host "请先复制 .env.example 为 .env 并配置："
    Write-Host "  Copy-Item .env.example .env"
    exit 1
}

# 读取 .env 文件
$envContent = Get-Content .env
$postgresUser = ($envContent | Select-String "^POSTGRES_USER=(.+)$").Matches.Groups[1].Value
$postgresDb = ($envContent | Select-String "^POSTGRES_DB=(.+)$").Matches.Groups[1].Value

Write-Host "当前数据库配置："
Write-Host "  POSTGRES_USER: $postgresUser"
Write-Host "  POSTGRES_DB: $postgresDb"
Write-Host ""

$confirm = Read-Host "确认要删除所有数据库数据并重新初始化吗？(yes/no)"

if ($confirm -ne "yes") {
    Write-Host "操作已取消"
    exit 0
}

Write-Host ""
Write-Host "正在停止所有服务..." -ForegroundColor Yellow
docker-compose down

Write-Host ""
Write-Host "正在删除数据库数据卷..." -ForegroundColor Yellow
docker volume rm academicdraftagentic_workflow_postgres_data 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "数据卷不存在或已被删除" -ForegroundColor Gray
}

Write-Host ""
Write-Host "正在重新启动服务..." -ForegroundColor Yellow
docker-compose up -d postgres

Write-Host ""
Write-Host "等待数据库初始化完成..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "检查数据库健康状态..." -ForegroundColor Yellow
$timeout = 60
$elapsed = 0
$ready = $false

while ($elapsed -lt $timeout) {
    $result = docker exec academic_workflow_db pg_isready -U $postgresUser 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 数据库已就绪" -ForegroundColor Green
        $ready = $true
        break
    }
    Write-Host "等待数据库启动... ($elapsed/$timeout 秒)"
    Start-Sleep -Seconds 2
    $elapsed += 2
}

if (-not $ready) {
    Write-Host "❌ 数据库启动超时" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "启动所有服务..." -ForegroundColor Yellow
docker-compose up -d

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ 数据库重置完成！" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "服务状态："
docker-compose ps
Write-Host ""
Write-Host "查看后端日志："
Write-Host "  docker logs -f academic_workflow_backend"

