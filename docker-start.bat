@echo off
REM Docker Compose 快速启动脚本 (Windows)

echo ==========================================
echo ResearchFlow Docker Compose 启动脚本
echo ==========================================
echo.

REM 检查 .env 文件是否存在
if not exist .env (
    echo ⚠️  未找到 .env 文件
    echo 正在从 .env.example 创建 .env 文件...
    if exist .env.example (
        copy .env.example .env >nul
        echo ✅ 已创建 .env 文件，请编辑 .env 文件配置必要的环境变量
        echo    特别是：
        echo    - OPENAI_API_KEY
        echo    - SECRET_KEY
        echo    - SUPER_ADMIN_PASSWORD
        echo    - POSTGRES_PASSWORD
        echo.
        pause
    ) else (
        echo ❌ 未找到 .env.example 文件
        exit /b 1
    )
)

REM 检查 Docker 是否运行
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker 未运行，请先启动 Docker Desktop
    pause
    exit /b 1
)

echo.
echo 正在构建镜像...
docker-compose build
if errorlevel 1 (
    echo ❌ 构建失败
    pause
    exit /b 1
)

echo.
echo 正在启动服务...
docker-compose up -d
if errorlevel 1 (
    echo ❌ 启动失败
    pause
    exit /b 1
)

echo.
echo 等待服务启动...
timeout /t 5 /nobreak >nul

echo.
echo ==========================================
echo ✅ 服务启动完成！
echo ==========================================
echo.
echo 访问地址：
echo   - 前端:        http://localhost:3000
echo   - 管理员前端:  http://localhost:3001
echo   - 后端 API:    http://localhost:8000/docs
echo.
echo 查看日志：
echo   docker-compose logs -f
echo.
echo 停止服务：
echo   docker-compose down
echo.
pause

