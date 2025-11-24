# Docker 镜像配置说明

本项目提供了两套 Docker 配置，分别适用于国内和国外服务器环境。

## 📦 配置文件

### 国外服务器配置（默认）
- `docker-compose.yml`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `Dockerfile.admin_frontend`

### 国内服务器配置（推荐国内使用）
- `docker-compose.cn.yml`
- `Dockerfile.backend.cn`
- `Dockerfile.frontend.cn`
- `Dockerfile.admin_frontend.cn`

## 🚀 快速使用

### 国外服务器

```bash
# 构建
docker-compose build

# 启动
docker-compose up -d

# 停止
docker-compose down
```

### 国内服务器（推荐）

```bash
# 构建
docker-compose -f docker-compose.cn.yml build

# 启动
docker-compose -f docker-compose.cn.yml up -d

# 停止
docker-compose -f docker-compose.cn.yml down
```

## 🌐 镜像源说明

### 国内配置使用的镜像源

1. **Docker 镜像**：使用官方镜像（推荐配置 Docker daemon 镜像加速器）
2. **Python 包**：清华大学 PyPI 镜像 `pypi.tuna.tsinghua.edu.cn`
3. **Node.js 包**：淘宝 npm 镜像 `registry.npmmirror.com`
4. **系统包**：阿里云 Debian 镜像源

### ⚠️ 重要提示：Docker 镜像加速器配置

**如果遇到 Docker 镜像拉取失败**（如 `no such host` 错误），请先配置 Docker daemon 的镜像加速器，这是推荐的最佳实践。

**快速配置**（Linux - 推荐使用脚本）：
```bash
# 使用自动配置脚本（推荐）
sudo bash scripts/update_docker_mirrors.sh
```

**手动配置**（Linux）：
```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": [
    "https://docker.1panel.live",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io",
    "https://dockerproxy.net",
    "https://registry.cyou"
  ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

**Windows 配置**：
1. 打开 Docker Desktop
2. 进入 Settings -> Docker Engine
3. 添加或更新 `registry-mirrors` 字段（同上）
4. 点击 Apply & Restart

> ⚠️ **注意**：中科大、网易、百度云等镜像源已不可用，请使用上述最新可用的镜像源。

**详细配置说明**：请参考 [Docker 镜像加速器配置指南](docs/docker_mirror_setup.md)

### 优势

- ✅ 显著提升镜像拉取速度
- ✅ 加速依赖包安装
- ✅ 减少构建时间
- ✅ 提高部署成功率

## 📝 注意事项

1. 两种配置使用相同的 `.env` 文件
2. 两种配置使用相同的数据卷，可以无缝切换
3. 根据服务器位置选择合适的配置
4. 国内服务器强烈推荐使用 `.cn` 配置

## 🐛 故障排查

如果遇到镜像拉取问题：

1. **首先配置 Docker 镜像加速器**（推荐方案）
   - 参考：[Docker 镜像加速器配置指南](docs/docker_mirror_setup.md)

2. **如果仍无法解决**，可以修改 Dockerfile 直接指定镜像源
   - 在 Dockerfile 中将 `FROM python:3.11-slim` 改为 `FROM registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim`
   - 详细说明见：[Docker 镜像加速器配置指南](docs/docker_mirror_setup.md)

## 📚 详细文档

更多详细信息请参考：
- [Docker 镜像加速器配置指南](docs/docker_mirror_setup.md) ⭐ **推荐先阅读**
- [Docker 部署指南](docs/docker_deployment.md)
- [Docker Compose 运维架构文档](docs/docker_compose_operations.md)

