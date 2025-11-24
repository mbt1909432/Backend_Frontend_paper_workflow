#!/bin/bash
# Docker Compose 快速启动脚本

set -e

echo "=========================================="
echo "ResearchFlow Docker Compose 启动脚本"
echo "=========================================="

# 检查 .env 文件是否存在
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件"
    echo "正在从 .env.example 创建 .env 文件..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ 已创建 .env 文件，请编辑 .env 文件配置必要的环境变量"
        echo "   特别是："
        echo "   - OPENAI_API_KEY"
        echo "   - SECRET_KEY"
        echo "   - SUPER_ADMIN_PASSWORD"
        echo "   - POSTGRES_PASSWORD"
        echo ""
        read -p "按 Enter 继续，或 Ctrl+C 退出以编辑 .env 文件..."
    else
        echo "❌ 未找到 .env.example 文件"
        exit 1
    fi
fi

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行，请先启动 Docker"
    exit 1
fi

# 检查 Docker Compose 是否可用
if ! docker-compose version > /dev/null 2>&1 && ! docker compose version > /dev/null 2>&1; then
    echo "❌ Docker Compose 未安装"
    exit 1
fi

# 确定使用的命令
if docker compose version > /dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo ""
echo "正在构建镜像..."
$DOCKER_COMPOSE build

echo ""
echo "正在启动服务..."
$DOCKER_COMPOSE up -d

echo ""
echo "等待服务启动..."
sleep 5

echo ""
echo "=========================================="
echo "✅ 服务启动完成！"
echo "=========================================="
echo ""
echo "访问地址："
echo "  - 前端:        http://localhost:3000"
echo "  - 管理员前端:  http://localhost:3001"
echo "  - 后端 API:    http://localhost:8000/docs"
echo ""
echo "查看日志："
echo "  $DOCKER_COMPOSE logs -f"
echo ""
echo "停止服务："
echo "  $DOCKER_COMPOSE down"
echo ""

