## Query → Markdown Workflow Implementation Plan

### 1. End-to-End Overview
- 用户在前端输入原始 `query`，后端创建 `task_id` 并记录到 `Task` 表。
- 流程分为六阶段：`rewrite` → `search` → `ingest_pdf` → `emit_md` → `extract_methodology` → `innovation_synthesis`，每个阶段的产物都落盘并写入任务状态，便于追踪与重试。
- 过程中所有文件放在 `{output_dir}/{username}/{session_id}/` 目录下（通过 `file_manager.create_session_folder` 创建），子目录按阶段划分，最终输出 Markdown 文件、Methodology 提取结果、创新方案与汇总索引供前端下载。
- **实现位置**：`app/core/workflows/query_to_md_workflow.py` 的 `QueryToMarkdownWorkflow` 类。

### 2. Query Rewrite
- **Agent 实现**：使用 `app/core/agents/query_rewrite_agent.py` 的 `QueryRewriteAgent`。
- **功能**：
  - **信息提取与过滤**：用户输入可能包含各种信息（个人信息、工作背景、研究兴趣描述等），Agent 需要：
    1. 识别并提取**核心的研究主题**（技术领域、方法、应用场景等）
    2. **过滤掉不相关的个人信息**（如公司名称、职位、个人经历等）
    3. 专注于学术研究相关的技术概念、任务、领域、方法
  - **查询重写**：将提取的核心研究主题重写为 **4 个检索短句**（不是单个关键词），每个短句是完整的查询短语（4-12 个单词），适合 arXiv 搜索。
  - **输出要求**：
    - 每个短句应独立表达完整的核心研究意图（包含任务 + 领域 + 方法/模型）
    - 避免使用论文类型词汇（如 "survey", "review", "overview", "paper", "article"）
    - 提供 4 个略有不同角度的重写版本，覆盖同一核心主题的不同表达方式
- **输出格式**：Agent 输出 Markdown 代码块格式：
  ```
  ```path
  rewrite.json
  ```
  ```json
  {
    "reason": "...",
    "keywords": ["k1", "k2", "k3", "k4"]
  }
  ```
  ```
  - `reason`: 生成这 4 个 keywords 的理由说明，包括：
    - 从用户输入中提取了哪些核心研究主题
    - 如何过滤掉个人信息（如适用）
    - 为什么选择这些特定的 keywords 来表达研究意图
  - `keywords`: 4 个重写后的检索短句
- **处理示例**：
  - **输入示例**（包含个人信息）：
    ```
    我是 Aescape 公司的 Founding Business Analyst，目前负责建立公司在机器人、AI 和健康领域的
    数据实践。我的研究兴趣包括：1) 将 AI 和 ML 应用于数字健康技术优化；2) 使用 A/B 测试框架
    优化健康平台；3) 应用 NLP 和 LLM 提高医疗效率；4) 健康结果预测建模。
    ```
  - **期望输出**（提取核心研究主题，过滤个人信息）：
    ```json
    {
      "reason": "Extracted 4 core research themes from the user's input: (1) AI/ML for digital health optimization, (2) A/B testing for health platforms, (3) NLP/LLM for healthcare efficiency, (4) predictive modeling for health outcomes. Filtered out personal information (company name 'Aescape', job title 'Founding Business Analyst', work responsibilities). Each keyword represents one research direction with its application domain, suitable for academic search.",
      "keywords": [
        "AI and machine learning for digital health and wellness optimization",
        "A/B testing frameworks for health platform patient engagement",
        "NLP and large language models for healthcare delivery efficiency",
        "predictive modeling for health outcomes and risk identification"
      ]
    }
    ```
  - **说明**：Agent 应识别出核心研究领域（AI/ML、A/B 测试、NLP/LLM、预测建模）和应用场景（数字健康、健康平台、医疗效率、健康结果），过滤掉公司名称、职位等个人信息。`reason` 字段应说明提取和转换的理由，而不是原封不动地输出用户输入。
- **重试机制**：使用 `tenacity` 库实现自动重试（最多 3 次），如果解析失败会自动重试。
- **存档路径**：`artifact/rewrite.json`（通过 `file_manager.save_artifact` 保存），包含：
  - `original_query`: 原始查询（由 workflow 保存，用于记录）
  - `keywords`: 4 个重写后的检索短句
  - `agent_payload`: Agent 返回的完整 JSON（包含 `reason` 和 `keywords`）
  - `usage`: Token 使用统计（input_tokens, output_tokens, total_tokens）
- **错误处理**：若重写失败（3 次重试后仍无法解析），抛出 `ValueError`，终止后续阶段。

### 3. arXiv 搜索与下载
- **服务实现**：使用 `app/services/arxiv_service.py` 的 `search_and_download()` 函数。
- **参数配置**（可通过 `execute()` 方法参数调整）：
  - `per_keyword_max_results`: 每个关键词搜索时返回的最大结果数（默认 10）
  - `per_keyword_recent_limit`: 每个关键词只考虑最近 N 篇论文（默认 3）
  - `target_paper_count`: 最终保留的论文数量（默认 12，可配置）
  - `skip_dblp_check`: 是否跳过 DBLP 检查（默认 False）
    - `False`: 只下载在 DBLP 中有匹配的论文，使用 DBLP 的 BibTeX（质量更高）
    - `True`: 跳过 DBLP 检查，下载所有符合条件的论文，使用 arXiv 生成的 BibTeX（可能下载更多论文）
  - `filter_surveys`: 是否过滤综述论文（默认 True）
- **搜索流程**：
  1. 对 4 个关键词**顺序**调用 `search_and_download()`（关键词之间有 3 秒延迟，避免请求过快）
  2. 每个关键词的下载目录：`raw_pdfs/{keyword_dir_name}/`（关键词中的空格替换为下划线，截断至 80 字符）
  3. PDF 命名：`arxiv_{id}.pdf`，BibTeX 命名：`arxiv_{id}.bib`
- **去重与筛选逻辑**：
  1. 按 `arxiv_id` 去重（保留第一次出现的论文）
  2. 按 `published` 时间降序排序（最新的在前）
  3. 取前 `target_paper_count` 篇论文
- **Manifest 生成**：
  - 路径：`generated/papers_manifest.json`
  - 字段包括：`original_query`, `rewrite_keywords`, `per_keyword_max_results`, `per_keyword_recent_limit`, `total_found`, `total_deduped`, `target_paper_count`, `status`, `papers[]`
  - `papers[]` 中每篇论文包含：`keyword`, `arxiv_id`, `title`, `authors`, `published`, `bibtex_path`, `pdf_path`, `status`（初始为 "ok"）
- **状态标记**：
  - 若去重后的论文数 < `target_paper_count`，manifest 的 `status` 标记为 `"insufficient"`，否则为 `"ok"`
  - 在后续阶段，如果某篇论文处理失败，其 `status` 会更新为 `"failed"`

### 4. PDF → 文本（OCR）
- **实现链路**：`pdf_to_pngs` → `VisionAgent.extract_text_from_image`（详见 `docs/pdf_to_text_flow.md`）。
- **并发控制**（通过 `QueryToMarkdownWorkflow.__init__` 参数配置）：
  - `max_concurrent_pdfs`: 同时处理的 PDF 数量（默认 2）
  - `max_concurrent_pages`: 每篇论文同时处理的页面数（默认 5）
  - 使用 `asyncio.Semaphore` 控制并发度
- **处理流程**：
  1. 对 manifest 中每篇论文（`status="ok"`）创建独立目录：`processed/paper_{idx:02d}/`
  2. **PDF → PNG**：调用 `pdf_to_pngs(pdf_path, output_dir, dpi=300)`，生成 `images/page_{n}.png`
  3. **页面级并发 OCR**：
     - 使用 `asyncio.gather` 并发处理所有页面（受 `max_concurrent_pages` 限制）
     - 每页调用 `VisionAgent.extract_text_from_image()`，使用固定 OCR prompt：
       ```
       "请直接输出图片中的所有文字内容、图表、表格、公式等，
        不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
       ```
     - OCR 参数：`temperature=0.3`, `max_tokens=10000`
  4. **结果保存**：
     - 每页 OCR 结果保存到 `ocr/page_{n}.txt`
     - 所有页面合并后保存到 `ocr/full.txt`（页面之间用 `\n\n` 分隔）
     - Token 使用统计保存到 `logs/usage.json`（包含 input_tokens, output_tokens, total_tokens, page_count, status, error, timestamp）
- **Manifest 更新**：
  - 在 manifest 中为每篇论文添加 `ocr_dir` 和 `ocr_full_path` 字段
  - 如果处理失败，更新论文的 `status` 为 `"failed"`，并记录 `error` 信息
- **Artifact 生成**：
  - 路径：`artifact/pdf_processing.json`
  - 包含每篇论文的处理结果：`index`, `arxiv_id`, `pdf_path`, `status`, `page_count`, `usage`, `error`
- **错误处理**：
  - 如果 PDF 不存在或 `pdf_to_pngs` 失败，标记为 `failed` 并继续处理其他论文
  - 如果部分页面 OCR 失败，整篇论文标记为 `failed`，但已成功的页面仍会保存
  - 处理完成后，更新 `generated/papers_manifest.json`（包含 OCR 路径和状态）

### 5. Markdown 生成
- **生成条件**：只对 `status="ok"` 且存在 `ocr_full_path` 的论文生成 Markdown。
- **论文 Markdown 文件**：
  - 路径：`generated/markdown/paper_{idx:02d}_{arxiv_id}.md`
  - 内容结构：
    ```markdown
    # {Title}
    
    - arXiv ID: {arxiv_id}
    - Published: {published}
    - Authors: {authors}
    - Source Keyword: {keyword}
    - DBLP BibTeX: {bibtex_path}
    
    ## Extracted Text
    
    {ocr全文，从 ocr/full.txt 读取}
    ```
  - 如果论文处理失败或缺少 OCR 文本，跳过该论文并在 manifest 中标记 `status="failed"`。
- **汇总索引文件**：
  - 路径：`generated/index.md`
  - 内容包含：
    1. **标题**：`# Query → Markdown Summary`
    2. **原始查询**：`**Original Query**: {original_query}`
    3. **重写关键词**：列出 4 个关键词
    4. **论文表格**：包含列（# | Title | arXiv ID | Keyword | Markdown | Status）
    5. **状态提示**：如果 `status != "ok"`，显示提示信息（找到的论文数少于目标数）
    6. **失败条目**：如果有失败的论文，列出失败原因
- **Artifact 生成**：
  - 路径：`artifact/markdown_emit.json`
  - 包含成功生成的 Markdown 列表：`index`, `arxiv_id`, `title`, `keyword`, `markdown_path`（相对路径）, `status`
- **最终产物统计**：
  - 如果 `target_paper_count=4`，最终会生成：
    - **4 个论文 Markdown 文件**（每篇论文一个）：`generated/markdown/paper_01_{arxiv_id}.md`, ..., `paper_04_{arxiv_id}.md`
    - **1 个汇总索引文件**：`generated/index.md`
    - 共 **5 个 Markdown 文件**（如果只统计论文文件，则为 4 个）
- **扩展**：若需要提供 zip 下载，可将 `generated/markdown/` 与 `generated/index.md` 打包成 `artifacts.zip`。

### 6. Methodology 提取
- **Agent 实现**：使用 `app/core/agents/methodology_extraction_agent.py` 的 `MethodologyExtractionAgent`。
- **功能**：
  - 从生成的 Markdown 文件中提取论文的 problem statement 与 methodology 两部分
  - 识别 problem statement 中的问题定义、任务背景、假设等
  - 识别并提取 methodology 中的研究方法、实验设置、数据处理方法、算法描述、模型架构、训练过程、评估指标等
  - 处理边缘情况：如果论文没有明确章节，分别从相关部分（如 "Approach", "Problem Formulation", "Technical Details"）中抽取
  - 对于综述类论文，提取综述的问题陈述与方法论（如论文选择标准、分析框架等）
- **生成条件**：只对成功生成 Markdown 的论文（`markdown_emit.json` 中的条目）提取 problem statement 与 methodology。
- **输出格式**：Agent 输出 Markdown 代码块格式：
  ```
  ```path
  methodology.json
  ```
  ```json
  {
    "reason": "...",
    "problem_statement": "...",
    "methodology": "..."
  }
  ```
  ```
  - `reason`: 提取理由说明，包括：
    - 识别了哪些章节包含 problem statement / methodology
    - methodology 的类型（实验性、理论性、计算性等）
    - 提取过程中的挑战或特殊考虑
    - 如果任一部分缺失或不完整，说明原因
  - `problem_statement`: 提取的 problem statement 文本（可为空字符串）
  - `methodology`: 提取的 methodology 文本（可为空字符串）
- **论文 Problem Statement & Methodology 文件**：
  - Problem statement 路径：`generated/problem_statement/paper_{idx:02d}_{arxiv_id}_problem_statement.md`
  - Methodology 路径：`generated/methodology/paper_{idx:02d}_{arxiv_id}_methodology.md`
  - 如果 problem statement 有内容会写入对应文件；methodology 同理
  - 如果 methodology 提取失败或返回空内容，在 artifact 中标记 `status="failed"` 或 `status="empty"`（problem statement 仍会记录成功结果）
- **Artifact 生成**：
  - 路径：`artifact/methodology_extraction.json`
  - 包含每篇论文的提取结果：`index`, `arxiv_id`, `title`, `problem_statement_path`, `methodology_path`（相对路径）, `reason`, `status`, `usage`
  - 统计信息：`total_papers`（总论文数）, `extracted_count`（成功提取数）
- **并发处理**：使用 `max_concurrent_pdfs` 参数控制同时提取的论文数量，与 PDF OCR 阶段共享并发限制。
- **错误处理**：
  - 如果 Markdown 文件不存在，跳过该论文
  - 如果提取失败，在 artifact 中标记 `status="failed"`，继续处理其他论文
  - 如果提取结果为空，在 artifact 中标记 `status="empty"`，记录原因
- **可选性**：如果工作流初始化时未提供 `methodology_extraction_agent`，此阶段会被跳过。

### 7. 三论文创新综合（Innovation Synthesis）
- **Agent 实现**：`app/core/agents/innovation_synthesis_agent.py` 的 `InnovationSynthesisAgent`。
- **功能**：
  - 从 Methodology 提取阶段成功的论文中选取 3 篇（若超过 3 篇则随机抽取），将其 problem statement 与 methodology 依次映射为模块 A/B/C。
  - 分析每个模块的机制级弱点并提出改进版 A*/B*/C*。
  - 评估 1-5 条由 {A, B, C, A*, B*, C*} 组合出的可行 pipeline，选择最优组合。
  - 综合原有问题与弱点提出新的跨论文问题 `P_new`，并在提供的关键词语境下给出完整方法提案。
- **输入约束**：
  - 仅当存在 ≥3 个 `status="ok"` 且 problem/methodology 均非空的条目时触发。
  - `target_paper_count` 强制下限 3（若调用时传入 <3，会自动提升至 3），确保最少可用论文。
- **输出格式**：
  - Agent 必须输出严格遵循 ```json ... ``` 包裹的 JSON，字段结构与用户提供的 schema 一致。
  - 解析成功后落盘 `artifact/innovation_synthesis.json`，记录：
    - `selected_modules`: 被映射为模块 A/B/C 的论文 index、title、arXiv ID
    - `module_payload`: 传入 Agent 的完整文本
    - `keywords`: Query Rewrite 阶段的 4 个关键词
    - `output`: Agent 返回的 JSON
    - `usage`: Token 统计
- **错误处理**：
  - 若可用条目不足 3 篇或 Agent 输出格式错误，记录 warning/exception 并跳过该阶段，前述产物仍可用。

### 8. 任务状态与日志
- **日志记录**：使用 `app/utils/logger.py` 的统一日志系统，所有关键事件都会记录日志。
- **阶段标识**：工作流分为 6 个阶段：
  1. `rewrite`: Query Rewrite（生成 4 个关键词）
  2. `search`: arXiv 搜索与下载
  3. `ingest_pdf`: PDF → PNG → OCR
  4. `emit_md`: Markdown 生成
  5. `extract_methodology`: Methodology 提取（可选，需要提供 `methodology_extraction_agent`）
  6. `innovation_synthesis`: 三论文创新综合（可选，需要提供 `innovation_agent` 且有 3 篇可用论文）
- **Token 使用统计**：
  - **Query Rewrite 阶段**：记录在 `artifact/rewrite.json` 的 `usage` 字段中
  - **PDF OCR 阶段**：每篇论文的 token 使用记录在 `processed/paper_{idx}/logs/usage.json`，汇总在 `artifact/pdf_processing.json`
  - **Methodology 提取阶段**：每篇论文的 token 使用记录在 `artifact/methodology_extraction.json` 的每个条目中
  - **Innovation Synthesis 阶段**：整体调用的 token 使用记录在 `artifact/innovation_synthesis.json`
  - 每个阶段的 usage 包含：`input_tokens`, `output_tokens`, `total_tokens`
- **状态追踪**：
  - 每篇论文在 `papers_manifest.json` 中有 `status` 字段（`"ok"`, `"failed"`）
  - 整个工作流的 `status` 在返回结果中（`"ok"` 或 `"insufficient"`）
- **错误处理**：
  - 如果 Query Rewrite 失败，抛出异常，终止流程
  - 如果某篇论文下载失败，在 manifest 中标记 `status="failed"`，继续处理其他论文
  - 如果某篇论文 OCR 失败，在 manifest 中标记 `status="failed"`，继续处理其他论文
  - 如果某篇论文缺少 OCR 文本，跳过 Markdown 生成，继续处理其他论文
  - 如果某篇论文 Methodology 提取失败，在 artifact 中标记 `status="failed"`，继续处理其他论文
- **返回结果**：`execute()` 方法返回字典，包含：
  ```python
  {
      "session_id": str,
      "session_folder": str,              # 完整路径
      "rewrite_artifact": str,            # artifact/rewrite.json 路径
      "papers_manifest": str,             # generated/papers_manifest.json 路径
      "pdf_processing_artifact": str,     # artifact/pdf_processing.json 路径
      "markdown_emit_artifact": str,      # artifact/markdown_emit.json 路径
      "index_md": str,                    # generated/index.md 路径
      "methodology_extraction_artifact": Optional[str],  # artifact/methodology_extraction.json 路径（如果执行了提取）
      "innovation_artifact": Optional[str],              # artifact/innovation_synthesis.txt 路径（如果执行了创新阶段）
      "status": str,                      # "ok" 或 "insufficient"
  }
  ```
- **扩展支持**：未来可集成 SSE 推送，实时推送各阶段进度（关键词生成完成、每个关键词的下载结果、每篇 PDF OCR 完成、Markdown 输出完成、Methodology 提取完成等）。

### 8. 文件层级结构（实际实现）

当前实际写盘是基于「输出根目录 + 用户名 + session」的结构（见 `file_manager.create_session_folder`）。  
所有该任务相关的中间产物与最终结果统一挂在同一个 session 目录下：

```
{output_dir}/{username}/{session_id}/
  artifact/                  # 每个阶段的中间产物 JSON，便于追踪与重试
    rewrite.json              # Step 1: Query Rewrite 结果（原始 query、4 个关键词、usage）
    pdf_processing.json       # Step 3: PDF OCR 处理结果（每篇论文的状态、token 使用）
    markdown_emit.json        # Step 4: Markdown 生成列表（成功生成的 markdown 文件信息）
    methodology_extraction.json  # Step 5: Methodology 提取结果（每篇论文的提取状态、路径、usage）
    innovation_synthesis.json    # Step 6: 三论文创新综合（所选模块、Agent 输出、usage）
  generated/                  # 本次任务的最终生成文件
    papers_manifest.json      # Step 2: 论文清单（包含所有论文的元数据、路径、状态）
    index.md                  # Step 4: 汇总索引文件（原始查询、关键词、论文表格）
    markdown/                 # Step 4: 每篇论文的 Markdown 文件
      paper_01_{arxiv_id}.md
      paper_02_{arxiv_id}.md
      ...
    problem_statement/        # Step 5: Problem Statement 提取文件
      paper_01_{arxiv_id}_problem_statement.md
      ...
    methodology/              # Step 5: Methodology 提取文件
      paper_01_{arxiv_id}_methodology.md
      paper_02_{arxiv_id}_methodology.md
      ...
  raw_pdfs/                   # Step 2: 下载的原始 PDF 和 BibTeX
    {keyword_dir_name}/
      arxiv_{id}.pdf
      arxiv_{id}.bib
      ...
  processed/                  # Step 3: PDF 处理后的中间产物
    paper_01/
      images/
        page_1.png
        page_2.png
        ...
      ocr/
        page_1.txt
        page_2.txt
        ...
        full.txt              # 所有页面的合并文本
      logs/
        usage.json            # Token 使用统计
    paper_02/
      ...
```

**关键文件说明**：
- `artifact/rewrite.json`: Query Rewrite 阶段的完整结果（包含 Agent 原始输出和 usage）
- `generated/papers_manifest.json`: 论文清单，包含所有论文的元数据、路径、状态，在 PDF 处理后会更新 OCR 路径
- `artifact/pdf_processing.json`: 每篇论文的 OCR 处理详情（页面数、token 使用、错误信息）
- `generated/markdown/`: 每篇成功处理的论文对应一个 Markdown 文件
- `generated/index.md`: 汇总索引，包含原始查询、关键词、所有论文的表格
- `generated/problem_statement/`: 每篇成功提取的论文对应一个 Problem Statement 文件（如果执行了提取）
- `generated/methodology/`: 每篇成功提取的论文对应一个 Methodology 文件（如果执行了提取）
- `artifact/methodology_extraction.json`: Problem Statement & Methodology 提取阶段的完整结果（包含每篇论文的提取状态、路径、usage）
- `artifact/innovation_synthesis.json`: 三论文创新综合阶段的输出（所选模块、Agent JSON、usage）

**Session ID 生成规则**：
- 如果调用时 `session_id=None`，系统会自动生成格式为 `session_{timestamp}_{uuid}` 的 session_id
- 例如：`session_20251127_112630_748edba5`（2025年11月27日 11:26:30，UUID前8位）

**如未来需要显式引入 `task_id` 维度**，可在 session 目录下再加一层：
```
{output_dir}/{username}/{session_id}/tasks/{task_id}/...
```

### 9. 参数配置与扩展

#### 9.1 工作流参数（`QueryToMarkdownWorkflow.execute()`）
- `original_query` (str, 必需): 用户输入的原始查询
- `session_id` (Optional[str]): Session ID，如果为 `None` 会自动生成
- `username` (Optional[str]): 用户名，用于构建输出路径
- `target_paper_count` (int, 默认 12): 最终保留的论文数量（去重后按时间排序取前 N 篇，**自动提升至 ≥3**，以满足创新 Agent 对三篇论文的要求）
- `per_keyword_max_results` (int, 默认 10): 每个关键词搜索时返回的最大结果数
- `per_keyword_recent_limit` (int, 默认 3): 每个关键词只考虑最近 N 篇论文
- `skip_dblp_check` (bool, 默认 False): 是否跳过 DBLP 检查
  - `False`: 只下载 DBLP 中有匹配的论文（BibTeX 质量更高）
  - `True`: 跳过 DBLP 检查，下载所有符合条件的论文（可能下载更多，但使用 arXiv BibTeX）

#### 9.2 工作流初始化参数（`QueryToMarkdownWorkflow.__init__()`）
- `query_rewrite_agent` (QueryRewriteAgent, 必需): Query Rewrite Agent 实例
- `vision_agent` (VisionAgent, 必需): Vision Agent 实例（用于 PDF OCR）
- `methodology_extraction_agent` (Optional[MethodologyExtractionAgent], 可选): Methodology 提取 Agent 实例
  - 如果提供，工作流会在 Step 4 之后执行 Step 5（Methodology 提取）
  - 如果为 `None`，跳过 Methodology 提取阶段
- `innovation_agent` (Optional[InnovationSynthesisAgent], 可选): 三论文创新 Agent
  - 如果提供且有 ≥3 篇可用论文，会执行 Step 6（Innovation Synthesis）
  - 若可用论文不足 3 篇，记录 warning 并跳过
- `max_concurrent_pdfs` (int, 默认 2): 同时处理的 PDF 数量（也用于 Methodology 提取的并发控制）
- `max_concurrent_pages` (int, 默认 5): 每篇论文同时处理的页面数
- `max_pages_per_pdf` (Optional[int], 默认 20): 每篇论文最多进行 OCR 的页数，`None` 表示不限制


#### 9.4 使用示例
```python
from app.core.workflows.query_to_md_workflow import QueryToMarkdownWorkflow
from app.core.agents.query_rewrite_agent import QueryRewriteAgent
from app.core.agents.vision_agent import VisionAgent
from app.core.agents.methodology_extraction_agent import MethodologyExtractionAgent
from app.core.agents.innovation_synthesis_agent import InnovationSynthesisAgent
from app.services.openai_service import OpenAIService
from app.services.anthropic_service import AnthropicService

# 初始化依赖
openai_service = OpenAIService()
query_agent = QueryRewriteAgent(openai_service=openai_service)
methodology_agent = MethodologyExtractionAgent(openai_service=openai_service)
innovation_agent = InnovationSynthesisAgent(openai_service=openai_service)

anthropic_service = AnthropicService()
vision_agent = VisionAgent(anthropic_service=anthropic_service)

# 创建工作流实例（包含 Methodology 提取）
workflow = QueryToMarkdownWorkflow(
    query_rewrite_agent=query_agent,
    vision_agent=vision_agent,
    methodology_extraction_agent=methodology_agent,  # Step 5
    innovation_agent=innovation_agent,               # Step 6
    max_concurrent_pdfs=2,
    max_concurrent_pages=5,
    max_pages_per_pdf=20,
)

# 执行工作流
result = await workflow.execute(
    original_query="Large Language Models for academic writing assistance",
    session_id=None,              # 自动生成 session_id
    username="dev_tester",
    target_paper_count=4,         # 最终保留 4 篇论文
    per_keyword_max_results=3,    # 每个关键词最多 3 篇
    per_keyword_recent_limit=3,   # 每个关键词只考虑最近 3 篇
    skip_dblp_check=True,        # 跳过 DBLP 检查
    max_pages_per_pdf=10,         # 如需覆盖实例默认值
)
```

#### 9.5 扩展与注意事项
- **可配置项**：
  - 关键词数量：当前固定为 4 个，如需修改需调整 `QueryRewriteAgent` 的 prompt
  - 目标论文数：通过 `target_paper_count` 参数配置
  - 是否保留 PNG：当前默认保留，如需清理可在处理完成后删除 `processed/paper_{idx}/images/` 目录
  - 并发上限：通过 `max_concurrent_pdfs` 和 `max_concurrent_pages` 参数配置
  - OCR 页数限制：通过 `max_pages_per_pdf` 参数控制，`None` 表示处理整篇 PDF
- **重试机制**：
  - Query Rewrite 阶段：自动重试 3 次（使用 `tenacity` 库）
  - Methodology 提取阶段：自动重试 3 次（使用 `tenacity` 库）
  - arXiv 下载：在 `arxiv_service` 中有重试机制
  - PDF OCR：当前无自动重试，失败后需手动重试（可通过重新调用工作流实现）
- **幂等性**：
  - Session 目录创建具备幂等性（`create_session_folder` 会创建已存在的目录）
  - 如果使用相同的 `session_id` 重新运行，会覆盖已有文件
- **性能优化**：
  - 关键词搜索之间有 3 秒延迟，避免请求过快
  - PDF 和页面级并发处理，提高处理速度
  - 使用 `asyncio.Semaphore` 控制并发度，避免资源耗尽
- **后续扩展**：
  - 可在 Markdown 中追加自动摘要或结构化要点，需要新增 Agent
  - 可支持用户自定义 OCR prompt
  - 可支持批量任务处理（多个 query 并行处理）
  - 可集成 Task 表，记录任务状态和进度
  - 可支持 SSE 实时推送进度

