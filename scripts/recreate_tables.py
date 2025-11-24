"""
重新创建数据库表的脚本

使用方法：
1. 删除所有表并重新创建（会丢失所有数据）：
   python scripts/recreate_tables.py --all

2. 只删除 tasks 表并重新创建（保留其他表的数据）：
   python scripts/recreate_tables.py --table tasks

3. 交互式选择：
   python scripts/recreate_tables.py
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from app.db.database import engine, Base
from app.db.models import User, Session, Task, TokenUsage
from app.utils.logger import logger


def drop_all_tables():
    """删除所有表"""
    logger.warning("⚠️  警告：将删除所有数据库表，所有数据将丢失！")
    
    with engine.connect() as conn:
        # 获取所有表名
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if not tables:
            logger.info("数据库中没有表，无需删除")
            return
        
        logger.info(f"找到以下表：{', '.join(tables)}")
        
        # 删除所有表（按依赖关系顺序）
        # 先删除有外键的表
        for table_name in ['tasks', 'token_usage', 'sessions']:
            if table_name in tables:
                logger.info(f"删除表: {table_name}")
                conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
        
        # 删除 users 表
        if 'users' in tables:
            logger.info("删除表: users")
            conn.execute(text('DROP TABLE IF EXISTS "users" CASCADE'))
        
        conn.commit()
        logger.info("✅ 所有表已删除")


def drop_table(table_name: str):
    """删除指定表"""
    logger.warning(f"⚠️  警告：将删除表 '{table_name}'，该表的所有数据将丢失！")
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        if table_name not in tables:
            logger.info(f"表 '{table_name}' 不存在，无需删除")
            return
        
        logger.info(f"删除表: {table_name}")
        conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
        conn.commit()
        logger.info(f"✅ 表 '{table_name}' 已删除")


def create_all_tables():
    """创建所有表"""
    logger.info("开始创建数据库表...")
    
    try:
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("✅ 所有表已成功创建")
        
        # 显示创建的表
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"已创建的表：{', '.join(tables)}")
        
    except Exception as e:
        logger.error(f"❌ 创建表时出错: {e}")
        raise


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="重新创建数据库表")
    parser.add_argument(
        "--all",
        action="store_true",
        help="删除所有表并重新创建（会丢失所有数据）"
    )
    parser.add_argument(
        "--table",
        type=str,
        help="只删除指定表并重新创建（例如: tasks）"
    )
    
    args = parser.parse_args()
    
    if args.all:
        # 删除所有表并重新创建
        response = input("⚠️  确认删除所有表并重新创建？这将丢失所有数据！(yes/no): ")
        if response.lower() != 'yes':
            logger.info("操作已取消")
            return
        
        drop_all_tables()
        create_all_tables()
        
    elif args.table:
        # 只删除指定表并重新创建
        table_name = args.table.lower()
        valid_tables = ['tasks', 'users', 'sessions', 'token_usage']
        
        if table_name not in valid_tables:
            logger.error(f"❌ 无效的表名: {table_name}")
            logger.info(f"有效的表名: {', '.join(valid_tables)}")
            return
        
        response = input(f"⚠️  确认删除表 '{table_name}' 并重新创建？这将丢失该表的所有数据！(yes/no): ")
        if response.lower() != 'yes':
            logger.info("操作已取消")
            return
        
        drop_table(table_name)
        create_all_tables()
        
    else:
        # 交互式选择
        print("\n请选择操作：")
        print("1. 删除所有表并重新创建（会丢失所有数据）")
        print("2. 只删除 tasks 表并重新创建（保留其他表的数据）")
        print("3. 取消")
        
        choice = input("\n请输入选项 (1/2/3): ").strip()
        
        if choice == '1':
            response = input("⚠️  确认删除所有表并重新创建？这将丢失所有数据！(yes/no): ")
            if response.lower() == 'yes':
                drop_all_tables()
                create_all_tables()
            else:
                logger.info("操作已取消")
        
        elif choice == '2':
            response = input("⚠️  确认删除表 'tasks' 并重新创建？这将丢失该表的所有数据！(yes/no): ")
            if response.lower() == 'yes':
                drop_table('tasks')
                create_all_tables()
            else:
                logger.info("操作已取消")
        
        else:
            logger.info("操作已取消")


if __name__ == "__main__":
    main()

