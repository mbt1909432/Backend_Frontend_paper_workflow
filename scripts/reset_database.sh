#!/bin/bash
# 重置数据库脚本 - 用于重新初始化数据库以使用新的用户名和密码
# 使用方法: ./scripts/reset_database.sh

set -e

echo "=========================================="
echo "重置数据库配置"
echo "=========================================="
echo ""
echo "⚠️  警告：此操作将删除所有数据库数据！"
echo ""

# 检查是否存在 .env 文件
if [ ! -f .env ]; then
    echo "❌ 错误：未找到 .env 文件"
    echo "请先复制 .env.example 为 .env 并配置："
    echo "  cp .env.example .env"
    exit 1
fi

# 读取 .env 文件中的数据库配置
source .env

echo "当前数据库配置："
echo "  POSTGRES_USER: ${POSTGRES_USER:-postgres}"
echo "  POSTGRES_DB: ${POSTGRES_DB:-academic_workflow}"
echo ""

read -p "确认要删除所有数据库数据并重新初始化吗？(yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "操作已取消"
    exit 0
fi

echo ""
echo "正在停止所有服务..."
docker-compose down

echo ""
echo "正在删除数据库数据卷..."
docker volume rm academicdraftagentic_workflow_postgres_data 2>/dev/null || echo "数据卷不存在或已被删除"

echo ""
echo "正在重新启动服务..."
docker-compose up -d postgres

echo ""
echo "等待数据库初始化完成..."
sleep 10

echo ""
echo "检查数据库健康状态..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker exec academic_workflow_db pg_isready -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; then
        echo "✅ 数据库已就绪"
        break
    fi
    echo "等待数据库启动... ($elapsed/$timeout 秒)"
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $timeout ]; then
    echo "❌ 数据库启动超时"
    exit 1
fi

echo ""
echo "启动所有服务..."
docker-compose up -d

echo ""
echo "=========================================="
echo "✅ 数据库重置完成！"
echo "=========================================="
echo ""
echo "服务状态："
docker-compose ps
echo ""
echo "查看后端日志："
echo "  docker logs -f academic_workflow_backend"

