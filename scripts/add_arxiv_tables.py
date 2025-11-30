"""
为数据库创建 arXiv 相关的新表的脚本。

使用方式：
    python scripts/add_arxiv_tables.py

脚本行为：
1. 检查 arxiv_crawl_runs、arxiv_papers 是否存在
2. 如果不存在则依据 SQLAlchemy 模型创建
3. 两张表都会在一个事务中创建，失败会回滚
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.database import engine
from app.db.models import ArxivCrawlRun, ArxivPaper
from app.utils.logger import logger


def ensure_tables():
    """检查并创建 arXiv 相关表"""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    missing_tables = []
    if ArxivCrawlRun.__tablename__ not in tables:
        missing_tables.append(ArxivCrawlRun.__table__)
    if ArxivPaper.__tablename__ not in tables:
        missing_tables.append(ArxivPaper.__table__)

    if not missing_tables:
        logger.info("✅ arxiv_crawl_runs 与 arxiv_papers 均已存在，无需更新")
        return True

    logger.info("检测到以下表缺失：%s", ", ".join(t.name for t in missing_tables))
    logger.info("开始创建表...")

    try:
        with engine.begin() as connection:  # 使用事务
            for table in missing_tables:
                table.create(bind=connection, checkfirst=True)
                logger.info("✅ 表 %s 已创建", table.name)

        logger.info("🎉 数据库 arXiv 相关表创建完成")
        return True

    except SQLAlchemyError as exc:
        logger.error("❌ 创建表失败: %s", exc)
        return False


def main():
    logger.info("=" * 60)
    logger.info("arXiv 数据库表检查 / 创建脚本")
    logger.info("=" * 60)

    success = ensure_tables()
    if success:
        logger.info("✅ 操作完成")
    else:
        logger.error("❌ 操作失败，请检查日志")
        sys.exit(1)


if __name__ == "__main__":
    main()


