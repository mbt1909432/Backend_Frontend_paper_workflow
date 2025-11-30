# `lab/crawl_ai.py` → `app/` 集成决策稿

> 明确 ArxivCrawler 纳入 FastAPI 服务的工程方案：服务封装、配置、数据库、调度/API、幂等策略与可观察性。`lab/crawl_ai.py` 仍为真源，只在 `app/` 内做 orchestrator。

---

## 服务层封装
- `app/services/crawler_service.py` 新增 `MonthlyArxivSyncService`。
- 直接 `from lab.crawl_ai import ArxivCrawler`，保持单一实现。
- 构造函数注入 `settings`（代理、速率、LLM、cron 等）。
- 提供 `async def run_once(self, *, persist=True, output_path=None) -> CrawlResult`，内部用 `loop.run_in_executor` 调用同步的 `crawler.run()`，避免阻塞 FastAPI 事件循环，并允许 dry-run/JSON 导出。
- `CrawlResult` 至少包含 `date_info/new_papers/hot_phrases/stats/log_summary`。

## 配置落地
- `app/config/settings.py` 新增：
  - `arxiv_max_papers: int = 200`
  - `arxiv_papers_per_page: int = 50`
  - `arxiv_use_proxy: bool = True`
  - `arxiv_fetch_details: bool = True`
  - `arxiv_summarize_new: bool = True`
  - `arxiv_summary_model: str`
  - `arxiv_summary_concurrency: int`
  - `arxiv_hot_top_k: int = 10`
  - `scheduler_enabled: bool = True`
  - `scheduler_timezone: str = "Asia/Shanghai"`
  - `arxiv_cron: str = "0 3 1 * *"`
- `.env` 提供默认值，CI 环境可用较小配置。
- `MonthlyArxivSyncService` 构造 `ArxivCrawler` 时直接读取上述字段。

## 数据库设计
### `ArxivCrawlRun`（`app/db/models.py`）
- 字段：`id (UUID)`, `run_month (YYYY-MM)`, `status (Enum running/success/failed)`, `started_at`, `finished_at`, `duration_seconds`, `error_message`, `total_papers`, `new_papers_count`, `hot_phrases (JSON list)`, `log (Text)`, `created_at`.
- 关系：`papers = relationship("ArxivPaper", back_populates="crawl_run")`。

### `ArxivPaper`
- 字段：`id (UUID)`, `crawl_run_id (ForeignKey)`, `arxiv_id (String, unique)`, `title`, `authors (Text)`, `subjects`, `abstract`, `detail_dateline`, `detail_title`, `algorithm_phrase (JSON)`, `metadata (JSON)`, `created_at`, `updated_at`.
- `arxiv_id` 唯一索引提供幂等写入。

### 迁移
- 若已有 Alembic：`alembic revision -m "add arxiv tables"`，在 upgrade 中创建上述表。
- 若无：在 `scripts/001_add_arxiv_tables.sql` 中写建表语句，并在 README 指定执行方式。
- 也可直接运行 `python scripts/add_arxiv_tables.py`，脚本会根据 SQLAlchemy 模型检查并补齐缺失的 `arxiv_crawl_runs`、`arxiv_papers` 表，幂等可重复执行。

## Repository 层（`app/db/repositories/arxiv_repository.py`）
- `create_crawl_run(session, payload)`
- `update_crawl_run_status(session, run_id, **fields)`
- `bulk_upsert_papers(session, papers)`：`ON CONFLICT (arxiv_id)` 更新 `algorithm_phrase/detail_title/detail_dateline/metadata/updated_at`。
- `get_latest_run(session)`
- `list_hot_phrases(session, limit=10)`

## 服务执行流程
1. `run_id = create_crawl_run(status="running")`
2. `result = await loop.run_in_executor(..., crawler.run)`
3. `bulk_upsert_papers(result["new_papers"])`
4. 统计 `total_papers`, `len(result["new_papers"])`, `result["hot_phrases"]`
5. `update_crawl_run_status(run_id, status="success", hot_phrases=..., finished_at=now, duration_seconds=...)`
6. 捕获异常 → `update_crawl_run_status(..., status="failed", error_message=str(exc))` 并重新抛出
7. 日志：复用 `app.utils.logger.setup_logger`，INFO/ERROR 均包含 `run_id`, `new_papers_count`, `duration_seconds`，并把摘要写入 `ArxivCrawlRun.log`

## 调度与 CLI
- `app/core/scheduler.py`
  - `from apscheduler.schedulers.asyncio import AsyncIOScheduler`
  - `init_scheduler(sync_service)`：`scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)`
  - `scheduler.add_job(sync_service.run_once, CronTrigger.from_crontab(settings.arxiv_cron, timezone=settings.scheduler_timezone), max_instances=1, misfire_grace_time=3600)`
- `app/main.py`
  - `startup_event`：实例化 `MonthlyArxivSyncService`；若 `settings.scheduler_enabled`，则 `init_scheduler` 并挂到 `app.state.scheduler`
  - `shutdown_event`：若存在 `app.state.scheduler`，执行 `scheduler.shutdown(wait=False)`
- CLI 兜底 `app/jobs/run_arxiv_crawl.py`，支持：
  - 默认模式：`python -m app.jobs.run_arxiv_crawl`
  - 仅本地验证、不写数据库：`python -m app.jobs.run_arxiv_crawl --dry-run --output ./lab/arxiv_papers.json`
  - 若未提供 `--output`，dry-run 会默认写到仓库根目录下 `lab/arxiv_papers.json`，便于快速检查 JSON。
  - dry-run 场景下仍会执行完整抓取（包括 LLM 摘要/热门聚合），但不会创建 `ArxivCrawlRun` 记录或 upsert 论文。

## API 暴露
- `app/api/v1/endpoints/arxiv_crawl.py`
  - `GET /arxiv-crawl/latest`：返回最近一次 `ArxivCrawlRun`（含 `hot_phrases`, `new_papers_count`, `status`, `finished_at`）
  - `GET /arxiv-crawl/papers`：分页/关键词过滤，输出 `id/arxiv_id/title/algorithm_phrase/created_at`
  - `POST /arxiv-crawl/trigger`：管理员权限，内部 `background_tasks.add_task(service.run_once)`
- `app/api/v1/router.py` 注册：`router.include_router(arxiv_crawl_router, prefix="/arxiv-crawl", tags=["arxiv"])`
- 前端直接消费 `hot_phrases` JSON，papers 接口返回必要字段即可

## 复用与隔离策略
- `lab/crawl_ai.py` 继续作为实验入口；`app/` 只 import 不 fork 逻辑。
- 所有调度/CLI/API 均调用 `MonthlyArxivSyncService`，确保统一日志、事务与指标。
- `app/services` 与现有 `arxiv_service.py` 保持一致的封装风格。

## 测试与可观察性
- **单元测试**：`tests/test_crawler_service.py` mock `ArxivCrawler`，断言 DB 写入、状态流转、异常处理。
- **集成测试**：脚本或 pytest fixture 使用 SQLite in-memory 跑 `run_once()`，供 CI 验证。
- **调度测试**：临时将 `settings.arxiv_cron = "* * * * *"`，观察 APScheduler 运行，再改回月度。
- **监控**：若项目已有 Prometheus，新增 `Counter("arxiv_crawl_runs_total", ...)` 与 `Gauge("arxiv_new_papers_last_run", ...)`；否则确保 INFO 日志包含关键字段。
- **失败重试**：依赖 APScheduler `max_instances=1`、`misfire_grace_time=3600`；失败时记录 `error_message`，由日志/告警系统捕获。

---

落地上述模块后，即可在 `app/` 内部自动化运行 cs.AI 论文月度采集，保证配置集中、数据落库、调度可靠、API 可查、CLI 可兜底，同时保留 `lab/` 的研发灵活性。

