## PDF 转文字整体流程说明

### 1. 总体思路

- **目标**：把用户上传的 PDF 转成纯文字内容，作为论文生成工作流的输入之一。
- **核心链路**：  
  **PDF → 临时 PDF 文件 → 按页转成 PNG 图片 → Vision 大模型做 OCR → 拼接为 `pdf_text_content` → 与其它输入合并为 `combined_document` → 传入论文生成工作流**。

---

### 2. PDF → PNG 图片

- **相关文件**：`app/utils/pdf_converter.py`
- **核心函数**：`pdf_to_pngs(pdf_path: str, output_dir: Optional[str] = None, dpi: int = 300) -> List[str]`
- **步骤**：
  - 检查 `pdf_path` 是否存在。
  - 使用 **PyMuPDF (`fitz`)** 打开 PDF 文档：`pdf_document = fitz.open(pdf_path)`。
  - 遍历每一页：
    - `page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))` 渲染为指定 DPI 的位图。
    - 使用 **Pillow (`PIL.Image`)** 将位图转换为 PNG 图像并保存。
    - 文件命名规则：`{pdf_name}_page_{页号}.png`，统一保存在 `output_dir` 中。
  - 返回值：每一页 PNG 的文件路径列表 `List[str]`。

---

### 3. PNG → 文字（Vision 大模型 OCR）

- **相关文件**：`app/api/v1/endpoints/workflow.py`
- **接口**：`POST /api/v1/workflow/execute`
- **主要逻辑（非流式接口）**：
  1. 前端上传 `pdf_file`（`UploadFile`）。
  2. 后端读取 PDF 二进制内容 `pdf_content = await pdf_file.read()`。
  3. 将内容写入一个临时 PDF 文件 `temp_pdf_path`。
  4. 创建临时输出目录 `temp_output_dir`，调用 `pdf_to_pngs`：
     - `png_paths = pdf_to_pngs(pdf_path=temp_pdf_path, output_dir=temp_output_dir, dpi=300)`
     - 若返回为空，则抛出 `HTTPException(status_code=500, detail="PDF转PNG失败")`。
  5. 对每一张 PNG 并发调用 `VisionAgent.extract_text_from_image`：
     - 文本提示词（`text_prompt`）为中文：  
       “请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。”
     - 通过 `asyncio.create_task` + `asyncio.gather` 并行处理所有页面。
  6. 将每一页返回的文本按页号排序后拼接：
     - `pdf_text_content = "\n\n".join(page_descriptions)`。
  7. 汇总所有页面的 token 使用量，调用 `record_usage_from_dict` 记录 `pdf_processing` 阶段的消耗。
  8. 清理临时 PDF 文件与 PNG 目录。

---

### 4. 合并 PDF 文本与其它输入

- **相关代码位置**：`execute_workflow` 接口内部。
- 将多种来源的内容统一拼接：
  - 用户直接输入的文字：`document` → `user_document`。
  - 从 PDF 提取的文字：`pdf_text_content`。
  - 从用户上传图片中提取的文字：`image_text_content`。
- 合并逻辑：
  - 有则追加到 `content_parts`：
    - `user_document`
    - `"--- PDF内容 ---\n\n{pdf_text_content}"`
    - `"--- 图片内容 ---\n\n{image_text_content}"`
  - 最终：`combined_document = "\n\n".join(content_parts)`。
  - 若 `combined_document` 为空，则返回 400 错误（必须提供文字 / PDF / 图片三者之一）。

---

### 5. 进入论文生成工作流

- 将 `combined_document` 作为 `user_document` 传入：
  - 非流式：`PaperGenerationWorkflow.execute(...)`
  - 流式：`PaperGenerationWorkflow.execute_stream(...)`
- 工作流内部按顺序调用三个 Agent：
  1. **PaperOverviewAgent**：生成论文概览文件。
  2. **LaTeXPaperGeneratorAgent**：生成 LaTeX 论文（可根据 `has_outline`、现有 `.tex` 决定是否跳过）。
  3. **RequirementChecklistAgent**：生成需求检查清单。
- 所有生成文件落盘到对应 `session` 的 `generated` 目录，上传的原始 PDF、图片则保存在 `uploaded` 目录。

---

### 6. 流式接口与非流式接口的差异（简要）

- **相同点**：
  - 都是：上传 PDF → `pdf_to_pngs` 转 PNG → VisionAgent OCR → 拼接成 `pdf_text_content` → 合并为 `combined_document` → 进入工作流。
- **不同点**：
  - 流式接口 `/execute/stream` 会：
    - 使用 Server-Sent Events（SSE）持续向前端推送进度日志。
    - 在处理 PDF/图片、调用工作流各阶段时发送 `WorkflowProgressChunk`。
    - 支持在客户端断开连接时中止任务并更新数据库中的任务状态。

---

### 7. 一句话总结

> **本项目中，PDF 不直接做文本解析，而是先转成高分辨率 PNG 图片，再用 Vision 大模型做 OCR+结构化提取，最后把得到的全文文本当作普通输入，交给后续的论文生成工作流。**


