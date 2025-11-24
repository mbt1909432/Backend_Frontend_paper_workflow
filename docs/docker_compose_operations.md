# Docker Compose 运维架构文档

本文档详细说明 Docker Compose 部署架构、端口配置、Nginx 作用以及前端请求流程。

## 📋 目录

- [整体架构](#整体架构)
- [国内/国外镜像配置](#国内国外镜像配置)
- [端口配置详解](#端口配置详解)
- [Nginx 的作用](#nginx-的作用)
- [请求流程](#请求流程)
- [容器内部网络](#容器内部网络)
- [部署后的访问方式](#部署后的访问方式)
- [常见问题](#常见问题)

---

## 🏗️ 整体架构

系统采用 Docker Compose 编排，包含以下服务：

```
┌─────────────────────────────────────────────────────────────┐
│                      Docker Compose                          │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Frontend   │  │ Admin Frontend│  │   Backend    │     │
│  │  (Nginx)     │  │   (Nginx)     │  │  (FastAPI)   │     │
│  │   Port 3000  │  │   Port 3001   │  │   Port 8000  │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            │                                 │
│                    ┌───────▼────────┐                        │
│                    │   PostgreSQL   │                        │
│                    │   Port 5432    │                        │
│                    └────────────────┘                        │
│                                                              │
│              academic_workflow_network (Bridge)              │
└─────────────────────────────────────────────────────────────┘
```

### 服务说明

1. **Frontend** - 用户前端界面（React + Vite）
2. **Admin Frontend** - 管理员前端界面（React + Vite）
3. **Backend** - 后端 API 服务（FastAPI）
4. **PostgreSQL** - 数据库服务

---

## 🌐 国内/国外镜像配置

系统提供了两套 Docker 配置，分别适用于国内和国外服务器环境：

### 配置文件说明

| 配置类型 | 国外服务器 | 国内服务器 |
|---------|-----------|-----------|
| **Docker Compose** | `docker-compose.yml` | `docker-compose.cn.yml` |
| **Backend Dockerfile** | `Dockerfile.backend` | `Dockerfile.backend.cn` |
| **Frontend Dockerfile** | `Dockerfile.frontend` | `Dockerfile.frontend.cn` |
| **Admin Frontend Dockerfile** | `Dockerfile.admin_frontend` | `Dockerfile.admin_frontend.cn` |

### 国内镜像配置特点

国内镜像配置（`.cn` 后缀）使用以下国内镜像源，加速镜像拉取和依赖安装：

1. **Docker 镜像源**：
   - 使用中科大镜像：`docker.mirrors.ustc.edu.cn/library/`
   - 包括：Python、Node.js、Nginx、PostgreSQL 等基础镜像

2. **Python 包镜像源**：
   - 使用清华大学 PyPI 镜像：`https://pypi.tuna.tsinghua.edu.cn/simple`
   - 在 `Dockerfile.backend.cn` 中自动配置

3. **Node.js 包镜像源**：
   - 使用淘宝 npm 镜像：`https://registry.npmmirror.com`
   - 在 `Dockerfile.frontend.cn` 和 `Dockerfile.admin_frontend.cn` 中自动配置

4. **系统包镜像源**：
   - 使用阿里云 Debian 镜像源
   - 加速系统依赖包的安装

### 使用方法

#### 国外服务器（默认配置）

```bash
# 使用默认的 docker-compose.yml
docker-compose build
docker-compose up -d
```

#### 国内服务器（推荐）

```bash
# 使用国内镜像配置
docker-compose -f docker-compose.cn.yml build
docker-compose -f docker-compose.cn.yml up -d
```

### 镜像源对比

| 组件 | 国外配置 | 国内配置 |
|------|---------|---------|
| **PostgreSQL** | `postgres:15-alpine` | `docker.mirrors.ustc.edu.cn/library/postgres:15-alpine` |
| **Python** | `python:3.11-slim` | `docker.mirrors.ustc.edu.cn/library/python:3.11-slim` |
| **Node.js** | `node:18-alpine` | `docker.mirrors.ustc.edu.cn/library/node:18-alpine` |
| **Nginx** | `nginx:alpine` | `docker.mirrors.ustc.edu.cn/library/nginx:alpine` |
| **pip 源** | PyPI 官方 | 清华大学镜像 |
| **npm 源** | npm 官方 | 淘宝镜像 |

### 切换配置

如果需要在两种配置之间切换：

```bash
# 停止当前服务
docker-compose down
# 或
docker-compose -f docker-compose.cn.yml down

# 切换到另一种配置
docker-compose -f docker-compose.cn.yml build
docker-compose -f docker-compose.cn.yml up -d
```

### 注意事项

1. **环境变量文件**：两种配置使用相同的 `.env` 文件，无需修改
2. **数据卷**：两种配置使用相同的数据卷名称，切换时数据会保留
3. **网络**：两种配置使用相同的网络名称，可以无缝切换
4. **性能**：国内服务器使用国内镜像配置可以显著提升构建速度

### 验证镜像源

构建时可以查看日志确认使用的镜像源：

```bash
# 查看构建日志
docker-compose -f docker-compose.cn.yml build --progress=plain 2>&1 | grep -i "pulling\|mirror\|registry"
```

---

## 🔌 端口配置详解

### 对外暴露端口（Host → Container）

这些端口是服务器对外暴露的，用户通过浏览器访问：

| 服务 | 对外端口 | 容器内部端口 | 环境变量 | 默认值 | 说明 |
|------|---------|-------------|---------|--------|------|
| **Frontend** | `3000` | `80` | `FRONTEND_PORT` | `3000` | 用户前端访问端口 |
| **Admin Frontend** | `3001` | `80` | `ADMIN_FRONTEND_PORT` | `3001` | 管理员前端访问端口 |
| **Backend** | `8000` | `8000` | `BACKEND_PORT` | `8000` | 后端 API 直接访问端口（可选） |
| **PostgreSQL** | `5432` | `5432` | `POSTGRES_PORT` | `5432` | 数据库访问端口（仅内网） |

**📝 端口配置位置**：
- 端口配置在 **`.env`** 文件中设置（从 `.env.example` 复制）
- 在 `docker-compose.yml` 中使用：`${FRONTEND_PORT:-3000}` 格式
- 修改端口后需要重启服务：`docker-compose down && docker-compose up -d`

### 容器内部端口（Container → Container）

容器之间通过 Docker 网络通信，使用服务名作为主机名：

| 服务 | 容器内部端口 | 服务名（主机名） | 说明 |
|------|------------|----------------|------|
| **Backend** | `8000` | `backend` | 其他容器通过 `http://backend:8000` 访问 |
| **PostgreSQL** | `5432` | `postgres` | Backend 通过 `postgres:5432` 连接数据库 |
| **Frontend (Nginx)** | `80` | `frontend` | 容器内部 Nginx 监听 80 端口 |
| **Admin Frontend (Nginx)** | `80` | `admin_frontend` | 容器内部 Nginx 监听 80 端口 |

### 🔄 前端、Nginx 和后端的通信关系

**重要理解**：前端（React 应用）和 Nginx 的关系

1. **前端是静态文件**：
   - React 应用构建后生成 HTML、CSS、JavaScript 文件
   - 这些文件存储在 Nginx 容器的 `/usr/share/nginx/html` 目录
   - Nginx 作为**静态文件服务器**，提供这些文件给浏览器

2. **前端代码在浏览器中运行**：
   - 用户访问 `http://localhost:3000` 时，Nginx 返回 `index.html`
   - 浏览器加载并执行 JavaScript 代码（React 应用）
   - **前端代码在用户的浏览器中运行，不是在容器中运行**

3. **前端发起 API 请求**：
   - 前端 JavaScript 代码发起 API 请求（如 `fetch('/api/v1/chat')`）
   - 请求发送到**前端所在的域名和端口**（`http://localhost:3000/api/v1/chat`）
   - 浏览器自动处理相对路径，发送到同一个服务器

4. **Nginx 代理 API 请求到后端**：
   - Nginx 接收到 `/api` 开头的请求
   - 根据配置 `proxy_pass http://backend:8000`，转发到后端容器
   - 通过 Docker 网络，使用服务名 `backend` 访问后端

**通信流程图**：

```
┌─────────────────────────────────────────────────────────┐
│  用户浏览器（客户端）                                      │
│  ┌──────────────────────────────────────────────────┐   │
│  │  1. 访问前端页面                                   │   │
│  │     GET http://localhost:3000/                   │   │
│  │                                                  │   │
│  │  2. 加载 React 应用（HTML/CSS/JS）                │   │
│  │     - index.html                                 │   │
│  │     - main.js                                    │   │
│  │     - style.css                                  │   │
│  │                                                  │   │
│  │  3. React 应用在浏览器中运行                      │   │
│  │     - 用户交互                                   │   │
│  │     - 发起 API 请求                              │   │
│  │       fetch('/api/v1/chat')                      │   │
│  │       ↓                                          │   │
│  │       GET http://localhost:3000/api/v1/chat      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                    ↓ HTTP 请求
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Frontend Container (Nginx)                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Nginx 监听 80 端口                               │   │
│  │                                                  │   │
│  │  情况 1: 请求静态文件（/、/index.html、/main.js）│   │
│  │    → 返回 /usr/share/nginx/html 中的文件         │   │
│  │                                                  │   │
│  │  情况 2: 请求 API（/api/*）                      │   │
│  │    → 匹配 location /api 规则                     │   │
│  │    → proxy_pass http://backend:8000              │   │
│  │    → 转发到后端容器                               │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                    ↓ Docker 网络通信
                    ↓ http://backend:8000/api/v1/chat
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Backend Container (FastAPI)                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  FastAPI 监听 8000 端口                          │   │
│  │  - 处理 API 请求                                 │   │
│  │  - 连接数据库                                    │   │
│  │  - 返回 JSON 响应                                │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                    ↓ 数据库查询
                    ↓ postgres:5432
                    ↓
┌─────────────────────────────────────────────────────────┐
│  PostgreSQL Container                                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  PostgreSQL 监听 5432 端口                       │   │
│  │  - 存储数据                                      │   │
│  │  - 返回查询结果                                  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**关键点总结**：

- ✅ **前端是静态文件**：由 Nginx 提供，存储在容器中
- ✅ **前端代码在浏览器运行**：不在容器中运行，在用户浏览器中执行
- ✅ **Nginx 是反向代理**：接收浏览器请求，转发 API 请求到后端
- ✅ **Nginx 和后端通过 Docker 网络通信**：使用服务名 `backend:8000`
- ✅ **同域部署**：前端和 API 在同一域名下，避免跨域问题

### 端口映射示例

```yaml
# docker-compose.yml 中的端口映射
ports:
  - "${FRONTEND_PORT:-3000}:80"        # 外部 3000 → 容器内 80
  - "${ADMIN_FRONTEND_PORT:-3001}:80"  # 外部 3001 → 容器内 80
  - "${BACKEND_PORT:-8000}:8000"       # 外部 8000 → 容器内 8000
  - "${POSTGRES_PORT:-5432}:5432"      # 外部 5432 → 容器内 5432
```

**格式说明**：`外部端口:容器内部端口`

### 如何修改端口？

1. **编辑 `.env` 文件**（如果不存在，从 `.env.example` 复制）：
   ```bash
   # 复制示例文件
   cp .env.example .env
   
   # 编辑 .env 文件，修改端口
   FRONTEND_PORT=8080          # 修改前端端口为 8080
   ADMIN_FRONTEND_PORT=8081    # 修改管理员前端端口为 8081
   BACKEND_PORT=9000           # 修改后端端口为 9000
   POSTGRES_PORT=5433          # 修改数据库端口为 5433
   ```

2. **重启服务**：
   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. **验证端口**：
   ```bash
   docker-compose ps
   ```

---

## 🌐 Nginx 的作用

### 为什么需要 Nginx？

前端应用（React）是**单页应用（SPA）**，需要 Nginx 提供以下功能：

#### 1. **静态文件服务**
- 提供 HTML、CSS、JavaScript 等静态资源
- 前端构建后的文件存放在 `/usr/share/nginx/html`

#### 2. **API 反向代理**
- 将前端的 `/api/*` 请求转发到后端服务
- 解决跨域问题（同域部署）
- 统一入口，简化前端配置

#### 3. **SPA 路由支持**
- React Router 使用客户端路由
- 刷新页面时，Nginx 需要返回 `index.html` 而不是 404
- 配置：`try_files $uri $uri/ /index.html;`

#### 4. **性能优化**
- **Gzip 压缩**：减少传输数据量
- **静态资源缓存**：设置长期缓存（1年）
- **安全头**：添加 XSS、CSRF 防护头

### Nginx 配置解析

#### 前端 Nginx 配置（`nginx.frontend.conf`）

```nginx
server {
    listen 80;  # 容器内部监听 80 端口
    server_name localhost;
    root /usr/share/nginx/html;  # 静态文件目录
    index index.html;

    # API 代理：将 /api 请求转发到后端
    location /api {
        proxy_pass http://backend:8000;  # 使用服务名访问后端
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SPA 路由支持：所有请求都返回 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

**关键点**：
- `proxy_pass http://backend:8000` - 使用 Docker 服务名 `backend`，不是 `localhost`
- `try_files $uri $uri/ /index.html` - 支持前端路由

---

## 🔄 请求流程

### 场景 1：用户访问前端页面

```
用户浏览器
    ↓
    GET http://your-server.com:3000/
    ↓
服务器端口 3000 (Docker Host)
    ↓
Frontend 容器端口 80 (Nginx)
    ↓
Nginx 返回 index.html
    ↓
浏览器加载 React 应用
```

### 场景 2：前端调用 API（推荐方式）

```
用户浏览器
    ↓
    GET http://your-server.com:3000/api/v1/chat
    ↓
服务器端口 3000 (Docker Host)
    ↓
Frontend 容器端口 80 (Nginx)
    ↓
Nginx 匹配 /api 规则
    ↓
反向代理到 http://backend:8000/api/v1/chat
    ↓
Backend 容器处理请求
    ↓
返回响应给 Nginx
    ↓
Nginx 返回给浏览器
```

**为什么这样设计？**
- ✅ 同域部署，无跨域问题
- ✅ 前端只需配置相对路径 `/api/v1`
- ✅ 统一入口，便于管理

### 场景 3：直接访问后端 API（可选）

```
用户/工具
    ↓
    GET http://your-server.com:8000/api/v1/chat
    ↓
服务器端口 8000 (Docker Host)
    ↓
Backend 容器端口 8000 (FastAPI)
    ↓
直接处理请求
```

**使用场景**：
- API 测试工具（Postman、curl）
- 第三方系统集成
- 开发调试

---

## 🌍 容器内部网络

Docker Compose 创建了一个**桥接网络**（Bridge Network）：

```yaml
networks:
  academic_workflow_network:
    driver: bridge
```

### 网络特性

1. **服务发现**：容器可以通过服务名互相访问
   - `backend:8000` - 访问后端
   - `postgres:5432` - 访问数据库
   - `frontend:80` - 访问前端（通常不需要）

2. **隔离性**：容器之间可以通信，但外部无法直接访问（除非映射端口）

3. **DNS 解析**：Docker 内置 DNS，自动解析服务名

### 网络通信示例

```python
# Backend 连接数据库
POSTGRES_HOST = "postgres"  # 使用服务名，不是 localhost
POSTGRES_PORT = 5432

# Nginx 代理到后端
proxy_pass http://backend:8000;  # 使用服务名
```

---

## 🚀 部署后的访问方式

### 假设部署到服务器：`192.168.1.100` 或 `your-domain.com`

#### 1. **用户前端访问**

```
http://192.168.1.100:3000
或
http://your-domain.com:3000
```

**前端请求流程**：
- 用户打开页面：`http://your-domain.com:3000/`
- 前端 JavaScript 发起 API 请求：`/api/v1/chat`
- 浏览器自动转换为：`http://your-domain.com:3000/api/v1/chat`
- Nginx 接收请求，转发到 `http://backend:8000/api/v1/chat`
- 后端处理并返回响应

#### 2. **管理员前端访问**

```
http://192.168.1.100:3001
或
http://your-domain.com:3001
```

#### 3. **后端 API 直接访问（可选）**

```
http://192.168.1.100:8000/api/v1/chat
或
http://your-domain.com:8000/api/v1/chat
```

### 前端 API 配置

前端代码中的 API 配置（`frontend/src/services/api.ts`）：

```typescript
// 支持环境变量配置，默认使用相对路径
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
```

**说明**：
- 默认值 `/api/v1` 是**相对路径**，会自动使用当前域名和端口
- 如果部署时前端和后端不在同一域名，可以通过环境变量 `VITE_API_BASE_URL` 指定完整 URL

### 构建时配置 API 地址

在 `docker-compose.yml` 中：

```yaml
frontend:
  build:
    args:
      - VITE_API_BASE_URL=${VITE_API_BASE_URL:-/api/v1}
```

**推荐配置**：
- **同域部署**（推荐）：`VITE_API_BASE_URL=/api/v1`（默认值）
- **跨域部署**：`VITE_API_BASE_URL=http://api.your-domain.com:8000/api/v1`

---

## 📊 完整请求流程图

```
┌─────────────┐
│  用户浏览器  │
└──────┬──────┘
       │
       │ 1. GET http://your-domain.com:3000/
       ↓
┌─────────────────────────────────────┐
│  Docker Host (服务器)                │
│  Port 3000 (对外暴露)                │
└──────┬──────────────────────────────┘
       │
       │ 2. 端口映射 3000 → 80
       ↓
┌─────────────────────────────────────┐
│  Frontend Container                 │
│  ┌──────────────────────────────┐   │
│  │  Nginx (Port 80)             │   │
│  │  - 返回 index.html           │   │
│  │  - 提供静态资源              │   │
│  └──────────────────────────────┘   │
└──────┬──────────────────────────────┘
       │
       │ 3. 前端 JS 发起请求: /api/v1/chat
       │    浏览器转换为: http://your-domain.com:3000/api/v1/chat
       ↓
┌─────────────────────────────────────┐
│  Frontend Container (Nginx)         │
│  ┌──────────────────────────────┐   │
│  │  location /api {             │   │
│  │    proxy_pass                │   │
│  │    http://backend:8000       │   │
│  │  }                           │   │
│  └──────┬───────────────────────┘   │
└─────────┼───────────────────────────┘
          │
          │ 4. Docker 网络通信
          │    http://backend:8000/api/v1/chat
          ↓
┌─────────────────────────────────────┐
│  Backend Container                  │
│  ┌──────────────────────────────┐   │
│  │  FastAPI (Port 8000)         │   │
│  │  - 处理 API 请求             │   │
│  │  - 连接数据库                │   │
│  └──────┬───────────────────────┘   │
└─────────┼───────────────────────────┘
          │
          │ 5. 数据库查询
          │    postgres:5432
          ↓
┌─────────────────────────────────────┐
│  PostgreSQL Container               │
│  ┌──────────────────────────────┐   │
│  │  PostgreSQL (Port 5432)      │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
```

---

## ❓ 常见问题

### Q0: 前端和 Nginx 之间如何通信？Nginx 和后端如何通信？

**A**: 这是两个不同的通信场景：

#### 1. **前端和 Nginx 的通信**

- **前端是静态文件**：React 应用构建后生成 HTML、CSS、JavaScript 文件，存储在 Nginx 容器的 `/usr/share/nginx/html` 目录
- **Nginx 提供静态文件**：当用户访问 `http://localhost:3000/` 时，Nginx 返回 `index.html` 和相关的 JS/CSS 文件
- **前端代码在浏览器运行**：浏览器加载并执行 JavaScript 代码，React 应用在**用户的浏览器中运行**，不是在容器中运行
- **前端发起 API 请求**：前端 JavaScript 代码发起请求（如 `fetch('/api/v1/chat')`），浏览器自动将相对路径转换为 `http://localhost:3000/api/v1/chat`，发送到 Nginx

**总结**：前端和 Nginx 的通信是**HTTP 请求**，通过浏览器作为中介。

#### 2. **Nginx 和后端的通信**

- **Nginx 作为反向代理**：当 Nginx 接收到 `/api` 开头的请求时，根据配置 `proxy_pass http://backend:8000`，将请求转发到后端容器
- **通过 Docker 网络通信**：Nginx 容器和后端容器在同一个 Docker 网络 `academic_workflow_network` 中，可以通过服务名 `backend` 访问后端
- **使用服务名而非 IP**：Docker 内置 DNS 解析，`backend:8000` 会自动解析为后端容器的 IP 地址

**总结**：Nginx 和后端的通信是**Docker 内部网络通信**，使用服务名 `backend:8000`。

**完整流程**：
```
浏览器 → HTTP → Nginx (端口 3000→80) → Docker 网络 → Backend (backend:8000)
```

### Q1: 为什么前端不直接连接后端，而是通过 Nginx？

**A**: 
1. **解决跨域问题**：同域部署，浏览器不会阻止请求
2. **简化配置**：前端只需配置相对路径 `/api/v1`
3. **统一入口**：便于添加认证、限流等中间件
4. **性能优化**：Nginx 可以缓存、压缩响应

### Q2: 前端请求打到哪里？

**A**: 
- **默认情况**：前端请求使用相对路径 `/api/v1`，会发送到**前端所在的域名和端口**
- **示例**：如果前端在 `http://your-domain.com:3000`，请求会发送到 `http://your-domain.com:3000/api/v1/...`
- **Nginx 代理**：Nginx 接收到 `/api` 请求后，自动转发到 `http://backend:8000`

### Q3: 可以去掉 Nginx，让前端直接连接后端吗？

**A**: 
- **可以**，但需要：
  1. 配置后端 CORS，允许前端域名跨域
  2. 前端配置完整 API URL：`http://your-domain.com:8000/api/v1`
  3. 前端需要支持直接访问后端（开发环境通常这样）

**推荐**：保留 Nginx，架构更清晰，性能更好。

### Q4: 如何修改端口？

**A**: 
在 `.env` 文件中修改：

```bash
FRONTEND_PORT=8080          # 修改前端端口为 8080
ADMIN_FRONTEND_PORT=8081    # 修改管理员前端端口为 8081
BACKEND_PORT=9000           # 修改后端端口为 9000
```

然后重启服务：
```bash
docker-compose down
docker-compose up -d
```

### Q5: 生产环境如何配置域名？

**A**: 
1. **使用反向代理**（推荐）：
   - 在服务器上安装 Nginx 或 Traefik
   - 配置域名：`frontend.your-domain.com` → `localhost:3000`
   - 配置域名：`api.your-domain.com` → `localhost:8000`

2. **修改前端 API 配置**：
   ```bash
   VITE_API_BASE_URL=https://api.your-domain.com/api/v1
   ```

3. **配置 HTTPS**：使用 Let's Encrypt 证书

### Q6: 容器之间如何通信？

**A**: 
- 使用 **Docker 服务名**作为主机名
- 示例：`http://backend:8000`、`postgres:5432`
- Docker 内置 DNS 自动解析服务名

### Q7: 为什么后端也暴露 8000 端口？

**A**: 
- **可选暴露**：主要用于开发调试、API 测试工具
- **生产环境**：可以移除端口映射，只通过 Nginx 访问
- **安全考虑**：如果不需要直接访问，可以在 `docker-compose.yml` 中注释掉端口映射

---

## 📝 总结

### 关键要点

1. **端口映射**：`外部端口:容器内部端口`
2. **Nginx 作用**：静态文件服务 + API 反向代理 + SPA 路由支持
3. **请求流程**：浏览器 → 前端 Nginx → 后端 FastAPI → PostgreSQL
4. **网络通信**：容器之间使用服务名（如 `backend:8000`）
5. **前端配置**：默认使用相对路径 `/api/v1`，通过 Nginx 代理到后端

### 部署检查清单

- [ ] 确认所有端口未被占用
- [ ] 配置 `.env` 文件（特别是密钥和密码）
- [ ] 检查防火墙规则（开放 3000、3001、8000 端口）
- [ ] 验证容器网络连通性
- [ ] 测试前端访问和 API 调用
- [ ] 配置域名和 HTTPS（生产环境）

---

**文档版本**：v1.0  
**最后更新**：2024-01-XX

