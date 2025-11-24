# Docker Compose 部署方案总结

## 已创建的文件

### 1. 核心配置文件

- **docker-compose.yml** - 完整的 Docker Compose 配置，包含所有服务
- **.env.example** - 环境变量配置示例文件（需要复制为 .env 并修改）

### 2. Dockerfile 文件

- **Dockerfile.backend** - 后端服务 Dockerfile
- **Dockerfile.frontend** - 前端服务 Dockerfile（多阶段构建）
- **Dockerfile.admin_frontend** - 管理员前端服务 Dockerfile（多阶段构建）

### 3. Nginx 配置文件

- **nginx.frontend.conf** - 前端 Nginx 配置（包含 API 代理）
- **nginx.admin_frontend.conf** - 管理员前端 Nginx 配置（包含 API 代理）

### 4. 启动脚本

- **docker-start.sh** - Linux/macOS 快速启动脚本
- **docker-start.bat** - Windows 快速启动脚本

### 5. 文档

- **docs/docker_deployment.md** - 完整的部署文档

## 服务架构

```
┌─────────────────────────────────────────────────┐
│              Docker Network                     │
│         academic_workflow_network               │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ Frontend │  │  Admin   │  │   Backend    │ │
│  │  :3000   │  │ Frontend │  │    :8000     │ │
│  │ (Nginx)  │  │  :3001   │  │  (FastAPI)   │ │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘ │
│       │             │                │         │
│       └─────────────┴────────────────┘         │
│                    │                           │
│              ┌─────▼─────┐                     │
│              │ PostgreSQL│                     │
│              │   :5432   │                     │
│              └───────────┘                     │
└─────────────────────────────────────────────────┘
```

## 部署步骤

### 1. 准备环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置必要的环境变量
```

### 2. 启动服务

**方式一：使用脚本（推荐）**
```bash
# Linux/macOS
./docker-start.sh

# Windows
docker-start.bat
```

**方式二：手动启动**
```bash
docker-compose build
docker-compose up -d
```

### 3. 访问服务

- 前端: http://localhost:3000
- 管理员前端: http://localhost:3001
- 后端 API: http://localhost:8000/docs

## 关键配置说明

### 环境变量

所有配置都在 `.env` 文件中，主要配置项：

1. **数据库配置**
   - `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB`

2. **Backend 配置**
   - `OPENAI_API_KEY`（必需）
   - `SECRET_KEY`（生产环境必须修改）
   - `SUPER_ADMIN_PASSWORD`（生产环境必须修改）

3. **Frontend 配置**
   - `VITE_API_BASE_URL`（默认 `/api/v1`，Nginx 会代理到后端）

### 网络配置

- 所有服务在同一个 Docker 网络 `academic_workflow_network` 中
- 服务间通过服务名访问（如 `backend:8000`、`postgres:5432`）
- 前端通过 Nginx 代理 `/api` 到后端

### 数据持久化

- **数据库数据**：Docker volume `postgres_data`
- **应用输出**：`./output` 目录挂载到容器

## 生产环境注意事项

1. **安全配置**
   - 修改所有默认密码和密钥
   - 配置防火墙规则
   - 启用 HTTPS

2. **性能优化**
   - 配置资源限制
   - 使用反向代理（Nginx/Traefik）
   - 配置日志收集和监控

3. **备份策略**
   - 定期备份数据库
   - 备份 `output/` 目录

## 常见问题

详见 `docs/docker_deployment.md` 中的"常见问题"章节。

## 下一步

1. 阅读完整的部署文档：`docs/docker_deployment.md`
2. 配置 `.env` 文件
3. 运行启动脚本
4. 访问服务并测试功能

