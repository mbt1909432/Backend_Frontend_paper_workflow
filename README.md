# ResearchFlow

基于 FastAPI + OpenAI SDK 的 Agent 项目，支持流式响应，为后续 Agentic Workflow 扩展预留接口。

## 功能特性

- ✅ FastAPI 异步 Web 框架
- ✅ OpenAI SDK 集成
- ✅ 流式响应支持（Server-Sent Events）
- ✅ 自定义 Agent Endpoint
- ✅ 模块化架构设计
- ✅ Paper Overview Agent - 论文概览生成
- ✅ LaTeX Paper Generator Agent - LaTeX 论文生成
- ✅ Requirement Checklist Agent - 需求清单生成
- ✅ Vision Agent - PDF 文档处理和图片分析
- ✅ PDF 转 PNG 工具 - 支持多页 PDF 转换为图片
- ✅ 多图片上传支持 - 支持上传多张图片并提取文字内容
- ✅ 现代化前端界面（React + TypeScript）
- 🔄 为 Agentic Workflow 预留扩展点

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件并填入配置信息：

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

**环境变量示例（`.env` 文件内容）：**

```env
# OpenAI 配置（必需）
OPENAI_API_KEY=your_openai_api_key_here

# OpenAI 可选配置
OPENAI_API_BASE=https://api.openai.com/v1  # 自定义 API endpoint（用于模型转发商，不配置则使用默认）
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=2000

# Anthropic 配置（用于 Vision Agent，可选）
ANTHROPIC_API_KEY=your_anthropic_api_key_here  # Vision Agent 需要此配置
ANTHROPIC_API_BASE=https://api.anthropic.com  # 自定义 API endpoint（可选）
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022  # 默认模型

# 服务器配置（可选）
HOST=0.0.0.0
PORT=8000
DEBUG=True

# 日志配置（可选）
LOG_LEVEL=INFO
```

**注意：** 
- `OPENAI_API_KEY` 是必需配置（用于大部分 Agent）
- `ANTHROPIC_API_KEY` 是可选配置（用于 Vision Agent 和 PDF 处理功能）
- 其他配置项都有默认值，可根据需要修改

### 3. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 前端应用

项目包含一个现代化的 React + TypeScript 前端应用，可以单独调用各个 Agent 的能力。

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端应用将在 `http://localhost:3000` 启动。

### 前端功能

- 💬 **通用对话 Agent** - 支持多轮对话和流式响应
- 📄 **论文概览生成** - 根据文档生成论文概览
- 📝 **LaTeX 论文生成** - 生成完整的 LaTeX 论文文件
- ✅ **需求清单生成** - 生成需求清单文件
- 📑 **PDF 文档处理** - 上传 PDF 文件，使用 Vision Agent 提取文字内容
- 🖼️ **图片处理** - 上传多张图片，使用 Vision Agent 提取文字内容

每个功能都支持：
- 流式和非流式响应
- 自定义温度参数和最大 Token 数
- 查看 Token 使用情况

详细使用说明请参考 [frontend/README.md](frontend/README.md)。

## GitHub Actions：输出目录自动同步

如果需要在构建后自动把 `output/` 内容推送到服务器供 docker-compose 挂载，参考 `docs/sync-output-workflow.md` 中的工作流说明并配置仓库机密即可。

## API 端点

### Agent 对话

#### 非流式对话
```
POST /api/v1/agent/chat
```

#### 流式对话
```
POST /api/v1/agent/chat/stream
```

### Paper Overview Agent

#### 生成论文概览（非流式）
```
POST /api/v1/paper-overview/generate
```

**请求体示例：**
```json
{
  "document": "用户提供的文档内容...",
  "temperature": 0.7,
  "max_tokens": 4000,
  "model": "gpt-4"
}
```

**响应示例：**
```json
{
  "file_name": "Deep_Learning_Method_paper_overview.txt",
  "file_content": "Title: ...\nPaper Type: Method\n...",
  "raw_response": "```path\n...\n```\n```text\n...\n```",
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 500,
    "total_tokens": 600
  }
}
```

#### 流式生成论文概览
```
POST /api/v1/paper-overview/generate/stream
```

### LaTeX Paper Generator Agent

#### 生成 LaTeX 论文（非流式）
```
POST /api/v1/latex-paper/generate
```

**请求体示例：**
```json
{
  "paper_overview": "从 Paper Overview Agent 得到的文本内容...",
  "user_info": "用户提供的额外信息（可选）",
  "has_outline": false,
  "has_existing_tex": false,
  "temperature": 0.7,
  "max_tokens": 16000,
  "model": "gpt-4"
}
```

**响应示例（成功生成）：**
```json
{
  "file_name": "paper_framework.tex",
  "file_content": "\\documentclass[conference]{IEEEtran}...",
  "raw_response": "```path\n...\n```\n```latex\n...\n```",
  "is_skipped": false,
  "skip_reason": null,
  "usage": {
    "prompt_tokens": 500,
    "completion_tokens": 8000,
    "total_tokens": 8500
  }
}
```

**响应示例（跳过生成）：**
```json
{
  "file_name": null,
  "file_content": null,
  "raw_response": "SKIPPED: User provided outline",
  "is_skipped": true,
  "skip_reason": "User provided outline",
  "usage": {}
}
```

#### 流式生成 LaTeX 论文
```
POST /api/v1/latex-paper/generate/stream
```

### Requirement Checklist Agent

#### 生成需求清单（非流式）
```
POST /api/v1/requirement-checklist/generate
```

**请求体示例：**
```json
{
  "paper_overview": "从 Paper Overview Agent 得到的文本内容...",
  "latex_content": "从 LaTeX Paper Generator Agent 得到的 LaTeX 内容（如果 Agent 2 没有跳过）",
  "user_original_input": "用户原始输入（如果 Agent 2 SKIPPED 则使用此输入）",
  "temperature": 0.7,
  "max_tokens": 4000,
  "model": "gpt-4"
}
```

**说明：**
- `paper_overview`: 必需，从 Agent 1 (Paper Overview Agent) 得到的文本内容
- `latex_content`: 可选，如果 Agent 2 (LaTeX Paper Generator Agent) 没有跳过，则提供 LaTeX 内容
- `user_original_input`: 可选，如果 Agent 2 SKIPPED，则提供用户原始输入

**响应示例：**
```json
{
  "file_name": "requirements_checklist.md",
  "file_content": "# [Paper Title in English]\n\n─────────────────────────────────────────────────────────────────────────────\n📊 第一大类: 画图需求\n...",
  "raw_response": "```path\nrequirements_checklist.md\n```\n```markdown\n...\n```",
  "usage": {
    "prompt_tokens": 300,
    "completion_tokens": 1500,
    "total_tokens": 1800
  }
}
```

#### 流式生成需求清单
```
POST /api/v1/requirement-checklist/generate/stream
```

### Vision Agent - PDF 文档处理

#### 处理 PDF 文档
```
POST /api/v1/vision/pdf/process
```

**说明：** 此端点用于处理 PDF 文档，将 PDF 转换为图片后使用 Vision Agent 提取文字内容。

**请求格式：** `multipart/form-data`

**请求参数：**
- `file`: **必需**，PDF 文件（通过表单上传）
- `text_prompt`: 可选，自定义文本提示（默认：`"Please extract all text content from this image. Preserve the structure and formatting as much as possible."`）
- `temperature`: 可选，温度参数（默认：0.3）
- `max_tokens`: 可选，最大 token 数（默认：4096）
- `dpi`: 可选，PDF 转图片的 DPI（默认：300）

**响应示例：**
```json
{
  "success": true,
  "total_pages": 5,
  "combined_text": "从所有页面提取并拼接的完整文本内容...",
  "page_descriptions": [
    {
      "page_number": 1,
      "description": "第1页的文字内容...",
      "usage": {
        "input_tokens": 1000,
        "output_tokens": 500,
        "total_tokens": 1500
      }
    },
    {
      "page_number": 2,
      "description": "第2页的文字内容...",
      "usage": {
        "input_tokens": 1000,
        "output_tokens": 450,
        "total_tokens": 1450
      }
    }
  ],
  "total_usage": {
    "input_tokens": 5000,
    "output_tokens": 2500,
    "total_tokens": 7500
  }
}
```

**使用场景：**
- 处理扫描版 PDF 文档
- 提取 PDF 中的文字内容（特别是无法直接复制的情况）
- 将 PDF 内容转换为可编辑的文本格式

**注意事项：**
- 需要配置 `ANTHROPIC_API_KEY` 环境变量
- 大文件处理可能需要较长时间
- 临时图片文件会在处理完成后自动清理

### Paper Generation Workflow（论文生成工作流）

#### 执行完整工作流
```
POST /api/v1/workflow/execute
```

**说明：** 这个端点整合了三个 Agent，按顺序执行：
1. **Paper Overview Agent** - 生成论文概览文件 `[Paper_Title]_[Paper_Type]_paper_overview.txt`
2. **LaTeX Paper Generator Agent** - 生成 LaTeX 论文文件 `paper_framework.tex`
3. **Requirement Checklist Agent** - 生成需求清单文件 `requirements_checklist.md`

所有文件将保存在同一个 session 文件夹中（自动创建）。

**请求体示例：**
```json
{
  "document": "用户提供的文档内容...",
  "session_id": "optional_session_id",
  "user_info": "用户提供的额外信息（可选）",
  "has_outline": false,
  "has_existing_tex": false,
  "temperature": 0.7,
  "max_tokens": 16000,
  "model": "gpt-4"
}
```

**参数说明：**
- `document`: **必需**，用户提供的文档内容
- `session_id`: 可选，如果不提供则自动生成（格式：`session_YYYYMMDD_HHMMSS_uuid`）
- `user_info`: 可选，用户提供的额外信息（用于 LaTeX 生成）
- `has_outline`: 可选，用户是否提供了论文大纲（如果为 true，LaTeX 生成会被跳过）
- `has_existing_tex`: 可选，是否存在现有的 .tex 文件（如果为 true，LaTeX 生成会被跳过）
- `temperature`: 可选，温度参数（默认使用各 Agent 的默认值）
- `max_tokens`: 可选，最大 token 数（默认使用各 Agent 的默认值）
- `model`: 可选，模型名称（默认使用配置中的模型）

**响应示例：**
```json
{
  "session_id": "session_20240101_120000_abc12345",
  "session_folder": "output/session_20240101_120000_abc12345",
  "paper_overview": {
    "file_name": "Deep_Learning_Method_paper_overview.txt",
    "file_path": "output/session_20240101_120000_abc12345/Deep_Learning_Method_paper_overview.txt",
    "usage": {
      "prompt_tokens": 100,
      "completion_tokens": 500,
      "total_tokens": 600
    }
  },
  "latex_paper": {
    "file_name": "paper_framework.tex",
    "file_path": "output/session_20240101_120000_abc12345/paper_framework.tex",
    "is_skipped": false,
    "skip_reason": null,
    "usage": {
      "prompt_tokens": 500,
      "completion_tokens": 8000,
      "total_tokens": 8500
    }
  },
  "requirement_checklist": {
    "file_name": "requirements_checklist.md",
    "file_path": "output/session_20240101_120000_abc12345/requirements_checklist.md",
    "usage": {
      "prompt_tokens": 300,
      "completion_tokens": 1500,
      "total_tokens": 1800
    }
  },
  "total_usage": {
    "prompt_tokens": 900,
    "completion_tokens": 10000,
    "total_tokens": 10900
  }
}
```

**工作流特点：**
- ✅ 自动创建 session 文件夹，所有文件保存在同一文件夹中
- ✅ 按顺序执行三个 Agent，确保数据流正确传递
- ✅ 如果 LaTeX 生成被跳过，Requirement Checklist Agent 会使用用户原始输入
- ✅ 返回每个 Agent 的详细结果和 Token 使用情况
- ✅ 提供总 Token 使用情况统计

#### 工作流各步骤输入输出详解

工作流按顺序执行以下步骤：

```
[步骤0] 用户输入与PDF处理（API端点处理）
    ↓
[步骤1] Paper Overview Agent
    ↓
[步骤2] LaTeX Paper Generator Agent
    ↓
[步骤3] Requirement Checklist Agent
    ↓
最终输出 (三个文件)
```

##### 步骤0: 用户输入与PDF处理（预处理阶段）

**📥 用户输入 (User Input):**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `document` | `str` | ❌ | 用户提供的文字描述（可选） |
| `pdf_file` | `UploadFile` | ❌ | 用户上传的PDF文件（可选） |
| `image_files` | `List[UploadFile]` | ❌ | 用户上传的图片文件（可选，支持多张）<br>支持的格式：`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp` |
| `session_id` | `str` | ❌ | 可选的 session ID，如果不提供则自动生成 |
| `user_info` | `str` | ❌ | 用户提供的额外信息（用于后续步骤） |
| `has_outline` | `bool` | ❌ | 用户是否提供了论文大纲（默认: false） |
| `has_existing_tex` | `bool` | ❌ | 是否存在现有的 .tex 文件（默认: false） |
| `temperature` | `float` | ❌ | 温度参数（可选，覆盖默认配置） |
| `max_tokens` | `int` | ❌ | 最大token数（可选，覆盖默认配置） |
| `model` | `str` | ❌ | 模型名称（可选，覆盖默认配置） |

**⚠️ 注意：** `document`、`pdf_file` 和 `image_files` 至少需要提供一个。

**🔄 PDF处理流程（如果上传了PDF）：**
1. **PDF验证**：验证文件格式是否为 `.pdf`
2. **PDF转PNG**：将PDF的每一页转换为PNG图片（DPI: 300）
3. **文字提取**：使用 Vision Agent 并发处理所有页面，提取每页的文字内容
   - 提取提示词：`"请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"`
   - 并发处理所有页面，提高效率
4. **内容合并**：将所有页面的文字内容按顺序拼接

**🖼️ 图片处理流程（如果上传了图片）：**
1. **图片验证**：验证文件格式是否为支持的图片格式（`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`）
2. **图片保存**：将所有图片保存到 `session/uploaded/` 文件夹
3. **文字提取**：使用 Vision Agent 并发处理所有图片，提取每张图片的文字内容
   - 提取提示词：`"请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"`
   - 并发处理所有图片，提高效率
4. **内容合并**：将所有图片的文字内容按顺序拼接，每张图片的内容前添加标识：
   ```
   --- 图片 1: [filename] ---
   
   [extracted_text]
   
   --- 图片 2: [filename] ---
   
   [extracted_text]
   ...
   ```

**📝 文档合并逻辑：**
如果同时提供了多种输入，将按以下顺序合并：
```
{user_document}  (如果提供了文字描述)

--- PDF内容 ---  (如果上传了PDF)

{pdf_text_content}

--- 图片内容 ---  (如果上传了图片)

--- 图片 1: [filename] ---

[image_1_text]

--- 图片 2: [filename] ---

[image_2_text]
...
```

**📤 输出 (Output):**
| 字段 | 类型 | 说明 |
|------|------|------|
| `combined_document` | `str` | 合并后的文档内容（用于后续Agent）<br>包含：文字描述 + PDF提取文字 + 图片提取文字 |
| `pdf_file_path` | `str` or `None` | 保存的PDF文件路径（如果上传了PDF）<br>保存在：`session/uploaded/[filename].pdf` |
| `image_file_paths` | `List[str]` or `None` | 保存的图片文件路径列表（如果上传了图片）<br>保存在：`session/uploaded/[filename]` |
| `has_outline` | `bool` | 如果上传了PDF，自动设置为 `True`（将跳过LaTeX生成） |
| `session_folder` | `Path` | 创建的session文件夹路径 |

**📁 文件保存位置：**
- PDF文件：`output/session_YYYYMMDD_HHMMSS_uuid/uploaded/[filename].pdf`
- 图片文件：`output/session_YYYYMMDD_HHMMSS_uuid/uploaded/[image_filename]`
- 后续生成的文件：`output/session_YYYYMMDD_HHMMSS_uuid/generated/`

##### 步骤1: Paper Overview Agent（论文概览生成）

**📥 输入 (Input):**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `user_document` | `str` | ✅ | 从步骤0得到的合并文档内容（`combined_document`）<br>如果用户上传了PDF，此内容包含PDF提取的文字；<br>如果用户上传了图片，此内容包含图片提取的文字；<br>如果用户提供了文字描述，此内容包含用户文字；<br>如果多种输入都有，则包含合并后的所有内容 |
| `temperature` | `float` | ❌ | 温度参数（默认: 0.7） |
| `max_tokens` | `int` | ❌ | 最大token数（默认: 4000） |
| `model` | `str` | ❌ | 模型名称（可选，覆盖默认配置） |

**📤 输出 (Output):**
| 字段 | 类型 | 说明 |
|------|------|------|
| `file_name` | `str` | 生成的文件名，格式：`[Paper_Title]_[Paper_Type]_paper_overview.txt`<br>例如：`Deep_Learning_Method_paper_overview.txt` |
| `file_content` | `str` | 文件内容（纯文本），包含：<br>1. **Title**: 完整论文标题（英文）<br>2. **Paper Type**: Method 或 Survey<br>3. **Abstract**: 200-300字的摘要<br>4. **Research Content**: 研究内容描述<br>5. **Innovations**: 至少3个具体创新点<br>6. **Application Scenarios**: 应用场景 |
| `raw_response` | `str` | 原始响应（包含markdown格式） |
| `usage` | `dict` | Token使用情况：<br>`{prompt_tokens, completion_tokens, total_tokens}` |

**📄 输出文件示例：**
```
文件名: Deep_Learning_Method_paper_overview.txt

内容结构:
Title: [Full paper title in English]

Paper Type: Method

Abstract:
[200-300 words abstract including background, problem, solution, results, significance]

Research Content:
[What problem, methods, scenarios, goals]

Innovations:
1. [First innovation - specific and verifiable]
2. [Second innovation - specific and verifiable]
3. [Third innovation - specific and verifiable]

Application Scenarios:
[Realistic application scenarios]
```

##### 步骤2: LaTeX Paper Generator Agent（LaTeX 论文生成）

**📥 输入 (Input):**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `paper_overview` | `str` | ✅ | 从步骤1得到的论文概览文件内容 |
| `user_document` | `str` | ✅ | 从步骤0得到的合并文档内容（`combined_document`） |
| `user_info` | `str` | ❌ | 用户提供的额外信息（可选） |
| `has_outline` | `bool` | ❌ | 用户是否提供了论文大纲（如果为 true，会跳过生成） |
| `has_existing_tex` | `bool` | ❌ | 是否存在现有的 .tex 文件（如果为 true，会跳过生成） |
| `temperature` | `float` | ❌ | 温度参数（默认: 0.7） |
| `max_tokens` | `int` | ❌ | 最大token数（默认: 16000） |
| `model` | `str` | ❌ | 模型名称（可选，覆盖默认配置） |

**📤 输出 (Output):**
| 字段 | 类型 | 说明 |
|------|------|------|
| `file_name` | `str` or `None` | 生成的文件名（如果跳过则为 None），通常为 `paper_framework.tex` |
| `file_content` | `str` or `None` | LaTeX 文件内容（如果跳过则为 None） |
| `raw_response` | `str` | 原始响应（包含markdown格式或跳过信息） |
| `is_skipped` | `bool` | 是否跳过了生成 |
| `skip_reason` | `str` or `None` | 跳过原因（如果跳过）：<br>- "User provided outline"<br>- "Existing .tex file exists" |
| `usage` | `dict` | Token使用情况（如果跳过则为空字典） |

**⚠️ 跳过条件：**
- 如果 `has_outline=True`（用户提供了论文大纲或上传了PDF），则跳过生成
- 如果 `has_existing_tex=True`（session文件夹中已存在 .tex 文件），则跳过生成

**📄 输出文件示例（成功生成）：**
```
文件名: paper_framework.tex

内容: 完整的 LaTeX 论文代码，包含：
- 文档类定义（如 \documentclass[conference]{IEEEtran}）
- 必要的包导入
- 论文结构（Abstract, Introduction, Method, Experiments, Conclusion等）
- 占位符内容，等待后续填充
```

##### 步骤3: Requirement Checklist Agent（需求清单生成）

**📥 输入 (Input):**
| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `paper_overview` | `str` | ✅ | 从步骤1得到的论文概览文件内容 |
| `latex_content` | `str` | ❌ | 从步骤2得到的 LaTeX 内容（如果步骤2没有跳过） |
| `combined_document` | `str` | ❌ | 从步骤0得到的合并文档内容（如果步骤2跳过了，则使用此输入） |
| `temperature` | `float` | ❌ | 温度参数（默认: 0.7） |
| `max_tokens` | `int` | ❌ | 最大token数（默认: 4000） |
| `model` | `str` | ❌ | 模型名称（可选，覆盖默认配置） |

**📝 输入逻辑：**
- 如果步骤2成功生成 LaTeX：使用 `paper_overview` + `latex_content`
- 如果步骤2跳过：使用 `paper_overview` + `combined_document`（从步骤0得到的合并文档）

**📤 输出 (Output):**
| 字段 | 类型 | 说明 |
|------|------|------|
| `file_name` | `str` | 生成的文件名，固定为 `requirements_checklist.md` |
| `file_content` | `str` | Markdown 格式的需求清单内容 |
| `raw_response` | `str` | 原始响应（包含markdown格式） |
| `usage` | `dict` | Token使用情况 |

**📄 输出文件示例：**
```
文件名: requirements_checklist.md

内容结构:
# [Paper Title in English]

─────────────────────────────────────────────────────────────────────────────
📊 第一大类: 画图需求
─────────────────────────────────────────────────────────────────────────────

**1.1 算法图/Motivation图 (正文用):**
- [ ] 系统架构图 - 展示方法框架（放在Method章节，Method类型必需）
- [ ] 动机图 - 展示问题背景和动机（放在Introduction章节，可选）
- [ ] 算法流程图 - 展示关键算法步骤（放在Method章节，Method类型推荐）

**1.2 实验分析图 (实验部分用，Method类型为主):**
- [ ] 主实验结果对比图 - 与baseline对比（放在Experiments章节，Method类型必需）
- [ ] 消融实验结果图 - 展示各模块贡献（放在Experiments章节，Method类型推荐）

**1.3 Survey类型专用图表:**
- [ ] 方法分类对比图 - 展示不同方法类别（Survey类型推荐）
- [ ] 时间线图 - 展示领域发展历程（Survey类型推荐）

**1.4 表格:**
- [ ] 主实验结果表 - 对比各方法性能（Method类型必需）
- [ ] 消融实验结果表 - 各模块性能变化（Method类型推荐）

─────────────────────────────────────────────────────────────────────────────
✍️ 第二大类: 文字需求
─────────────────────────────────────────────────────────────────────────────

**2.1 第一部分: 摘要、引言**
- [ ] 摘要 (Abstract): 背景、问题、方法、结果、意义
- [ ] 引言 (Introduction): 动机、现有方法、局限、贡献、论文组织

**2.2 第二部分: 方法**
- [ ] 问题定义 - 数学符号定义输入、输出、目标
- [ ] 方法框架 - 整体流程描述（配合架构图）
- [ ] 核心模块 - 各模块详细说明和公式
- [ ] 算法伪代码 - 关键算法步骤

**2.3 第三部分: 实验分析**
- [ ] 实验设置 - 数据集、baseline、评估指标、实现细节
- [ ] 主实验结果 - 与baseline对比和分析
- [ ] 消融实验 - 各模块贡献分析
- [ ] 结果讨论 - 实验发现和原因分析
```

**📊 数据流图：**
```
用户输入
├─ document (文字描述，可选)
├─ pdf_file (PDF文件，可选)
└─ image_files (图片文件，可选，支持多张)
    ↓
[步骤0] 用户输入与PDF/图片处理
    如果上传PDF:
    ├─ PDF → PNG转换
    ├─ Vision Agent提取文字（并发处理所有页面）
    └─ pdf_text_content
    如果上传图片:
    ├─ 保存图片到 session/uploaded/
    ├─ Vision Agent提取文字（并发处理所有图片）
    └─ image_text_content
    合并所有输入:
    └─ combined_document = document + PDF文字 + 图片文字
    输出: combined_document, pdf_file_path, image_file_paths, has_outline
    ↓
[步骤1] Paper Overview Agent
    输入: combined_document (from step 0) - 包含文字/PDF/图片的所有内容
    输出: paper_overview (file_content)
    ↓
[步骤2] LaTeX Paper Generator Agent
    输入: paper_overview (from step 1), user_document (from step 0), has_outline (from step 0)
    输出: latex_content (file_content) 或 is_skipped=True
    ↓
[步骤3] Requirement Checklist Agent
    输入: paper_overview (from step 1) + 
         (latex_content from step 2 或 combined_document from step 0)
    输出: requirements_checklist.md
```

#### 流式执行工作流

```
POST /api/v1/workflow/execute/stream
```

**说明：** 流式执行完整工作流，支持 Server-Sent Events (SSE)，实时返回进度更新。

**请求格式：** `multipart/form-data`

**请求参数：**
- `document`: 可选，用户提供的文字描述
- `pdf_file`: 可选，用户上传的PDF文件
- `image_files`: 可选，用户上传的图片文件（支持多张，格式：`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.webp`）
- `session_id`: 可选，session ID
- `user_info`: 可选，用户提供的额外信息
- `has_outline`: 可选，用户是否提供了论文大纲（默认: false）
- `has_existing_tex`: 可选，是否存在现有的 .tex 文件（默认: false）
- `temperature`: 可选，温度参数
- `max_tokens`: 可选，最大token数
- `model`: 可选，模型名称

**响应格式：** Server-Sent Events (SSE)

**响应示例：**
```
data: {"type":"progress","step":0,"step_name":"初始化","message":"正在初始化工作流，Session ID: session_20240101_120000_abc12345","done":false}

data: {"type":"progress","step":1,"step_name":"生成论文概览","message":"步骤 1/3: 正在生成论文概览...","done":false}

data: {"type":"log","log":"正在分析用户输入...","done":false}

data: {"type":"progress","step":1,"step_name":"生成论文概览","message":"✓ 论文概览生成完成: Deep_Learning_Method_paper_overview.txt","done":false}

data: {"type":"progress","step":2,"step_name":"生成 LaTeX 论文","message":"步骤 2/3: 正在生成 LaTeX 论文...","done":false}

data: {"type":"log","log":"\\documentclass[conference]{IEEEtran}","done":false}

data: {"type":"log","log":"\\usepackage{...}","done":false}

...

data: {"type":"progress","step":2,"step_name":"生成 LaTeX 论文","message":"✓ LaTeX 论文生成完成: paper_framework.tex","done":false}

data: {"type":"progress","step":3,"step_name":"生成需求清单","message":"步骤 3/3: 正在生成需求清单...","done":false}

data: {"type":"progress","step":3,"step_name":"生成需求清单","message":"✓ 需求清单生成完成: requirements_checklist.md","done":false}

data: {"type":"result","step":3,"step_name":"完成","message":"工作流执行完成！","done":true,"result":{...}}
```

**流式响应类型：**
- `progress`: 进度更新（包含步骤编号、步骤名称、消息）
- `log`: 日志信息（用于显示 LaTeX 生成过程中的实时内容）
- `result`: 最终结果（包含完整的工作流响应数据）

### 健康检查
```
GET /api/v1/health
```

## 项目结构

详见 `项目架构图.md`

