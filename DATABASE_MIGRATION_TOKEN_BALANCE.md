# Token余额功能数据库迁移说明

## 概述

本次更新为系统添加了Token余额管理功能：
- 每个用户初始拥有 **100万** Token
- 每次工作流执行完成后，会自动从用户余额中扣除使用的Token
- 允许用户欠费（余额可以为负数），确保工作流能够完整执行

## 数据库变更

### 新增字段

在 `users` 表中添加了新字段：
- **字段名**: `token_balance`
- **类型**: `INTEGER`
- **默认值**: `1000000` (100万)
- **是否允许NULL**: `否`

## 迁移步骤

### 方法1：使用迁移脚本（推荐）

运行迁移脚本自动添加字段：

```bash
python scripts/add_token_balance_column.py
```

此脚本会：
1. 检查 `users` 表是否存在 `token_balance` 列
2. 如果不存在，则添加该列，默认值为 1000000
3. 如果已存在，则跳过
4. 对于已存在的用户，如果 `token_balance` 为 NULL，则设置为 1000000

### 方法2：手动SQL迁移

如果使用PostgreSQL，可以手动执行以下SQL：

```sql
-- 添加 token_balance 列
ALTER TABLE users ADD COLUMN token_balance INTEGER DEFAULT 1000000 NOT NULL;

-- 更新已存在用户的 token_balance（如果为 NULL）
UPDATE users SET token_balance = 1000000 WHERE token_balance IS NULL;
```

### 方法3：重新创建表（会丢失数据）

如果数据库中没有重要数据，可以重新创建所有表：

```bash
python scripts/recreate_tables.py --all
```

**⚠️ 警告**: 此方法会删除所有表和数据！

## 验证迁移

迁移完成后，可以通过以下方式验证：

1. **检查数据库表结构**：
   ```sql
   \d users  -- PostgreSQL
   DESCRIBE users;  -- MySQL
   ```

2. **检查现有用户的余额**：
   ```sql
   SELECT id, username, token_balance FROM users;
   ```

3. **检查新创建的用户**：
   创建新用户后，检查其 `token_balance` 是否为 1000000

## 功能说明

### Token结算机制

1. **工作流执行过程中**：
   - Token使用会实时记录到 `token_usage` 表
   - 不会立即扣除用户余额

2. **工作流执行完成后**：
   - 系统会计算本次流程使用的总Token数
   - 从用户的 `token_balance` 中扣除
   - 允许余额为负数（欠费）

3. **Token余额显示**：
   - 前端Token使用统计界面会显示用户当前余额
   - 如果余额为负数，会显示"欠费"提示

### API端点

新增的API端点：
- `GET /api/v1/token-usage/balance` - 获取用户当前Token余额

更新的API端点：
- `GET /api/v1/token-usage/summary` - 现在返回结果中包含 `token_balance` 字段

## 注意事项

1. **现有用户**：
   - 迁移脚本会自动为所有现有用户设置初始余额为 1000000
   - 如果用户已有使用记录，余额不会自动调整（需要手动处理）

2. **新用户**：
   - 新创建的用户会自动获得 1000000 Token
   - 这是通过数据库模型的默认值实现的

3. **欠费处理**：
   - 系统允许用户欠费，不会阻止工作流执行
   - 前端会显示欠费提示，提醒用户充值

4. **数据一致性**：
   - Token使用记录存储在 `token_usage` 表中
   - 用户余额存储在 `users.token_balance` 字段中
   - 两者是独立的，余额是累计扣除的结果

## 回滚（如果需要）

如果需要回滚此功能，可以执行：

```sql
-- 删除 token_balance 列（会丢失余额数据）
ALTER TABLE users DROP COLUMN token_balance;
```

**⚠️ 警告**: 删除列会丢失所有余额数据！

## 问题排查

如果遇到问题：

1. **字段已存在错误**：
   - 运行迁移脚本会检查字段是否存在，如果已存在则跳过

2. **默认值不生效**：
   - 检查数据库表结构，确认默认值设置正确
   - 对于已存在的用户，可能需要手动更新

3. **余额显示不正确**：
   - 检查前端API调用是否正确
   - 检查后端返回的数据格式

## 联系支持

如有问题，请查看日志文件或联系技术支持。

