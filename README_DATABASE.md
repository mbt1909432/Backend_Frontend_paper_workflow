# 数据库和认证系统使用说明

## 快速开始

### 1. 启动PostgreSQL数据库

使用Docker Compose启动数据库：

```bash
docker-compose up -d
```

数据库将在 `localhost:5432` 启动。

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并配置：

```bash
cp .env.example .env
```

重要配置项：
- `POSTGRES_USER`: 数据库用户名（默认：postgres）
- `POSTGRES_PASSWORD`: 数据库密码（默认：postgres）
- `POSTGRES_DB`: 数据库名称（默认：academic_workflow）
- `POSTGRES_HOST`: 数据库主机（默认：localhost）
- `POSTGRES_PORT`: 数据库端口（默认：5432）
- `SECRET_KEY`: JWT密钥（生产环境必须修改）
- `SUPER_ADMIN_USERNAME`: 超级管理员用户名（默认：admin）
- `SUPER_ADMIN_PASSWORD`: 超级管理员密码（默认：admin123，生产环境必须修改）

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动后端服务

```bash
python start_server.py
```

或者：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

数据库表会在应用启动时自动创建。

### 5. 启动前端

#### 业务前端（端口3000）

```bash
cd frontend
npm install
npm run dev
```

访问：http://localhost:3000

#### 管理员前端（端口3001）

```bash
cd admin_frontend
npm install
npm run dev
```

访问：http://localhost:3001

## 使用说明

### 登录系统

1. **超级管理员登录**
   - 用户名：在 `.env` 中配置的 `SUPER_ADMIN_USERNAME`（默认：admin）
   - 密码：在 `.env` 中配置的 `SUPER_ADMIN_PASSWORD`（默认：admin123）
   - 超级管理员可以登录业务前端和管理员前端

2. **普通用户登录**
   - 用户名和密码由管理员在管理员前端创建
   - 普通用户只能登录业务前端

### 管理员功能

访问管理员前端（http://localhost:3001），使用超级管理员账号登录后可以：

1. **创建用户**：创建新的普通用户账号
2. **编辑用户**：修改用户密码或启用/禁用用户
3. **删除用户**：删除普通用户（不能删除超级管理员）

### 业务功能

访问业务前端（http://localhost:3000），使用任何有效账号登录后可以使用所有业务功能。

## API端点

### 认证端点

- `POST /api/v1/auth/login` - 用户登录
- `GET /api/v1/auth/me` - 获取当前用户信息（需要认证）

### 管理员端点（需要管理员权限）

- `GET /api/v1/admin/users` - 列出所有用户
- `GET /api/v1/admin/users/{user_id}` - 获取用户信息
- `POST /api/v1/admin/users` - 创建用户
- `PUT /api/v1/admin/users/{user_id}` - 更新用户
- `DELETE /api/v1/admin/users/{user_id}` - 删除用户

### 业务端点

所有业务端点（workflow、agent等）现在支持可选的认证。如果提供了认证token，系统会记录用户信息。

## 数据库模型

### User（用户）
- `id`: 用户ID（UUID）
- `username`: 用户名（唯一）
- `password_hash`: 密码哈希
- `is_admin`: 是否为管理员
- `is_active`: 是否启用
- `created_at`: 创建时间
- `updated_at`: 更新时间

### Session（会话）
- `id`: 会话ID（UUID）
- `session_id`: 会话标识符（唯一）
- `user_id`: 所属用户ID
- `created_at`: 创建时间
- `updated_at`: 更新时间

### Task（任务）
- `id`: 任务ID（UUID）
- `task_id`: 任务标识符（唯一）
- `user_id`: 所属用户ID
- `session_id`: 所属会话ID（可选）
- `document`: 文档内容
- `user_info`: 用户信息
- `status`: 任务状态（pending, running, completed, failed）
- `progress`: 进度（0-100）
- `result_data`: 结果数据（JSON）
- `created_at`: 创建时间
- `updated_at`: 更新时间
- `completed_at`: 完成时间

## 注意事项

1. **生产环境配置**
   - 必须修改 `SECRET_KEY` 为强随机字符串
   - 必须修改 `SUPER_ADMIN_PASSWORD` 为强密码
   - 建议修改数据库密码
   - 建议限制CORS允许的域名

2. **数据库备份**
   - 定期备份PostgreSQL数据库
   - 可以使用 `docker-compose exec postgres pg_dump -U postgres academic_workflow > backup.sql` 进行备份

3. **安全建议**
   - 使用HTTPS
   - 定期更新依赖包
   - 监控异常登录尝试
   - 限制管理员账号的访问IP（可选）

