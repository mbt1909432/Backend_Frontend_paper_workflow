import axios from 'axios';

// 支持环境变量配置 API 地址，默认使用相对路径（适用于同域部署）
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

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
    const token = localStorage.getItem('admin_token');
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
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

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
};

// 用户管理API
export interface User {
  id: string;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  user_type: string;
  token_balance: number;
  max_concurrent_workflows: number;
  created_at: string;
}

export interface CreateUserRequest {
  username: string;
  password: string;
  user_type?: string;
}

export interface UpdateUserRequest {
  password?: string;
  is_active?: boolean;
  user_type?: string;
}

export interface UpdateTokenBalanceRequest {
  token_balance: number;
}

export interface UpdateMaxConcurrentWorkflowsRequest {
  max_concurrent_workflows: number;
}

export const userApi = {
  async listUsers(): Promise<User[]> {
    const response = await apiClient.get<User[]>('/admin/users');
    return response.data;
  },

  async getUser(userId: string): Promise<User> {
    const response = await apiClient.get<User>(`/admin/users/${userId}`);
    return response.data;
  },

  async createUser(data: CreateUserRequest): Promise<User> {
    const response = await apiClient.post<User>('/admin/users', data);
    return response.data;
  },

  async updateUser(userId: string, data: UpdateUserRequest): Promise<User> {
    const response = await apiClient.put<User>(`/admin/users/${userId}`, data);
    return response.data;
  },

  async deleteUser(userId: string): Promise<void> {
    await apiClient.delete(`/admin/users/${userId}`);
  },

  async updateTokenBalance(userId: string, data: UpdateTokenBalanceRequest): Promise<User> {
    const response = await apiClient.patch<User>(`/admin/users/${userId}/token-balance`, data);
    return response.data;
  },

  async updateMaxConcurrentWorkflows(userId: string, data: UpdateMaxConcurrentWorkflowsRequest): Promise<User> {
    const response = await apiClient.patch<User>(`/admin/users/${userId}/max-concurrent-workflows`, data);
    return response.data;
  },
};

