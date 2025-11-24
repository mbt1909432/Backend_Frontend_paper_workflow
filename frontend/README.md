# ResearchFlow - 前端应用

这是一个现代化的 React + TypeScript 前端应用，用于调用后端提供的各个 Agent 能力。

## 功能特性

- 🎨 现代化的 UI 设计
- 💬 通用对话 Agent - 支持多轮对话和流式响应
- 📄 论文概览生成 - 根据文档生成论文概览
- 📝 LaTeX 论文生成 - 生成完整的 LaTeX 论文文件
- ✅ 需求清单生成 - 生成需求清单文件
- 📑 PDF 文档处理 - 上传 PDF 文件，使用 Vision Agent 提取文字内容
- 🔄 支持流式和非流式响应
- 📱 响应式设计，支持移动端

## 技术栈

- React 18
- TypeScript
- Vite
- React Router
- Axios
- CSS3

## 安装和运行

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

前端应用将在 `http://localhost:3000` 启动。

### 3. 确保后端服务运行

确保后端服务在 `http://localhost:8000` 运行。如果后端运行在不同的端口，请修改 `vite.config.ts` 中的代理配置。

## 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist/` 目录。

## 预览生产版本

```bash
npm run preview
```

## 项目结构

```
frontend/
├── src/
│   ├── components/          # React 组件
│   │   ├── AgentChat.tsx
│   │   ├── PaperOverview.tsx
│   │   ├── LaTeXPaper.tsx
│   │   ├── RequirementChecklist.tsx
│   │   └── PDFProcessor.tsx
│   ├── services/            # API 服务
│   │   └── api.ts
│   ├── types/               # TypeScript 类型定义
│   │   └── index.ts
│   ├── App.tsx              # 主应用组件
│   ├── App.css              # 应用样式
│   ├── main.tsx             # 入口文件
│   └── index.css            # 全局样式
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## API 端点

前端通过以下 API 端点与后端通信：

- `/api/v1/agent/chat` - 通用对话（非流式）
- `/api/v1/agent/chat/stream` - 通用对话（流式）
- `/api/v1/paper-overview/generate` - 论文概览生成（非流式）
- `/api/v1/paper-overview/generate/stream` - 论文概览生成（流式）
- `/api/v1/latex-paper/generate` - LaTeX 论文生成（非流式）
- `/api/v1/latex-paper/generate/stream` - LaTeX 论文生成（流式）
- `/api/v1/requirement-checklist/generate` - 需求清单生成（非流式）
- `/api/v1/requirement-checklist/generate/stream` - 需求清单生成（流式）
- `/api/v1/vision/pdf/process` - PDF 文档处理（将 PDF 转换为图片并使用 Vision Agent 提取文字）

## 使用说明

1. **通用对话 Agent**: 输入消息与 AI 进行对话，支持多轮对话和流式响应。

2. **论文概览生成**: 输入文档内容，AI 将生成结构化的论文概览文件。

3. **LaTeX 论文生成**: 输入论文概览内容，可以添加额外信息，生成完整的 LaTeX 论文。

4. **需求清单生成**: 输入论文概览和 LaTeX 内容（或原始输入），生成需求清单。

5. **PDF 文档处理**: 
   - 上传 PDF 文件（支持多页）
   - 自动将 PDF 转换为 PNG 图片（可自定义 DPI）
   - 使用 Vision Agent 逐页分析并提取文字描述
   - 自动拼接所有页面的内容
   - 查看每页的单独描述和整体结果
   - 支持下载提取的文本内容
   - 显示 Token 使用统计

每个页面都支持：
- 调整温度参数（0-2）
- 设置最大 Token 数
- 选择流式或非流式响应（PDF 处理除外）
- 查看 Token 使用情况

## 注意事项

- 确保后端服务已启动并运行在正确的端口
- 如果遇到 CORS 问题，检查后端的 CORS 配置
- 流式响应使用 Server-Sent Events (SSE) 实现

