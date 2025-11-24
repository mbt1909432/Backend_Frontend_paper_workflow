#!/bin/bash

# Docker 镜像加速器更新脚本
# 使用最新的可用镜像源（2025年10月测试）

set -e

echo "=========================================="
echo "Docker 镜像加速器配置更新脚本"
echo "=========================================="
echo ""

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then 
    echo "❌ 请使用 sudo 运行此脚本"
    exit 1
fi

# 备份现有配置
DAEMON_JSON="/etc/docker/daemon.json"
if [ -f "$DAEMON_JSON" ]; then
    BACKUP_FILE="${DAEMON_JSON}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "📦 备份现有配置到: $BACKUP_FILE"
    cp "$DAEMON_JSON" "$BACKUP_FILE"
fi

# 创建配置目录
mkdir -p /etc/docker

# 写入新的镜像加速器配置
echo "📝 写入新的镜像加速器配置..."
cat > "$DAEMON_JSON" <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1panel.live",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io",
    "https://dockerproxy.net",
    "https://registry.cyou",
    "https://docker-0.unsee.tech"
  ]
}
EOF

echo "✅ 配置已更新"
echo ""

# 重启 Docker 服务
echo "🔄 重启 Docker 服务..."
if command -v systemctl &> /dev/null; then
    systemctl daemon-reload
    systemctl restart docker
    echo "✅ Docker 服务已重启"
elif command -v service &> /dev/null; then
    service docker restart
    echo "✅ Docker 服务已重启"
else
    echo "⚠️  请手动重启 Docker 服务"
fi

echo ""
echo "=========================================="
echo "验证配置"
echo "=========================================="
docker info | grep -A 10 "Registry Mirrors" || echo "⚠️  无法获取镜像加速器信息"

echo ""
echo "=========================================="
echo "测试镜像拉取"
echo "=========================================="
echo "正在测试拉取 node:18-alpine 镜像..."
if docker pull node:18-alpine > /dev/null 2>&1; then
    echo "✅ 镜像拉取成功！"
    docker rmi node:18-alpine > /dev/null 2>&1 || true
else
    echo "❌ 镜像拉取失败，请检查网络连接或尝试其他镜像源"
fi

echo ""
echo "=========================================="
echo "配置完成！"
echo "=========================================="
echo ""
echo "如果仍有问题，请参考: docs/docker_mirror_setup.md"

