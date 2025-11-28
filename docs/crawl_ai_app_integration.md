# `lab/crawl_ai.py` → `app/` 集成方案

## 目标与约束
- **目标**：每月自动运行 `ArxivCrawler` 流程，产出新增论文、热门算法短语，并写入现有数据库供 Web/API 使用。
- **非目标**：此阶段不重构业务逻辑，只做工程化包装（配置、持久化、调度、可观察性）。
- **约束**：
  - 复用已有脚本，避免双维护。
  - 运行环境为 `app/` FastAPI 服务同一套依赖（依赖需列入 `requirements.txt`）。
  - 数据库存量可能较大，写入策略需幂等、可重复执行（允许运行失败后重试）。

## 集成路线图
1. **封装服务层**（Week 1）
   - 在 `app/services/` 新增 `crawler_service.py`，导入 `lab.crawl_ai` 中的核心函数或类。
   - 将 `ArxivCrawler` 实例化参数改为依赖 `app.config.settings`（代理、OpenAI、速率等）。
   - 暴露结构化接口：
     ```python
     class MonthlyArxivSyncService:
         async def run_once(self) -> CrawlResult:
             ...
     ```
   - `CrawlResult` 包含 `date_info`, `new_papers`, `hot_phrases`, `stats`.

2. **数据库建模**（Week 1-2）
   - 在 `app/db/models.py` 增加两张表：
     - `ArxivCrawlRun`: `id`, `run_month`, `started_at`, `finished_at`, `status`, `total_papers`, `new_papers_count`, `hot_phrases` (JSON), `log`.
     - `ArxivPaper`: `id`, `crawl_run_id`, `arxiv_id`, `title`, `authors`, `subjects`, `abstract`, `algorithm_phrase` (JSON/Text), `detail_dateline`, `metadata` (JSON), `created_at`.
   - 迁移脚本：使用当前项目的 Alembic/自定义迁移方式（参考 `scripts/` 中 DB 操作文档）。
   - Repository 层（放在 `app/db/repositories/arxiv_repository.py`）：
     - `create_crawl_run(session, payload)`
     - `upsert_papers(session, papers)`
     - `list_latest_hot_phrases(limit=5)`

3. **服务-DB 接口**（Week 2）
   - `MonthlyArxivSyncService.run_once()` 步骤：
     1. 创建 `crawl_run` 记录（status=`running`）。
     2. 调用 `ArxivCrawler.run()` 获取结果。
     3. `bulk_upsert` 新论文（以 `arxiv_id` 去重）。
     4. 更新 `crawl_run` 统计与热门短语 JSON。
     5. 记录日志到 `crawl_run.log`（包含 `crawler.get_hot_phrases()` 返回的前 5 条，用于快速展示）。
   - 写入策略：
     - 若 `arxiv_id` 已存在，仅更新 `algorithm_phrase`, `detail_title`, `updated_at`。
     - `hot_phrases` 以 JSON 列 `["phrase1", "phrase2", ...]` 形式存储，方便 API 直接返回。

4. **调度方案**（Week 3）
   - **首选**：在 `app/core/` 下新增 `scheduler.py`，基于 `APScheduler` (`BackgroundScheduler`)。
     - 在 `app/main.py` 的 `startup_event` 中：
       ```python
       scheduler = init_scheduler()
       scheduler.add_job(sync_service.run_once, trigger='cron', day=1, hour=3)
       app.state.scheduler = scheduler
       ```
     - `shutdown_event` 中 `scheduler.shutdown(wait=False)`。
   - **备选**：若不希望服务常驻调度，可提供 CLI：
     - 新建 `app/jobs/run_arxiv_crawl.py`，内容为同步入口：
       ```bash
       poetry run python -m app.jobs.run_arxiv_crawl
       ```
     - 配合系统级任务计划（Linux cron / Windows 任务计划程序）每月运行一次。
   - 可以同时保留两种方式：服务内调度 + 外部 CLI 兜底。

5. **API/前端联动**（Week 3-4）
   - 在 `app/api/v1/endpoints/` 新增 `arxiv_crawl.py`：
     - `GET /arxiv-runs/latest` → 返回最近一次运行及热门短语。
     - `POST /arxiv-runs/manual-trigger`（需管理员权限）→ 手动触发 `run_once()`。
   - 若前端需要展示热门短语，可调用新的 API 或直接读取 `hot_phrases`.

6. **运维与可观察性**
   - 日志：使用现有 `app.utils.logger`，在服务层打 INFO/ERROR，字段包括 `run_id`, `new_papers_count`, `duration`.
   - 监控：可在 Prometheus/Grafana 中新增 counter（如 `arxiv_crawl_runs_total`）和 gauge（`arxiv_new_papers_last_run`）。
   - 告警：调度任务失败时发送邮件/Slack（可借助现有通知模块或简单 SMTP）。

## 每月自动化流程
| 步骤 | 详情 |
| --- | --- |
| 1. 调度触发 | APScheduler 或外部任务计划在每月 1 日 03:00 触发 `run_once()`。 |
| 2. 初始化 | `MonthlyArxivSyncService` 读取 `.env` 配置，锁定当月 `run_month`，写入 `crawl_run(status=running)`。 |
| 3. 数据抓取 | 复用 `ArxivCrawler.run()`，按配置抓取/去重/LLM 摘要/热门聚合。 |
| 4. 数据写入 | 将 `new_papers` 批量 upsert，`hot_phrases` 写入 `crawl_run.hot_phrases`。 |
| 5. 完成 | 更新 `crawl_run.status=success`，记录 `duration`、`new_papers_count`。 |
| 6. 失败恢复 | 若抛异常，捕获并更新 `crawl_run.status=failed` + `error_message`，告警；调度器默认下次再尝试。 |

## 配置清单
- `settings.py` 新增字段：
  - `ARXIV_MAX_PAPERS`, `ARXIV_FETCH_DETAILS`, `ARXIV_SUMMARIZE_NEW`, `ARXIV_HOT_TOP_K`.
  - `SCHEDULER_ENABLED`, `SCHEDULER_TIMEZONE`, `ARXIV_CRON`（如 `"0 3 1 * *"`）。
- `.env` 示例：
  ```
  ARXIV_MAX_PAPERS=50
  ARXIV_PAPERS_PER_PAGE=25
  ARXIV_USE_PROXY=true
  SCHEDULER_ENABLED=true
  ARXIV_CRON=0 3 1 * *
  ```

## 测试计划
1. **单元测试**
   - Mock `ArxivCrawler` 输出，验证 `MonthlyArxivSyncService` 能正确写入 DB，并在异常时 rollback。
2. **集成测试**
   - 利用 SQLite 内存库运行一次完整流程（禁用实际抓取，使用预置 JSON），确保 API 返回符合预期。
3. **调度测试**
   - 启用 APScheduler，设置 cron 为每分钟，观察 run/stop 行为后再改回每月。
4. **性能/超时**
   - 在 Staging 环境配置较小 `max_papers=5` 快速验证，确保任务控制在 <10 分钟。

## 交付物 checklist
- [ ] `app/services/crawler_service.py`（含日志与配置注入）。
- [ ] `app/db/models.py` 新增表 + 迁移脚本。
- [ ] Repository + API endpoint。
- [ ] `app/core/scheduler.py`（可选 CLI 工具 `app/jobs/run_arxiv_crawl.py`）。
- [ ] 文档更新：`docs/crawl_ai.md` 链接至本集成文档，并在 `docs/` 新增运维说明。
- [ ] 操作指南：如何手动触发/查看结果/排错。

完成以上步骤后，即可在 `app/` 工程内自动化运行 cs.AI 论文月度采集，并将结果纳入统一的数据库和 API 体系。***

