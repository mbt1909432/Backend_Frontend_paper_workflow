"""
为 users 表添加 token_balance 字段的迁移脚本

使用方法：
python scripts/add_token_balance_column.py

此脚本会：
1. 检查 users 表是否存在 token_balance 列
2. 如果不存在，则添加该列，默认值为 1000000（100万）
3. 如果已存在，则跳过
4. 对于已存在的用户，如果 token_balance 为 NULL，则设置为 1000000
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from app.db.database import engine
from app.utils.logger import logger


def add_token_balance_column():
    """为 users 表添加 token_balance 列"""
    logger.info("开始检查 users 表...")
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if 'users' not in tables:
            logger.error("❌ users 表不存在，请先创建数据库表")
            return False
        
        # 检查列是否存在
        columns = [col['name'] for col in inspector.get_columns('users')]
        
        if 'token_balance' in columns:
            logger.info("✅ token_balance 列已存在")
            
            # 检查是否有 NULL 值，如果有则更新为默认值
            result = conn.execute(text(
                "SELECT COUNT(*) FROM users WHERE token_balance IS NULL"
            )).scalar()
            
            if result > 0:
                logger.info(f"发现 {result} 个用户的 token_balance 为 NULL，正在更新为默认值 1000000...")
                conn.execute(text(
                    "UPDATE users SET token_balance = 1000000 WHERE token_balance IS NULL"
                ))
                conn.commit()
                logger.info("✅ 已更新所有 NULL 值为默认值")
            
            return True
        
        # 添加列
        logger.info("正在添加 token_balance 列...")
        try:
            # 对于 PostgreSQL，使用 ALTER TABLE ADD COLUMN
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN token_balance INTEGER DEFAULT 1000000 NOT NULL"
            ))
            conn.commit()
            logger.info("✅ token_balance 列已成功添加")
            
            # 更新已存在用户的 token_balance（如果为 NULL）
            result = conn.execute(text(
                "SELECT COUNT(*) FROM users WHERE token_balance IS NULL"
            )).scalar()
            
            if result > 0:
                logger.info(f"发现 {result} 个用户的 token_balance 为 NULL，正在更新为默认值...")
                conn.execute(text(
                    "UPDATE users SET token_balance = 1000000 WHERE token_balance IS NULL"
                ))
                conn.commit()
                logger.info("✅ 已更新所有 NULL 值为默认值")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 添加列时出错: {e}")
            conn.rollback()
            return False


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("Token Balance 字段迁移脚本")
    logger.info("=" * 60)
    
    success = add_token_balance_column()
    
    if success:
        logger.info("=" * 60)
        logger.info("✅ 迁移完成！")
        logger.info("=" * 60)
    else:
        logger.error("=" * 60)
        logger.error("❌ 迁移失败！")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

