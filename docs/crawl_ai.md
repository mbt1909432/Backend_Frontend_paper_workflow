# `lab/crawl_ai.py` 文档

## 概述

`lab/crawl_ai.py` 是一个端到端的 arXiv cs.AI 论文采集与处理脚本，核心职责包括：
- 批量抓取最新的 arXiv cs.AI 条目并按页遍历。
- 读取本地历史 JSON 数据，执行去重，仅保留新增论文。
- 可选地访问每篇论文详情页补全标题、摘要等信息。
- 在具备 OpenAI API Key 时，异步调用 LLM 生成 3~5 条算法级摘要短语。
- 将结果与历史数据合并后输出到 JSON，并提供命令行预览。

脚本兼具可配置性（分页大小、代理、最大条目等）与可扩展性（LLM 总结、详情抓取开关），适合作为学术情报收集流水线的入口。

## 依赖与环境

- 核心第三方库：`requests`, `beautifulsoup4`, `openai`, `asyncio`.
- 可通过 `build_proxies()` 读取本地代理配置（默认 127.0.0.1:7890）。
- 支持 `.env` 文件（`load_local_env()`）以注入 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 等变量；未配置时会自动跳过 LLM。

## 模块结构

| 函数 | 职责 |
| --- | --- |
| `build_proxies` | 根据配置返回统一的 HTTP/HTTPS 代理字典。 |
| `scrape_arxiv_page` | 抓取单页 HTML，解析 `<dt>/<dd>` 区块，提取 ID、链接、作者、分类等。 |
| `fetch_paper_detail` | 访问单篇详情页，补充完整版标题、摘要、发布日期等。 |
| `load_existing_data` | 读取本地 JSON（默认 `arxiv_papers.json`）以便去重。 |
| `build_summary_prompt` | 生成结构化 LLM 提示词，约束输出 JSON。 |
| `extract_json_from_response` | 从 LLM 返回的 ```json 代码块中提取结构化数据。 |
| `summarize_papers_with_llm` | 基于 `AsyncOpenAI` 的异步并发摘要生成器，写回 `algorithm_phrase`。 |
| `build_hot_phrase_prompt` / `aggregate_trending_phrases_with_llm` | 聚合所有 `algorithm_phrase`，若总量超过 200 条仅取前 200 条传给 LLM，并输出 10-20 条按热度排序的热门短语。 |
| `ArxivCrawler` | 面向 cs.AI 的流程封装类，负责分页抓取、去重、详情补全、LLM 摘要与热门聚合。 |
| `ArxivCrawler.get_hot_phrases` | 返回最近一次热门聚合的前 N 条短语（默认 5 条），便于 CLI/UI 直接展示。 |
| `save_to_json` / `print_papers` | 辅助输出：保存 JSON、打印摘要列表。 |

## 主流程 (`ArxivCrawler.run`)

1. **加载既有数据**：调用 `load_existing_data` 读取历史 JSON，构建 `existing_ids` 集合用于快速去重。
2. **分页抓取**：
   - 计算目标页数 `num_pages` 并依次访问。
   - 通过 `scrape_arxiv_page` 抓取单页，基于 `processed_count` 限定“前 N 篇”处理范围。
   - 对每条记录：
     - 若缺少 `arxiv_id` 或已在 `seen_ids` 中则跳过。
     - 新增条目写入 `all_papers` 并更新计数。
   - 当处理数达到 `max_papers` 即停止继续翻页，避免无效抓取。
3. **详情补充**（可选）：若 `fetch_details=True` 且存在新增论文，遍历 `all_papers`，逐篇调用 `fetch_paper_detail` 补全 title/abstract，并加入节流等待。
4. **LLM 摘要**（可选）：若设置 `summarize_new=True` 且已配置 API key，调用 `summarize_papers_with_llm`；该函数利用 `asyncio.Semaphore` 控制并发，确保输出 JSON 格式的 `summary_points` 并写回每篇论文。
5. **热门聚合**（可选）：将 `all_papers + existing_papers` 中的 `algorithm_phrase` 扁平化去重，记录本次聚合获得的短语数量，若超过 200 条则仅截取前 200 条交给 LLM agent（`aggregate_trending_phrases_with_llm`），最终输出 10-20 条按热度排序的方向，写入返回结果的 `hot_phrases` 字段并打印。
6. **结果汇总**：
   - 将新增论文与历史 `existing_papers` 合并，返回 `{'date_info','total_papers','papers','new_papers','hot_phrases'}`。
   - 若无新增条目，明确提示“无新增论文，跳过详情页抓取和 LLM 摘要”。
   - 可以通过 `crawler.get_hot_phrases(limit=5)` 快速获取热门短语子集，用于 UI widget 或指标上报。

## LLM 摘要逻辑

- 入口：`summarize_papers_with_llm(papers, model, temperature, max_tokens, sleep_time, concurrency)`。
- 并发控制：`asyncio.Semaphore` + `asyncio.gather`，默认最多 5 并发请求。
- Prompt 约束：要求模型输出一个包裹在 ```json 代码块内的对象，字段为 `summary_points`（≤8 词的技术短语列表），方便 `extract_json_from_response` 解析。
- 结果写入：
  - 若 `summary_points` 解析成功，则同时更新 `ai_summary_structured` 与 `algorithm_phrase`。
  - 若解析失败，退化为保存原始文本。
- 错误处理：捕获 `Exception` 后打印提示并继续其他任务，避免单次失败影响整体。

## CLI / 脚本入口

文件末尾提供 `if __name__ == '__main__':` 执行示例：
1. 调用 `load_local_env()` 注入 .env。
2. 输出当前 `OPENAI_*` 环境变量（以脱敏形式展示 API Key）。
3. 根据需要实例化 `ArxivCrawler` 并调用 `run()`（默认抓取 25 条、启用代理、开启 LLM 摘要）。
4. 仅打印前 5 篇论文概览、输出 TOP 10-20 热门短语，并将完整结果保存到 `arxiv_papers.json`。
5. 如需在外部模块中重复展示热门短语，可在 `run()` 之后立即调用 `crawler.get_hot_phrases()` 获取前若干条结果。

可根据需求调整：
- `max_papers`：控制抓取的最新论文数量上限。
- `papers_per_page`：与 arXiv `show` 参数对齐。
- `use_proxy` / `sleep_time`：应对网络限制与速率控制。
- `summarize_new`、`summary_*`：按需开启/调整 LLM 摘要。

## 工作流小结

```
load_existing_data
        │
        ▼
ArxivCrawler.run → scrape_arxiv_page (分页循环, processed_count 限速)
        │
去重 → all_papers
        │
   ┌────┴───────────┐
   ▼                ▼
fetch_paper_detail  summarize_papers_with_llm
   │                │
   └─────► enrich all_papers ◄──────┘
                    │
                    ▼
           merge with existing_papers
                    │
                    ▼
 aggregate_trending_phrases_with_llm (TOP 热门 10-20 条)
                    │
                    ▼
        return/save/print final dataset
```

以上文档可作为快速上手指南，也便于后续在此基础上扩展新的采集分类、数据后处理或持久化策略。***

