# 数据库重置指南

当您更改了数据库用户名或密码后，需要重新初始化数据库容器。

## 问题说明

PostgreSQL 容器在首次启动时会根据环境变量创建初始用户和数据库。如果数据卷已经存在（使用旧的用户名初始化），即使更改了环境变量，容器也不会重新创建用户。

## 解决方案

### 方法 1：使用重置脚本（推荐）

#### Linux/WSL 用户：
```bash
chmod +x scripts/reset_database.sh
./scripts/reset_database.sh
```

#### Windows PowerShell 用户：
```powershell
.\scripts\reset_database.ps1
```

### 方法 2：手动重置

1. **确保 `.env` 文件配置正确**

   如果还没有 `.env` 文件，请创建：
   ```bash
   cp .env.example .env
   ```

   然后编辑 `.env` 文件，确保数据库配置如下：
   ```env
   POSTGRES_USER=postgres_academic_workflow
   POSTGRES_PASSWORD=postgres_academic_workflow
   POSTGRES_DB=academic_workflow
   ```

2. **停止所有服务**
   ```bash
   docker-compose down
   ```

3. **删除数据库数据卷**
   ```bash
   docker volume rm academicdraftagentic_workflow_postgres_data
   ```

4. **重新启动服务**
   ```bash
   docker-compose up -d
   ```

5. **验证数据库连接**
   ```bash
   docker logs -f academic_workflow_backend
   ```

   应该看到类似以下信息，表示连接成功：
   ```
   INFO - Database connection successful
   ```

## 注意事项

⚠️ **重要警告**：
- 删除数据卷会**永久删除所有数据库数据**
- 如果数据库中有重要数据，请先备份
- 备份命令：`docker exec academic_workflow_db pg_dump -U postgres academic_workflow > backup.sql`

## 验证步骤

1. 检查数据库容器状态：
   ```bash
   docker ps | grep academic_workflow_db
   ```

2. 检查后端日志，确认没有认证错误：
   ```bash
   docker logs academic_workflow_backend | grep -i "authentication\|error\|failed"
   ```

3. 测试数据库连接：
   ```bash
   docker exec -it academic_workflow_db psql -U postgres_academic_workflow -d academic_workflow -c "SELECT version();"
   ```

## 常见问题

### Q: 执行脚本后仍然报错 "password authentication failed"
A: 确保 `.env` 文件中的配置已正确保存，然后重新执行重置脚本。

### Q: 如何保留现有数据？
A: 可以使用以下方法迁移数据：
1. 使用旧用户导出数据
2. 删除数据卷并重新初始化
3. 使用新用户导入数据

### Q: 数据卷名称是什么？
A: 默认情况下，Docker Compose 会创建名为 `{project_name}_postgres_data` 的卷。可以通过以下命令查看：
```bash
docker volume ls | grep postgres
```

