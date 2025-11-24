# Docker 镜像加速器配置指南

如果遇到 Docker 镜像拉取失败的问题，推荐配置 Docker daemon 的镜像加速器，而不是在 Dockerfile 中直接指定镜像源。

## 🚀 推荐方案：配置 Docker 镜像加速器

### Linux 系统配置

#### 方法1：使用自动配置脚本（推荐）

```bash
# 运行配置脚本（需要 root 权限）
sudo bash scripts/update_docker_mirrors.sh
```

脚本会自动：
- 备份现有配置
- 更新镜像加速器列表
- 重启 Docker 服务
- 验证配置并测试镜像拉取

#### 方法2：手动配置

1. **编辑或创建 Docker daemon 配置文件**：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
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
```

2. **重启 Docker 服务**：

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

3. **验证配置**：

```bash
docker info | grep -A 10 "Registry Mirrors"
```

### Windows 系统配置

1. **打开 Docker Desktop**
2. **进入 Settings（设置）**（点击右上角齿轮图标）
3. **选择 Docker Engine**
4. **在 JSON 配置中添加或更新 `registry-mirrors` 字段**：

```json
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
```

> ⚠️ **注意**：如果配置文件中已有其他设置，请保留它们，只添加或更新 `registry-mirrors` 字段。

5. **点击 Apply & Restart**（应用并重启）

6. **验证配置**：

打开 PowerShell 或 CMD，运行：
```powershell
docker info | Select-String -Pattern "Registry Mirrors" -Context 0,10
```

### macOS 系统配置

配置方法与 Windows 相同，通过 Docker Desktop 的 Settings 进行配置。

## 📋 国内可用镜像加速器列表（2025年10月测试）

> ⚠️ **重要提示**：许多之前常用的镜像站（包括中科大、网易、百度云等）已无法使用。以下列表为目前可用的镜像加速器。

| 镜像加速器 | 地址 | 说明 | 状态 |
|-----------|------|------|------|
| 1Panel 镜像 | https://docker.1panel.live | 限制只能中国地区 | ✅ 可用 |
| 毫秒镜像 | https://docker.1ms.run | 公益服务 | ✅ 可用 |
| DaoCloud 镜像站 | https://docker.m.daocloud.io | 商业服务 | ✅ 可用 |
| Docker Proxy | https://dockerproxy.net | 镜像加速服务 | ✅ 可用 |
| Registry.cyou | https://registry.cyou | 容器镜像管理中心 | ✅ 可用 |
| Unsee Tech | https://docker-0.unsee.tech | Docker Hub 镜像加速 | ✅ 可用 |
| 轩辕镜像 | https://docker.xuanyuan.me | 会员版 | ⚠️ 需赞助 |
| 中科大镜像 | https://docker.mirrors.ustc.edu.cn | ❌ 已不可用 | ❌ 不可用 |
| 网易镜像 | https://hub-mirror.c.163.com | ❌ 已不可用 | ❌ 不可用 |
| 百度云镜像 | https://mirror.baidubce.com | ❌ 已不可用 | ❌ 不可用 |
| Docker 中国官方 | https://registry.docker-cn.com | ❌ 已停止维护 | ❌ 不可用 |

### 其他可用镜像源（部分）

- `hub.rat.dev` - 个人维护
- `666860.xyz` - Docker Hub Search
- `docker.xiaogenban1993.com` - Docker Hub Search
- `https://lispy.org` - Docker Hub Search
- `https://dytt.online` - Docker Hub Search
- `https://docker.xpg666.xyz/` - Docker Hub 镜像搜索

> 💡 **提示**：建议在配置中添加多个镜像加速器，Docker 会自动尝试下一个可用的源。

### 获取专属镜像加速器地址

#### 阿里云
1. 登录 [阿里云容器镜像服务](https://cr.console.aliyun.com/)
2. 进入「镜像加速器」页面
3. 复制专属加速器地址

#### 腾讯云
1. 登录 [腾讯云容器服务](https://console.cloud.tencent.com/tke)
2. 进入「镜像仓库」->「镜像加速器」
3. 复制专属加速器地址

## 🔧 备选方案：在 Dockerfile 中指定镜像源

如果无法配置 Docker daemon，可以在 Dockerfile 中直接指定镜像源。

### 修改 Dockerfile.backend.cn

将：
```dockerfile
FROM python:3.11-slim
```

改为（选择可用的镜像源）：
```dockerfile
# 阿里云镜像
FROM registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim

# 或腾讯云镜像
# FROM mirror.ccs.tencentyun.com/library/python:3.11-slim

# 或网易镜像
# FROM hub-mirror.c.163.com/library/python:3.11-slim
```

### 修改 Dockerfile.frontend.cn 和 Dockerfile.admin_frontend.cn

将：
```dockerfile
FROM node:18-alpine AS builder
FROM nginx:alpine
```

改为（选择可用的镜像源）：
```dockerfile
# 阿里云镜像
FROM registry.cn-hangzhou.aliyuncs.com/library/node:18-alpine AS builder
FROM registry.cn-hangzhou.aliyuncs.com/library/nginx:alpine

# 或腾讯云镜像
# FROM mirror.ccs.tencentyun.com/library/node:18-alpine AS builder
# FROM mirror.ccs.tencentyun.com/library/nginx:alpine
```

## ✅ 验证配置

配置完成后，测试镜像拉取：

```bash
# 测试拉取 Python 镜像
docker pull python:3.11-slim

# 测试拉取 Node.js 镜像
docker pull node:18-alpine

# 测试拉取 Nginx 镜像
docker pull nginx:alpine
```

## 🐛 故障排查

### 问题1：DNS 解析失败

**错误信息**：`no such host` 或 `lookup failed`

**解决方案**：
1. 检查网络连接
2. 尝试使用其他镜像加速器
3. 检查 DNS 配置：`cat /etc/resolv.conf`

### 问题2：镜像拉取超时

**解决方案**：
1. 增加镜像加速器列表，Docker 会自动尝试下一个
2. 使用专属镜像加速器（阿里云/腾讯云）
3. 检查防火墙设置

### 问题3：镜像加速器不可用

**解决方案**：
1. **更新镜像加速器列表**：使用本文档中列出的最新可用镜像源
2. **使用多个镜像加速器**：在配置中添加多个镜像源，Docker 会自动尝试下一个
3. **测试镜像源**：使用 `docker pull` 测试各个镜像源是否可用
4. **考虑使用 VPN 或代理**：如果所有镜像源都不可用
5. **使用专属镜像加速器**：注册阿里云或腾讯云获取专属加速地址（更稳定）

### 问题4：所有镜像加速器都不可用

**解决方案**：
1. 检查网络连接和 DNS 配置
2. 尝试直接使用官方 Docker Hub（可能需要 VPN）
3. 考虑使用代理服务器
4. 联系网络管理员检查防火墙设置

## 📚 相关文档

- [Docker 官方文档 - 配置镜像加速器](https://docs.docker.com/config/daemon/registry-mirrors/)
- [DOCKER_MIRROR_README.md](../DOCKER_MIRROR_README.md)
- [Docker 部署指南](docker_deployment.md)

