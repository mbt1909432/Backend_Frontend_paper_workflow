// API 请求和响应类型定义

export interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  messages?: Message[];
  temperature?: number;
  max_tokens?: number;
  model?: string;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface StreamChunk {
  chunk: string;
  done: boolean;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface PaperOverviewRequest {
  document: string;
  temperature?: number;
  max_tokens?: number;
  model?: string;
}

export interface PaperOverviewResponse {
  file_name: string;
  file_content: string;
  raw_response: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface LaTeXPaperRequest {
  paper_overview: string;
  user_info?: string;
  has_outline?: boolean;
  has_existing_tex?: boolean;
  temperature?: number;
  max_tokens?: number;
  model?: string;
}

export interface LaTeXPaperResponse {
  file_name?: string;
  file_content?: string;
  raw_response: string;
  is_skipped: boolean;
  skip_reason?: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface RequirementChecklistRequest {
  paper_overview: string;
  latex_content?: string;
  user_original_input?: string;
  temperature?: number;
  max_tokens?: number;
  model?: string;
}

export interface RequirementChecklistResponse {
  file_name: string;
  file_content: string;
  raw_response: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

// Workflow API 类型定义
export interface PaperGenerationWorkflowRequest {
  document: string;
  session_id?: string;
  user_info?: string;
  has_outline?: boolean;
  has_existing_tex?: boolean;
  temperature?: number;
  max_tokens?: number;
  model?: string;
  task_id?: string;
}

export interface PaperOverviewResult {
  file_name: string;
  file_path: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface LaTeXPaperResult {
  file_name?: string;
  file_path?: string;
  is_skipped: boolean;
  skip_reason?: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface RequirementChecklistResult {
  file_name: string;
  file_path: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface PaperGenerationWorkflowResponse {
  session_id: string;
  session_folder: string;
  paper_overview: PaperOverviewResult;
  latex_paper: LaTeXPaperResult;
  requirement_checklist: RequirementChecklistResult;
  total_usage: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface WorkflowProgressChunk {
  type: 'progress' | 'log' | 'result' | 'error';
  step?: number;
  step_name?: string;
  message?: string;
  log?: string;
  done: boolean;
  result?: PaperGenerationWorkflowResponse;
}

// PDF 处理 API 类型定义
export interface PDFProcessRequest {
  text_prompt?: string;
  temperature?: number;
  max_tokens?: number;
  model?: string;
  dpi?: number;
}

export interface PDFProcessResponse {
  response: string;
  page_count: number;
  page_descriptions: string[];
  total_usage: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
  };
  raw_response: string;
}

// 任务管理相关类型定义
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'deleting';

export interface WorkflowTask {
  id: string; // 任务唯一ID
  name: string; // 任务名称（用户可编辑）
  status: TaskStatus;
  createdAt: Date;
  updatedAt: Date;
  // 任务输入
  document: string;
  userInfo: string;
  sessionId: string;
  pdfFile: File | null;
  imageFiles: File[];
  hasOutline: boolean;
  hasExistingTex: boolean;
  temperature: number | undefined;
  maxTokens: number | undefined;
  // 任务输出
  response: PaperGenerationWorkflowResponse | null;
  error: string | null;
  currentStep: string;
  logs: string[];
}

