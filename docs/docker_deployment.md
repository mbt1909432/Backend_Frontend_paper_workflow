# Docker Compose 部署指南

本文档介绍如何使用 Docker Compose 部署整个 ResearchFlow 系统，包括前端、后端、管理员前端和 PostgreSQL 数据库。

## 目录结构

```
.
├── docker-compose.yml          # Docker Compose 配置文件（国外服务器）
├── docker-compose.cn.yml       # Docker Compose 配置文件（国内服务器）
├── .env                        # 环境变量配置文件（需要创建）
├── .env.example                # 环境变量配置示例
├── Dockerfile.backend          # 后端 Dockerfile（国外）
├── Dockerfile.backend.cn       # 后端 Dockerfile（国内）
├── Dockerfile.frontend         # 前端 Dockerfile（国外）
├── Dockerfile.frontend.cn      # 前端 Dockerfile（国内）
├── Dockerfile.admin_frontend   # 管理员前端 Dockerfile（国外）
├── Dockerfile.admin_frontend.cn # 管理员前端 Dockerfile（国内）
├── nginx.frontend.conf         # 前端 Nginx 配置
├── nginx.admin_frontend.conf   # 管理员前端 Nginx 配置
├── docker-start.sh             # 快速启动脚本（Linux/macOS）
├── docker-start.bat            # 快速启动脚本（Windows）
└── docs/
    └── docker_deployment.md    # 本文档
```

## 前置要求

1. **Docker** 版本 20.10 或更高
2. **Docker Compose** 版本 2.0 或更高
3. **服务器资源**：
   - 至少 2GB RAM
   - 至少 10GB 磁盘空间
   - CPU: 2 核心或更多

## 国内/国外镜像配置选择

系统提供了两套 Docker 配置，分别适用于不同网络环境：

### 配置说明

- **国外服务器**：使用 `docker-compose.yml` 和对应的 Dockerfile（无 `.cn` 后缀）
  - 使用 Docker Hub 官方镜像
  - 使用 PyPI 和 npm 官方源
  
- **国内服务器**：使用 `docker-compose.cn.yml` 和对应的 Dockerfile（带 `.cn` 后缀）**（推荐）**
  - 使用中科大 Docker 镜像源：`docker.mirrors.ustc.edu.cn`
  - 使用清华大学 PyPI 镜像：`pypi.tuna.tsinghua.edu.cn`
  - 使用淘宝 npm 镜像：`registry.npmmirror.com`
  - 使用阿里云 Debian 镜像源

### 如何选择

- 如果服务器在中国大陆，**强烈推荐使用国内配置**（`.cn` 后缀），可以显著提升构建速度
- 如果服务器在海外，使用默认配置即可

### 使用方式

所有命令都需要根据选择的配置添加 `-f` 参数：

```bash
# 国外服务器（默认）
docker-compose build
docker-compose up -d

# 国内服务器（推荐）
docker-compose -f docker-compose.cn.yml build
docker-compose -f docker-compose.cn.yml up -d
```

> **注意**：两种配置使用相同的 `.env` 文件和数据卷，可以无缝切换。

## 快速开始

### 方式一：使用快速启动脚本（推荐）

#### Linux/macOS

```bash
# 赋予执行权限
chmod +x docker-start.sh

# 运行脚本
./docker-start.sh
```

#### Windows

```cmd
docker-start.bat
```

脚本会自动：
1. 检查并创建 `.env` 文件（如果不存在）
2. 检查 Docker 是否运行
3. 构建所有镜像
4. 启动所有服务

### 方式二：手动启动

#### 1. 克隆项目

```bash
git clone <your-repo-url>
cd academic-draft-agentic-workflow
```

#### 2. 配置环境变量

复制环境变量示例文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的环境变量（详见下方"环境变量配置"章节）。

**重要**：生产环境必须修改以下配置：
- `SECRET_KEY`：JWT 密钥（使用强随机字符串）
- `SUPER_ADMIN_PASSWORD`：超级管理员密码
- `POSTGRES_PASSWORD`：数据库密码
- `OPENAI_API_KEY`：OpenAI API 密钥

#### 3. 构建和启动服务

**选择配置**：
- **国外服务器**：使用默认配置 `docker-compose.yml`
- **国内服务器**：使用国内镜像配置 `docker-compose.cn.yml`（推荐，速度更快）

**国外服务器**：
```bash
# 构建所有镜像
docker-compose build

# 启动所有服务（后台运行）
docker-compose up -d
```

**国内服务器**：
```bash
# 使用国内镜像配置（推荐）
docker-compose -f docker-compose.cn.yml build

# 启动所有服务（后台运行）
docker-compose -f docker-compose.cn.yml up -d
```

**通用命令**：
```bash
# 查看服务状态
docker-compose ps
# 或
docker-compose -f docker-compose.cn.yml ps

# 查看日志
docker-compose logs -f
# 或
docker-compose -f docker-compose.cn.yml logs -f
```

> **提示**：国内服务器使用 `.cn` 配置可以显著提升镜像拉取和依赖安装速度，因为使用了国内镜像源（中科大 Docker 镜像、清华大学 PyPI 镜像、淘宝 npm 镜像）。

### 4. 验证部署

根据 `.env` 文件中配置的端口访问服务（默认端口如下）：

- **前端**：访问 http://localhost:${FRONTEND_PORT:-3000}
- **管理员前端**：访问 http://localhost:${ADMIN_FRONTEND_PORT:-3001}
- **后端 API**：访问 http://localhost:${BACKEND_PORT:-8000}/docs
- **数据库**：端口 ${POSTGRES_PORT:-5432}（仅内部访问）

### 5. 停止服务

**国外服务器**：
```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷（注意：会删除数据库数据）
docker-compose down -v
```

**国内服务器**：
```bash
# 停止所有服务
docker-compose -f docker-compose.cn.yml down

# 停止并删除数据卷（注意：会删除数据库数据）
docker-compose -f docker-compose.cn.yml down -v
```

## GitHub Actions 自动部署

仓库提供 `.github/workflows/deploy.yml`，当代码推送到 `main` 或 `master` 分支时会自动完成以下步骤：

1. Checkout 项目并使用 Docker Buildx 构建 `backend`、`frontend`、`admin-frontend` 三个镜像。
2. 将镜像推送到 GitHub Container Registry（`ghcr.io/<org>/<repo>-<component>`）。
3. 通过 SSH 登录部署服务器，同步仓库中的 `docker-compose.yml`。
4. 在服务器上执行 `docker compose pull && docker compose up -d`，拉取最新镜像并以最小停机时间重启服务。

> 如果服务器只安装了旧版 `docker-compose`，脚本会自动回退到 `docker-compose` 命令。

### pull_policy: always 的使用

如果希望在任何场景下都强制从远程拉取最新镜像，可以在 `docker-compose.yml` 的服务定义内增加 `pull_policy: always`：

```
services:
  backend:
    image: ghcr.io/<org>/<repo>-backend:latest
    pull_policy: always
```

这样即使手动执行 `docker compose up -d`，也会在启动前自动重新拉取镜像。与工作流中的显式 `docker compose pull` 结合使用，可以确保线上环境始终运行最新镜像。

## 服务说明

### 1. PostgreSQL 数据库

- **容器名**：`academic_workflow_db`
- **端口**：通过 `POSTGRES_PORT` 环境变量配置（默认: 5432）
- **数据持久化**：使用 Docker volume `postgres_data`
- **健康检查**：自动检查数据库就绪状态

### 2. Backend 服务

- **容器名**：`academic_workflow_backend`
- **端口**：通过 `BACKEND_PORT` 环境变量配置（默认: 8000）
- **访问地址**：http://localhost:${BACKEND_PORT:-8000}
- **API 文档**：http://localhost:${BACKEND_PORT:-8000}/docs
- **依赖**：等待 PostgreSQL 就绪后启动
- **数据持久化**：通过 `OUTPUT_DIR` 环境变量配置输出目录挂载（默认: `./output`）

### 3. Frontend 服务

- **容器名**：`academic_workflow_frontend`
- **端口**：通过 `FRONTEND_PORT` 环境变量配置（默认: 3000）
- **访问地址**：http://localhost:${FRONTEND_PORT:-3000}
- **技术栈**：React + Vite + Nginx
- **构建**：生产模式构建，使用 Nginx 提供静态文件服务

### 4. Admin Frontend 服务

- **容器名**：`academic_workflow_admin_frontend`
- **端口**：通过 `ADMIN_FRONTEND_PORT` 环境变量配置（默认: 3001）
- **访问地址**：http://localhost:${ADMIN_FRONTEND_PORT:-3001}
- **技术栈**：React + Vite + Nginx
- **构建**：生产模式构建，使用 Nginx 提供静态文件服务

## 环境变量配置

### 端口配置（所有对外暴露的端口都可配置）

```env
# PostgreSQL 数据库端口（默认: 5432）
POSTGRES_PORT=5432

# Backend API 端口（默认: 8000）
BACKEND_PORT=8000

# Frontend 前端端口（默认: 3000）
FRONTEND_PORT=3000

# Admin Frontend 管理员前端端口（默认: 3001）
ADMIN_FRONTEND_PORT=3001
```

### 输出目录配置

```env
# 输出目录挂载路径（相对于 docker-compose.yml 的路径，或使用绝对路径）
# 默认: ./output
# 示例:
#   - 相对路径: ./output
#   - 绝对路径: /data/researchflow/output
#   - Windows 路径: E:/data/output
OUTPUT_DIR=./output
```

### 数据库配置

```env
# PostgreSQL 数据库配置
POSTGRES_USER=postgres              # 数据库用户名
POSTGRES_PASSWORD=your_db_password  # 数据库密码（生产环境必须修改）
POSTGRES_DB=academic_workflow       # 数据库名称
POSTGRES_HOST=postgres              # 数据库主机（Docker 服务名）
POSTGRES_PORT=5432                  # 数据库端口（可通过环境变量配置）
```

### Backend 配置

```env
# OpenAI 配置
OPENAI_API_KEY=your_openai_api_key           # OpenAI API 密钥（必需）
OPENAI_API_BASE=                             # 自定义 API 端点（可选）
OPENAI_MODEL=gpt-4                           # 使用的模型
OPENAI_TEMPERATURE=0.7                       # 温度参数
OPENAI_MAX_TOKENS=2000                       # 最大 token 数

# Anthropic 配置（可选）
ANTHROPIC_API_KEY=                           # Anthropic API 密钥
ANTHROPIC_API_BASE=                          # 自定义 API 端点
ANTHROPIC_MODEL=claude-sonnet-4-20250514     # 使用的模型
ANTHROPIC_TEMPERATURE=0.7                    # 温度参数
ANTHROPIC_MAX_TOKENS=4096                    # 最大 token 数

# 服务器配置
HOST=0.0.0.0                                 # 监听地址
PORT=8000                                    # 监听端口
DEBUG=false                                  # 调试模式（生产环境设为 false）
LOG_LEVEL=INFO                               # 日志级别

# JWT 认证配置
SECRET_KEY=your-secret-key-change-in-production  # JWT 密钥（生产环境必须修改）
ALGORITHM=HS256                              # JWT 算法
ACCESS_TOKEN_EXPIRE_MINUTES=10080            # Token 过期时间（分钟，默认7天）

# 超级管理员配置
SUPER_ADMIN_USERNAME=admin                   # 超级管理员用户名
SUPER_ADMIN_PASSWORD=your_admin_password     # 超级管理员密码（生产环境必须修改）

# 文件输出配置
OUTPUT_DIR=/app/output                       # 输出目录（容器内路径，不要修改）
# 注意：OUTPUT_DIR 环境变量用于配置主机挂载路径，见上方"输出目录配置"
```

### Frontend 配置

```env
# 前端 API 地址（容器内使用服务名）
VITE_API_BASE_URL=http://backend:8000/api/v1
```

### Admin Frontend 配置

```env
# 管理员前端 API 地址（容器内使用服务名）
VITE_API_BASE_URL=http://backend:8000/api/v1
```

> ⚠️ **说明**：所有 `VITE_` 前缀变量在前端构建阶段就会被写入静态资源，运行中的容器修改这些变量不会生效，如需变更必须重新构建镜像。

## `.env` 变量使用范围说明

| 变量分类 | 示例 | docker-compose 是否会读取 | 说明 |
| --- | --- | --- | --- |
| Compose 运行时变量 | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`, `ADMIN_FRONTEND_PORT`, `OUTPUT_DIR`, `OPENAI_*`, `ANTHROPIC_*`, `SUPER_ADMIN_*` 等 | ✅ | `docker-compose` 在启动容器时读取 `.env` 并把这些值通过 `${VAR}` 注入，对数据库、后端和端口映射即时生效。 |
| 前端构建变量 | `VITE_API_BASE_URL`（以及任何 `VITE_` 前缀变量） | ❌（运行期无效） | 只会在 **构建镜像** 时由 Vite 读取并写入静态资源，运行中的容器即使通过 compose 设置也不会重新生效，必须重新 `docker build` 对应前端镜像才会更新。 |

> ✅ 小结：`.env` 中的大部分变量（数据库、后端、端口、API Key 等）可以直接通过 `docker-compose up -d` 生效；只有 `VITE_` 相关变量需要重新构建前端镜像。

## 网络配置

所有服务在同一个 Docker 网络 `academic_workflow_network` 中，可以通过服务名互相访问：

- `postgres`：数据库服务
- `backend`：后端服务
- `frontend`：前端服务
- `admin_frontend`：管理员前端服务

## 数据持久化

### 数据库数据

PostgreSQL 数据存储在 Docker volume `postgres_data` 中，即使容器删除，数据也会保留。

**备份数据库**：
```bash
docker-compose exec postgres pg_dump -U postgres academic_workflow > backup.sql
```

**恢复数据库**：
```bash
docker-compose exec -T postgres psql -U postgres academic_workflow < backup.sql
```

### 应用数据

- **输出文件**：通过 `OUTPUT_DIR` 环境变量配置输出目录挂载路径（默认: `./output`）
  - 生成的文件会保存在宿主机的指定目录
  - 支持相对路径（如 `./output`）或绝对路径（如 `/data/researchflow/output` 或 `E:/data/output`）
  - 配置示例：
    ```env
    # 相对路径（相对于 docker-compose.yml 所在目录）
    OUTPUT_DIR=./output
    
    # Linux/macOS 绝对路径
    OUTPUT_DIR=/data/researchflow/output
    
    # Windows 绝对路径
    OUTPUT_DIR=E:/data/output
    ```
- **日志**：可以通过 `docker-compose logs` 查看，或配置日志驱动输出到文件

## 生产环境部署建议

### 1. 使用反向代理（Nginx/Traefik）

在生产环境中，建议使用 Nginx 或 Traefik 作为反向代理：

```nginx
# Nginx 配置示例
server {
    listen 80;
    server_name your-domain.com;

    # 前端
    location / {
        proxy_pass http://localhost:3000;
    }

    # 管理员前端
    location /admin {
        proxy_pass http://localhost:3001;
    }

    # 后端 API
    location /api {
        proxy_pass http://localhost:8000;
    }
}
```

### 2. 启用 HTTPS

使用 Let's Encrypt 或类似服务为域名配置 SSL 证书。

### 3. 配置防火墙

只开放必要的端口：
- 80/443：HTTP/HTTPS
- 22：SSH（如果需要）

### 4. 监控和日志

- 配置日志收集（如 ELK Stack）
- 设置监控告警（如 Prometheus + Grafana）
- 定期备份数据库

### 5. 资源限制

在 `docker-compose.yml` 中为每个服务配置资源限制：

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 1G
    reservations:
      cpus: '0.5'
      memory: 512M
```

### 6. 环境变量安全

- 使用 Docker secrets 或外部密钥管理服务
- 不要将 `.env` 文件提交到版本控制
- 定期轮换密钥和密码

## 常见问题

### 1. 数据库连接失败

**问题**：后端无法连接到数据库

**解决方案**：
- 检查 `POSTGRES_HOST` 是否设置为 `postgres`（Docker 服务名）
- 确认数据库服务已启动：`docker-compose ps`
- 查看数据库日志：`docker-compose logs postgres`
- 检查网络连接：`docker-compose exec backend ping postgres`

### 2. 前端无法访问后端 API

**问题**：前端页面显示 API 错误

**解决方案**：
- 检查 `VITE_API_BASE_URL` 配置是否正确
- 确认后端服务已启动：`docker-compose ps backend`
- 检查 CORS 配置（后端允许的源）
- 查看浏览器控制台和网络请求

### 3. 端口冲突

**问题**：端口已被占用

**解决方案**：
- 修改 `docker-compose.yml` 中的端口映射
- 或停止占用端口的其他服务

### 4. 构建失败

**问题**：`docker-compose build` 失败

**解决方案**：
- 检查 Dockerfile 语法
- 确认依赖文件存在（requirements.txt, package.json 等）
- 查看详细错误信息：`docker-compose build --no-cache`

### 5. 权限问题

**问题**：容器内无法写入文件

**解决方案**：
- 检查挂载目录的权限
- 确保 `output/` 目录存在且可写
- 在 Linux 上可能需要调整 SELinux 或 AppArmor 配置

## 更新部署

### 更新代码

```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker-compose build

# 重启服务
docker-compose up -d
```

### 仅更新特定服务

```bash
# 仅更新后端
docker-compose build backend
docker-compose up -d backend

# 仅更新前端
docker-compose build frontend
docker-compose up -d frontend
```

### 数据库迁移

如果数据库结构有变化，后端启动时会自动创建表。如果需要手动迁移：

```bash
# 进入后端容器
docker-compose exec backend bash

# 运行迁移脚本（如果有）
python scripts/migrate.py
```

## CI/CD 部署流程

结合 GitHub Actions 与 GHCR 可以实现“代码推送 → 自动构建镜像 → 服务器拉取镜像 → Docker Compose 启动”的流程。核心分为 CI（云端构建推送）和 CD（服务器拉取部署）两部分。

### 1. CI：GitHub Actions 构建并推送镜像

仓库内的 `.github/workflows/deploy.yml` workflow 会在 `main`/`master` 分支的 push 与 PR 触发。它会：

1. 使用 Buildx 构建根目录下的 Docker 镜像。
2. 利用 `docker/metadata-action` 自动生成 `latest`、分支名、PR、SemVer、以及带分支前缀的 `sha` 等多个 tag。
3. 在 push 场景下将镜像发布到 `ghcr.io/<owner>/<repo>:<tag>`，PR 仅构建不推送，供预检。

> **注意**  
> - 默认凭证是 `GITHUB_TOKEN`，可推送到 GHCR。  
> - 如需跨仓库拉取，可额外创建带 `read:packages` 权限的 PAT。

#### `registry`/`username`/`password` 的来源

workflow 中常见的登录片段如下：

```yaml
- name: Login to registry
  uses: docker/login-action@v3
  with:
    registry: ${{ env.REGISTRY }}
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

- `REGISTRY`（环境变量）  
  在 workflow `env:` 中设置，例如 `REGISTRY: ghcr.io/<owner>/<repo>`。若你推送到自建 Harbor、ACR 等镜像仓库，将该值替换为对应域名即可。
- `github.actor`  
  GitHub 自动注入的运行身份，通常是 `github-actions[bot]`。无需手动配置。
- `secrets.GITHUB_TOKEN`  
  每次 workflow 运行自动生成的短期 token，默认具备向当前仓库 GHCR 推送镜像的权限。  
  若推送到第三方 registry，请在仓库/组织的 Secrets 中新增凭证（如 `REGISTRY_PASSWORD`），并把 `password` 改为该 secret。
- **GHCR 额外步骤**：在仓库 Settings → Packages 中勾选 “Allow GitHub Actions to create and publish packages”，否则 `GITHUB_TOKEN` 无法推送。

#### 流程示意图

```
开发者 git push/PR
        │
        ▼
GitHub Actions（CI）
1. checkout
2. build & tag
3. push 到 GHCR（仅 push）
        │
        ▼
服务器（CD）
docker compose pull
docker compose up -d
```

#### 可选：使用 GitHub Actions 自动 SSH 部署

- `.github/workflows/deploy.yml` 现在包含 `deploy` job，会在 `main/master` push 成功构建镜像后，通过 `appleboy/ssh-action` 登录到服务器并执行 `docker pull && docker-compose up -d`。  
- 你需要在仓库 Secrets 中配置 `SSH_HOST`、`SSH_USERNAME`、`SSH_PRIVATE_KEY`、可选的 `SSH_PORT` 与 `DEPLOY_PATH`。CI 就会连接那台机器完成上线，相当于把原先“登录服务器执行 CD 命令”的步骤自动化。  
- 如果要管理多台服务器，可将 `host` 列表改成 `matrix`，或在脚本中遍历；仍建议在 `docs`/Runbook 中记录每台服务器的角色，便于排障。  
- SSH 自动部署依然依赖服务器本地的 `.env`、持久化目录与 `docker-compose.yml` 配置，请确保这些文件提前到位，Actions 不会上传它们。

### 2. CD：服务器端部署步骤

Actions 推送成功后，在服务器执行以下步骤完成上线：

0. **首次部署前的准备**
   - 安装 Docker Engine ≥ 20.10 及 Docker Compose v2（或 `docker compose` 插件）。
   - 创建标准部署目录，例如 `sudo mkdir -p /opt/academic-workflow`，该目录用于存放 `docker-compose*.yml`、`.env`、日志及数据挂载，更便于运维同步。
   - 为需要持久化的宿主机目录（`OUTPUT_DIR`、`postgres_data` 等）赋予写权限：`sudo chown -R <deploy-user>:<deploy-user> /opt/academic-workflow`.
   - 配置防火墙/安全组，开放 3000/3001/8000/5432（或 `.env` 中自定义的端口），并准备可选的反向代理或证书。

1. **准备 `.env` 文件（必须手动上传）**
   - 在本地根据 `.env.example` 填写真实密钥、数据库配置、端口等，不要提交到 Git。  
   - 首次部署或需要更新变量时手工复制到服务器，例如：
     ```bash
     scp .env user@your-server:/opt/academic-workflow/.env
     ```

2. **更新代码（或仅拉取镜像）**
   - 如果服务器通过 Git 获取项目：`git pull`。  
   - 或者只依赖 Compose 文件，可直接 `docker compose pull`。

3. **登录 GHCR（仅首次或 token 更新时）**
   ```bash
   echo <PAT_or_TOKEN> | docker login ghcr.io -u <github-username> --password-stdin
   ```
   - 使用 GitHub PAT（需 `read:packages`）或 `GITHUB_TOKEN` 的部署副本。

4. **拉取最新镜像**
   ```bash
   docker compose pull backend frontend admin_frontend
   ```
   - 如果 `docker-compose.cn.yml` 在国内服务器使用，记得加 `-f docker-compose.cn.yml`。

5. **启动/滚动更新**
   ```bash
   docker compose up -d --remove-orphans
   # 或
   docker compose -f docker-compose.cn.yml up -d --remove-orphans
   ```
   - Compose 会使用 `.env` 中的端口、密钥并启动全部服务。

6. **验证**
   - `docker compose ps` 查看容器状态。  
   - 访问 `http://<server>:3000`（前端）、`3001`（Admin）、`8000/docs`（API 文档）。  
   - 查看日志确保迁移/任务正常：`docker compose logs -f backend`.

#### 这个流程如何知道要部署到哪台服务器？

- CI 的职责仅是把镜像推到镜像仓库（GHCR、ACR 等），它不会直接连接任何服务器。  
- **真正决定部署目标的是你在哪台机器上执行 CD 命令**。当你 SSH 到 `prod-01` 并运行 `docker compose pull && docker compose up -d` 时，新镜像就会被拉取到 `prod-01`。换到 `prod-02` 重复命令，则 `prod-02` 同步更新。  
- 如果需要自动化多台服务器，可使用 Ansible、Terraform、ArgoCD、或在 GitHub Actions 中添加自托管 runner/SSH 步骤，在脚本里显式维护服务器列表。  
- 因此“推送到哪个服务器”并不是在 workflow 里写死的，而是由你的运维流程（登陆的主机、编排脚本或集群管理器）来决定。

### 部署前需要准备哪些信息？

- **`.env` 配置**：以 `.env.example` 为模板填写真实密钥、数据库、端口、云服务等；首次部署或变量调整时需手动上传到服务器（例如 `scp .env user@server:/opt/app/.env`）。  
- **镜像拉取凭证**：准备 GitHub `PAT`（需 `read:packages`）或部署专用的 `GITHUB_TOKEN`，在服务器上运行 `echo TOKEN | docker login ghcr.io -u <github-username> --password-stdin`。  
- **部署镜像的 tag**：默认使用 `latest`（默认分支），也可在 Actions 运行日志中查看并指定 `branch-sha`、`vX.Y.Z` 等 tag。  
- **Compose 文件选择**：确认服务器使用 `docker-compose.yml` 还是 `docker-compose.cn.yml`（国内镜像源版本），并据此选择 `docker compose` 命令参数。  
- **持久化挂载路径**：确保 `OUTPUT_DIR`、`postgres_data` 等宿主机目录存在且有写权限，Windows 环境需提供绝对路径如 `E:/data/output`。  
- **网络与端口规划**：提前确认 3000/3001/8000/5432 等端口未被占用，并配置所需的反向代理或防火墙规则。

### 3. 常见问题

- **`.env` 何时上传？**  
  在服务器第一次部署前就需要放置 `.env`；若变量有变动（如新 API Key），需重新上传覆盖。CI 不会处理 `.env`，避免泄露。
- **如何指定特定镜像 tag？**  
  `docker compose pull backend=ghcr.io/<owner>/<repo>:<tag>`（Compose v2 支持 `service=image:tag` 语法），或在 `docker-compose.yml` 中写死 tag。
- **多服务器部署**  
  每台服务器重复步骤 1~6；可用同一 GHCR 镜像，`.env` 根据环境调整。

通过该流程，GitHub 负责构建和发布，服务器上只需 `docker compose pull && up -d`，即可快速复用相同镜像实现一致部署。

## 性能优化

### 1. 使用多阶段构建

Dockerfile 已使用多阶段构建，减少镜像大小。

### 2. 启用缓存

构建时使用 Docker 层缓存，加快构建速度。

### 3. 数据库连接池

后端已配置连接池（pool_size=10, max_overflow=20），可根据负载调整。

### 4. 前端资源优化

- 启用 Gzip 压缩（Nginx 配置中已包含）
- 使用 CDN 加速静态资源
- 配置浏览器缓存

## 安全建议

1. **定期更新**：保持 Docker 镜像和依赖包最新
2. **最小权限**：容器以非 root 用户运行
3. **网络安全**：使用 Docker 网络隔离服务
4. **密钥管理**：使用密钥管理服务，不要硬编码密钥
5. **日志审计**：记录所有重要操作
6. **备份策略**：定期备份数据库和应用数据

## 故障排查

### 查看所有服务日志

```bash
docker-compose logs -f
```

### 查看特定服务日志

```bash
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

### 进入容器调试

```bash
# 进入后端容器
docker-compose exec backend bash

# 进入数据库容器
docker-compose exec postgres psql -U postgres -d academic_workflow
```

### 检查服务健康状态

```bash
# 查看服务状态
docker-compose ps

# 检查服务健康检查
docker inspect academic_workflow_backend | grep -A 10 Health
```

## 联系和支持

如有问题，请查看：
- 项目 README.md
- 数据库使用说明：README_DATABASE.md
- 重试机制说明：docs/retry_mechanism.md

