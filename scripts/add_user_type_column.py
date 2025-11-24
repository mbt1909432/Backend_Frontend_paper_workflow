"""
数据库迁移脚本：为User表添加user_type字段
为现有用户设置默认值：backend
支持 SQLite 和 PostgreSQL
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.db.database import SessionLocal, engine
from app.utils.logger import logger


def check_column_exists(conn, db_type):
    """检查user_type列是否已存在"""
    if db_type == 'sqlite':
        # SQLite: 检查表结构
        result = conn.execute(text("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='users'
        """))
        table_sql = result.fetchone()
        if table_sql and 'user_type' in table_sql[0]:
            return True
        return False
    elif db_type == 'postgresql':
        # PostgreSQL: 检查information_schema
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='user_type'
        """))
        return result.fetchone() is not None
    else:
        # 其他数据库类型，尝试使用SQLAlchemy的inspect
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('users')]
        return 'user_type' in columns


def migrate():
    """执行迁移"""
    db = SessionLocal()
    try:
        logger.info("开始迁移：添加user_type字段...")
        
        # 检测数据库类型
        db_type = engine.dialect.name
        logger.info(f"检测到数据库类型: {db_type}")
        
        with engine.connect() as conn:
            # 检查字段是否已存在
            if check_column_exists(conn, db_type):
                logger.info("user_type字段已存在，跳过迁移")
                return
            
            # 添加user_type字段
            logger.info("添加user_type字段...")
            
            if db_type == 'sqlite':
                # SQLite: 可以直接添加带默认值和NOT NULL的列
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN user_type VARCHAR(20) DEFAULT 'backend' NOT NULL
                """))
                conn.commit()
            elif db_type == 'postgresql':
                # PostgreSQL: 需要分步执行
                # 1. 先添加列（带默认值，允许NULL）
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN user_type VARCHAR(20) DEFAULT 'backend'
                """))
                conn.commit()
                
                # 2. 为现有NULL值设置默认值
                conn.execute(text("""
                    UPDATE users 
                    SET user_type = 'backend' 
                    WHERE user_type IS NULL
                """))
                conn.commit()
                
                # 3. 设置NOT NULL约束
                conn.execute(text("""
                    ALTER TABLE users 
                    ALTER COLUMN user_type SET NOT NULL
                """))
                conn.commit()
            else:
                # 其他数据库类型，尝试通用语法
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN user_type VARCHAR(20) DEFAULT 'backend'
                """))
                conn.commit()
                
                # 为现有用户设置默认值
                conn.execute(text("""
                    UPDATE users 
                    SET user_type = 'backend' 
                    WHERE user_type IS NULL OR user_type = ''
                """))
                conn.commit()
            
            logger.info("user_type字段添加成功")
            
            # 为现有用户设置默认值（PostgreSQL已经在上面处理了）
            if db_type != 'postgresql':
                logger.info("为现有用户设置默认user_type值...")
                conn.execute(text("""
                    UPDATE users 
                    SET user_type = 'backend' 
                    WHERE user_type IS NULL OR user_type = ''
                """))
                conn.commit()
                logger.info("现有用户的user_type已设置为'backend'")
            
        logger.info("迁移完成！")
        
    except Exception as e:
        logger.error(f"迁移失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

