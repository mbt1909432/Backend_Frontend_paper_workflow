import axios from 'axios';
import type {
  ChatRequest,
  ChatResponse,
  PaperOverviewRequest,
  PaperOverviewResponse,
  LaTeXPaperRequest,
  LaTeXPaperResponse,
  RequirementChecklistRequest,
  RequirementChecklistResponse,
  PaperGenerationWorkflowRequest,
  PaperGenerationWorkflowResponse,
  StreamChunk,
  PDFProcessRequest,
  PDFProcessResponse,
} from '../types';

const API_BASE_URL = '/api/v1';

// 获取认证头的辅助函数
function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('auth_token');
  const headers: HeadersInit = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// 创建 axios 实例
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 添加请求拦截器，自动添加token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 添加响应拦截器，处理401错误
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      localStorage.removeItem('auth_user');
      // 重定向到登录页（如果不在登录页）
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Agent API
export const agentApi = {
  // 非流式聊天
  async chat(request: ChatRequest): Promise<ChatResponse> {
    const response = await apiClient.post<ChatResponse>('/agent/chat', request);
    return response.data;
  },

  // 流式聊天
  async chatStream(
    request: ChatRequest,
    onChunk: (chunk: StreamChunk) => void,
    onError?: (error: Error) => void
  ): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/agent/chat/stream`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (onError) {
        onError(error instanceof Error ? error : new Error(String(error)));
      } else {
        throw error;
      }
    }
  },
};

// Paper Overview API
export const paperOverviewApi = {
  // 非流式生成
  async generate(request: PaperOverviewRequest): Promise<PaperOverviewResponse> {
    const response = await apiClient.post<PaperOverviewResponse>(
      '/paper-overview/generate',
      request
    );
    return response.data;
  },

  // 流式生成
  async generateStream(
    request: PaperOverviewRequest,
    onChunk: (chunk: StreamChunk) => void,
    onError?: (error: Error) => void
  ): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/paper-overview/generate/stream`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (onError) {
        onError(error instanceof Error ? error : new Error(String(error)));
      } else {
        throw error;
      }
    }
  },
};

// LaTeX Paper API
export const latexPaperApi = {
  // 非流式生成
  async generate(request: LaTeXPaperRequest): Promise<LaTeXPaperResponse> {
    const response = await apiClient.post<LaTeXPaperResponse>(
      '/latex-paper/generate',
      request
    );
    return response.data;
  },

  // 流式生成
  async generateStream(
    request: LaTeXPaperRequest,
    onChunk: (chunk: StreamChunk) => void,
    onError?: (error: Error) => void
  ): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/latex-paper/generate/stream`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (onError) {
        onError(error instanceof Error ? error : new Error(String(error)));
      } else {
        throw error;
      }
    }
  },
};

// Requirement Checklist API
export const requirementChecklistApi = {
  // 非流式生成
  async generate(request: RequirementChecklistRequest): Promise<RequirementChecklistResponse> {
    const response = await apiClient.post<RequirementChecklistResponse>(
      '/requirement-checklist/generate',
      request
    );
    return response.data;
  },

  // 流式生成
  async generateStream(
    request: RequirementChecklistRequest,
    onChunk: (chunk: StreamChunk) => void,
    onError?: (error: Error) => void
  ): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/requirement-checklist/generate/stream`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (onError) {
        onError(error instanceof Error ? error : new Error(String(error)));
      } else {
        throw error;
      }
    }
  },
};

// Workflow API
export const workflowApi = {
  // 执行完整工作流（非流式）
  async execute(
    request: PaperGenerationWorkflowRequest & { pdfFile?: File; imageFiles?: File[] }
  ): Promise<PaperGenerationWorkflowResponse> {
    const formData = new FormData();
    
    if (request.document) {
      formData.append('document', request.document);
    }
    if (request.pdfFile) {
      formData.append('pdf_file', request.pdfFile);
    }
    if (request.imageFiles && request.imageFiles.length > 0) {
      request.imageFiles.forEach((file) => {
        formData.append('image_files', file);
      });
    }
    if (request.session_id) {
      formData.append('session_id', request.session_id);
    }
    if (request.user_info) {
      formData.append('user_info', request.user_info);
    }
    if (request.has_outline !== undefined) {
      formData.append('has_outline', request.has_outline.toString());
    }
    if (request.has_existing_tex !== undefined) {
      formData.append('has_existing_tex', request.has_existing_tex.toString());
    }
    if (request.temperature !== undefined) {
      formData.append('temperature', request.temperature.toString());
    }
    if (request.max_tokens !== undefined) {
      formData.append('max_tokens', request.max_tokens.toString());
    }
    if (request.model) {
      formData.append('model', request.model);
    }

    // 获取认证 token
    const token = localStorage.getItem('auth_token');
    const headers: HeadersInit = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

      const response = await fetch(`${API_BASE_URL}/workflow/execute`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    return response.json();
  },

  // 流式执行完整工作流
  async executeStream(
    request: PaperGenerationWorkflowRequest & { pdfFile?: File; imageFiles?: File[] },
    onChunk: (chunk: import('../types').WorkflowProgressChunk) => void,
    onError?: (error: Error) => void,
    abortController?: AbortController
  ): Promise<void> {
    try {
      const formData = new FormData();
      
      if (request.document) {
        formData.append('document', request.document);
      }
      if (request.pdfFile) {
        formData.append('pdf_file', request.pdfFile);
      }
      if (request.imageFiles && request.imageFiles.length > 0) {
        request.imageFiles.forEach((file) => {
          formData.append('image_files', file);
        });
      }
      if (request.session_id) {
        formData.append('session_id', request.session_id);
      }
      if (request.user_info) {
        formData.append('user_info', request.user_info);
      }
      if (request.has_outline !== undefined) {
        formData.append('has_outline', request.has_outline.toString());
      }
      if (request.has_existing_tex !== undefined) {
        formData.append('has_existing_tex', request.has_existing_tex.toString());
      }
      if (request.temperature !== undefined) {
        formData.append('temperature', request.temperature.toString());
      }
      if (request.max_tokens !== undefined) {
        formData.append('max_tokens', request.max_tokens.toString());
      }
      if (request.model) {
        formData.append('model', request.model);
      }
      if (request.task_id) {
        formData.append('task_id', request.task_id);
      }

      const response = await fetch(`${API_BASE_URL}/workflow/execute/stream`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
        signal: abortController?.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Response body is not readable');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        // 检查是否已取消
        if (abortController?.signal.aborted) {
          reader.cancel();
          break;
        }
        
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', e, line);
            }
          }
        }
      }

      // 处理剩余的 buffer
      if (buffer.trim()) {
        const lines = buffer.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              onChunk(data);
            } catch (e) {
              console.error('Failed to parse SSE data:', e, line);
            }
          }
        }
      }
    } catch (error) {
      if (onError) {
        onError(error instanceof Error ? error : new Error(String(error)));
      } else {
        throw error;
      }
    }
  },

  // 列出所有 sessions
  async listSessions(): Promise<{ sessions: Array<{
    session_id: string;
    created_at: string;
    size: number;
    file_count: number;
  }> }> {
    const response = await apiClient.get<{ sessions: Array<{
      session_id: string;
      created_at: string;
      size: number;
      file_count: number;
    }> }>('/workflow/sessions');
    return response.data;
  },

  // 删除 session
  async deleteSession(sessionId: string): Promise<{ success: boolean; message: string }> {
    // 设置30秒超时，避免删除操作卡住
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    
    try {
      // 使用查询参数而不是路径参数，因为 sessionId 可能包含斜杠
      const encodedSessionId = encodeURIComponent(sessionId);
      const response = await fetch(`${API_BASE_URL}/workflow/session?session_id=${encodedSessionId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
      }

      return response.json();
    } catch (err) {
      clearTimeout(timeoutId);
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('删除操作超时，请稍后重试');
      }
      throw err;
    }
  },

  // 获取 session 详细信息
  async getSessionDetails(sessionId: string): Promise<{
    artifacts: Record<string, any>;
    uploaded_files: Array<{ name: string; size: number }>;
    generated_files: Record<string, { content: string | null; size: number; is_binary?: boolean }>;
  }> {
    const encodedSessionId = encodeURIComponent(sessionId);
    const response = await apiClient.get<{
      artifacts: Record<string, any>;
      uploaded_files: Array<{ name: string; size: number }>;
      generated_files: Record<string, { content: string | null; size: number; is_binary?: boolean }>;
    }>(`/workflow/session?session_id=${encodedSessionId}`);
    return response.data;
  },

  // 下载文件（支持uploaded、generated、artifact三种类型）
  async downloadFile(
    sessionId: string,
    fileName: string,
    fileType: 'uploaded' | 'generated' | 'artifact' = 'uploaded'
  ): Promise<Blob> {
    const encodedSessionId = encodeURIComponent(sessionId);
    const encodedFileName = encodeURIComponent(fileName);
    const encodedFileType = encodeURIComponent(fileType);
    const response = await fetch(
      `${API_BASE_URL}/workflow/session/download?session_id=${encodedSessionId}&file_name=${encodedFileName}&file_type=${encodedFileType}`,
      {
        headers: getAuthHeaders(),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    return response.blob();
  },

  // 下载上传的文件（向后兼容）
  async downloadUploadedFile(sessionId: string, fileName: string): Promise<Blob> {
    return this.downloadFile(sessionId, fileName, 'uploaded');
  },
};

// PDF 处理 API
export const pdfProcessApi = {
  // 处理 PDF 文件
  async process(
    file: File,
    options?: PDFProcessRequest
  ): Promise<PDFProcessResponse> {
    const formData = new FormData();
    formData.append('file', file);
    
    if (options?.text_prompt) {
      formData.append('text_prompt', options.text_prompt);
    }
    if (options?.temperature !== undefined) {
      formData.append('temperature', options.temperature.toString());
    }
    if (options?.max_tokens !== undefined) {
      formData.append('max_tokens', options.max_tokens.toString());
    }
    if (options?.model) {
      formData.append('model', options.model);
    }
    if (options?.dpi !== undefined) {
      formData.append('dpi', options.dpi.toString());
    }
    
    const response = await fetch(`${API_BASE_URL}/vision/pdf/process`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: formData,
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    
    return response.json();
  },
};

// 认证API
export interface LoginResponse {
  access_token: string;
  token_type?: string;
  username: string;
  is_admin: boolean;
  user_type: string;
}

export const authApi = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await apiClient.post<LoginResponse>('/auth/login', {
      username,
      password,
    });
    return response.data;
  },
  
  async getCurrentUser() {
    const response = await apiClient.get('/auth/me');
    return response.data;
  },
};

// Token 使用统计 API
export interface TokenUsageSummary {
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  record_count: number;
}

export interface TokenUsageByStage {
  stage: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  record_count: number;
}

export interface TokenUsageByModel {
  model: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  record_count: number;
}

export interface TokenUsageDetail {
  id: string;
  session_id: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  model: string | null;
  stage: string | null;
  created_at: string;
}

export interface TokenUsageResponse {
  summary: TokenUsageSummary;
  by_stage: TokenUsageByStage[];
  by_model: TokenUsageByModel[];
  recent_records: TokenUsageDetail[];
  token_balance: number;  // 用户当前token余额
}

export interface TokenBalanceResponse {
  token_balance: number;
  is_overdraft: boolean;  // 是否欠费
}

export const tokenUsageApi = {
  async getSummary(days: number = 30): Promise<TokenUsageResponse> {
    const response = await apiClient.get<TokenUsageResponse>(`/token-usage/summary?days=${days}`);
    return response.data;
  },
  
  async getAll(limit: number = 100, offset: number = 0): Promise<TokenUsageDetail[]> {
    const response = await apiClient.get<TokenUsageDetail[]>(`/token-usage/all?limit=${limit}&offset=${offset}`);
    return response.data;
  },
  
  async getBalance(): Promise<TokenBalanceResponse> {
    const response = await apiClient.get<TokenBalanceResponse>(`/token-usage/balance`);
    return response.data;
  },
};

// 工作流任务 API
export interface WorkflowTaskResponse {
  id: string;
  task_id: string;
  name: string | null;
  status: string;
  document: string | null;
  user_info: string | null;
  session_id: string | null;
  has_outline: boolean;
  has_existing_tex: boolean;
  temperature: string | null;
  max_tokens: string | null;
  error: string | null;
  current_step: string | null;
  logs: string[];
  response: PaperGenerationWorkflowResponse | null;
  pdf_file_info: { name: string; size: number; type: string } | null;
  image_files_info: Array<{ name: string; size: number; type: string }>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface WorkflowTaskCreate {
  name?: string;
  document?: string;
  user_info?: string;
  session_id?: string;
  has_outline?: boolean;
  has_existing_tex?: boolean;
  temperature?: number;
  max_tokens?: number;
}

export interface WorkflowTaskUpdate {
  name?: string;
  document?: string;
  user_info?: string;
  session_id?: string;
  status?: string;
  has_outline?: boolean;
  has_existing_tex?: boolean;
  temperature?: number;
  max_tokens?: number;
  error?: string | null;
  current_step?: string | null;
  logs?: string[];
  response?: PaperGenerationWorkflowResponse | null;
  pdf_file_info?: { name: string; size: number; type: string } | null;
  image_files_info?: Array<{ name: string; size: number; type: string }>;
}

export const workflowTasksApi = {
  // 获取所有任务
  async list(): Promise<WorkflowTaskResponse[]> {
    const response = await apiClient.get<WorkflowTaskResponse[]>('/workflow/tasks/');
    return response.data;
  },

  // 获取单个任务
  async get(taskId: string): Promise<WorkflowTaskResponse> {
    const response = await apiClient.get<WorkflowTaskResponse>(`/workflow/tasks/${taskId}`);
    return response.data;
  },

  // 创建任务
  async create(taskData: WorkflowTaskCreate): Promise<WorkflowTaskResponse> {
    const response = await apiClient.post<WorkflowTaskResponse>('/workflow/tasks/', taskData);
    return response.data;
  },

  // 更新任务
  async update(taskId: string, taskData: WorkflowTaskUpdate): Promise<WorkflowTaskResponse> {
    const response = await apiClient.put<WorkflowTaskResponse>(`/workflow/tasks/${taskId}`, taskData);
    return response.data;
  },

  // 删除任务
  async delete(taskId: string): Promise<void> {
    await apiClient.delete(`/workflow/tasks/${taskId}`);
  },
};

