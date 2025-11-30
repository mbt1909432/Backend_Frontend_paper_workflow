# Query→Markdown arXiv/DBLP 阻塞分析

## 当前行为
- `query_to_md_workflow` 仍旧按关键词顺序串行执行，调用同步包装器 `search_and_download`。该包装器会阻塞直到单个关键词的检索 + 下载全部完成，并在关键词之间额外 `time.sleep(3)`。

```165:197:app/core/workflows/query_to_md_workflow.py
        for i, kw in enumerate(keywords):
            ...
            papers = search_and_download(...)  # synchronous wrapper
            ...
            if i < len(keywords) - 1:
                delay_seconds = 3
                ...
                time.sleep(delay_seconds)
- 包装器内部确实调用了 `search_and_download_async`，但 workflow 端没有 `await`，因此对调用者来说每个关键词仍是阻塞同步流程，只有内部 aiohttp 下载是异步。

- `search_and_download_async` 里对 DBLP 的校验 `_search_dblp_bibtex` 使用 `requests` + BeautifulSoup，是完全同步 IO，并且对每篇候选文章都要跑一遍，延长了关键路径。

## 影响
- 关键词一个接一个执行，整体耗时随重写关键词数量线性增长。
- 虽然 PDF 下载路径是 async I/O，但由于调用侧串行，下载无法与其他关键词的搜索并行，收益有限。
- DBLP 抓取一次可能耗时数秒；同步调用会长时间占用事件循环线程，阻塞其他异步任务。

## 改进建议
1. **让 workflow 直接 await 并发任务**
   - 去掉同步包装器，直接在 workflow 中 `await search_and_download_async`。
   - 采用 `asyncio.gather` + 限流信号量并发多个关键词，使 arXiv 检索与下载互相重叠。

2. **移除人工 `sleep`**
   - 在 `arxiv_service` 内部基于速率限制控制节奏后，外层不再 `time.sleep(3)`，避免空等。

3. **异步化 DBLP 抓取**
   - 将 `requests` 改为 `aiohttp`，或把同步请求丢到线程池中，避免 `_search_dblp_bibtex` 阻塞事件循环。
   - 针对 `(title, author)` 做缓存，减少失败重试时的重复请求。

4. **增加阶段级性能日志**
   - 记录单个关键词在 arXiv 搜索、DBLP 校验、PDF 下载各阶段耗时，便于并发改造后的瓶颈分析。

按以上方案改造后，可确保每个关键词内部流程非阻塞，最大化利用网络带宽，同时继续遵守 arXiv 的速率限制。
