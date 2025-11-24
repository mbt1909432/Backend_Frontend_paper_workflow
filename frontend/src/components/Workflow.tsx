import { useState, useRef, useEffect, useCallback } from 'react';
import { workflowApi, workflowTasksApi, authApi } from '../services/api';
import { useTaskContext } from '../contexts/TaskContext';
import type { PaperGenerationWorkflowRequest, PaperGenerationWorkflowResponse, WorkflowProgressChunk, WorkflowTask, TaskStatus } from '../types';

// localStorage 键名
const TASKS_STORAGE_KEY = 'workflow_tasks';
const ACTIVE_TASK_ID_KEY = 'workflow_active_task_id';

// 序列化任务（排除 File 对象，因为无法序列化）
interface SerializableTask {
  id: string;
  name: string;
  status: TaskStatus;
  createdAt: string; // ISO 字符串
  updatedAt: string; // ISO 字符串
  document: string;
  userInfo: string;
  sessionId: string;
  // File 对象信息（仅保存元数据）
  pdfFileInfo: { name: string; size: number; type: string } | null;
  imageFilesInfo: Array<{ name: string; size: number; type: string }>;
  hasOutline: boolean;
  hasExistingTex: boolean;
  temperature: number | undefined;
  maxTokens: number | undefined;
  response: PaperGenerationWorkflowResponse | null;
  error: string | null;
  currentStep: string;
  logs: string[];
}

// 将任务转换为可序列化格式
function serializeTask(task: WorkflowTask): SerializableTask {
  return {
    id: task.id,
    name: task.name,
    status: task.status,
    createdAt: task.createdAt.toISOString(),
    updatedAt: task.updatedAt.toISOString(),
    document: task.document,
    userInfo: task.userInfo,
    sessionId: task.sessionId,
    pdfFileInfo: task.pdfFile ? {
      name: task.pdfFile.name,
      size: task.pdfFile.size,
      type: task.pdfFile.type,
    } : null,
    imageFilesInfo: task.imageFiles.map(file => ({
      name: file.name,
      size: file.size,
      type: file.type,
    })),
    hasOutline: task.hasOutline,
    hasExistingTex: task.hasExistingTex,
    temperature: task.temperature,
    maxTokens: task.maxTokens,
    response: task.response,
    error: task.error,
    currentStep: task.currentStep,
    logs: task.logs,
  };
}

// 从序列化格式恢复任务（File 对象无法恢复，设为 null）
function deserializeTask(serialized: SerializableTask): WorkflowTask {
  return {
    id: serialized.id,
    name: serialized.name,
    status: serialized.status,
    createdAt: new Date(serialized.createdAt),
    updatedAt: new Date(serialized.updatedAt),
    document: serialized.document,
    userInfo: serialized.userInfo,
    sessionId: serialized.sessionId,
    pdfFile: null, // File 对象无法从 localStorage 恢复
    imageFiles: [], // File 对象无法从 localStorage 恢复
    hasOutline: serialized.hasOutline,
    hasExistingTex: serialized.hasExistingTex,
    temperature: serialized.temperature,
    maxTokens: serialized.maxTokens,
    response: serialized.response,
    error: serialized.error,
    currentStep: serialized.currentStep,
    logs: serialized.logs,
  };
}

// 保存任务到 localStorage
function saveTasksToStorage(tasks: WorkflowTask[]): void {
  try {
    const serialized = tasks.map(serializeTask);
    localStorage.setItem(TASKS_STORAGE_KEY, JSON.stringify(serialized));
  } catch (error) {
    console.error('保存任务到 localStorage 失败:', error);
  }
}

// 从 localStorage 加载任务
function loadTasksFromStorage(): WorkflowTask[] {
  try {
    const stored = localStorage.getItem(TASKS_STORAGE_KEY);
    if (!stored) return [];
    
    const serialized = JSON.parse(stored) as SerializableTask[];
    return serialized.map(deserializeTask);
  } catch (error) {
    console.error('从 localStorage 加载任务失败:', error);
    return [];
  }
}

// 保存当前活动任务ID
function saveActiveTaskId(taskId: string | null): void {
  try {
    if (taskId) {
      localStorage.setItem(ACTIVE_TASK_ID_KEY, taskId);
    } else {
      localStorage.removeItem(ACTIVE_TASK_ID_KEY);
    }
  } catch (error) {
    console.error('保存活动任务ID失败:', error);
  }
}

// 加载当前活动任务ID
function loadActiveTaskId(): string | null {
  try {
    return localStorage.getItem(ACTIVE_TASK_ID_KEY);
  } catch (error) {
    console.error('加载活动任务ID失败:', error);
    return null;
  }
}

// 生成任务ID
function generateTaskId(): string {
  return `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// 生成任务名称
function generateTaskName(index: number): string {
  return `任务 ${index}`;
}

// 检查任务是否正在处理文件（PDF或图片）
function isProcessingFile(task: WorkflowTask | null | undefined): boolean {
  if (!task || task.status !== 'running') return false;
  
  // 检查 currentStep
  const currentStepLower = (task.currentStep || '').toLowerCase();
  
  // 如果已经进入论文生成步骤（步骤1/3、步骤2/3、步骤3/3），允许删除
  // 这些步骤不是文件处理，应该允许删除
  if (currentStepLower.includes('步骤 1/3') || 
      currentStepLower.includes('步骤1/3') ||
      currentStepLower.includes('步骤 2/3') || 
      currentStepLower.includes('步骤2/3') ||
      currentStepLower.includes('步骤 3/3') || 
      currentStepLower.includes('步骤3/3') ||
      currentStepLower.includes('正在生成论文概览') ||
      currentStepLower.includes('正在生成latex') ||
      currentStepLower.includes('正在生成需求清单')) {
    return false; // 这些步骤允许删除
  }
  
  // 检查 logs 数组中的最新消息（取最后几条日志）
  const recentLogs = task.logs.slice(-5).join(' ').toLowerCase();
  const allText = (currentStepLower + ' ' + recentLogs).toLowerCase();
  
  // 检查是否正在处理图片（更精确的匹配）
  const isProcessingImages = allText.includes('处理图片') ||
                             allText.includes('正在处理图片') ||
                             (allText.includes('正在处理') && (allText.includes('图片') || allText.includes('image'))) ||
                             (allText.includes('提取文字') && !currentStepLower.includes('正在生成论文概览')) ||
                             allText.includes('ocr') ||
                             allText.includes('vision') ||
                             allText.includes('转换为图片');
  
  // 检查是否正在处理PDF（更精确的匹配）
  const isProcessingPDF = allText.includes('正在处理pdf') ||
                          allText.includes('处理pdf文件') ||
                          allText.includes('正在处理pdf文件') ||
                          allText.includes('正在将pdf转换为图片') ||
                          allText.includes('pdf已转换为') ||
                          allText.includes('pdf转换为') ||
                          allText.includes('pdf转图片');
  
  return isProcessingImages || isProcessingPDF;
}

function Workflow() {
  // 任务管理状态 - 从后端 API 初始化
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const { setTasks: setTasksContext } = useTaskContext();
  const [isLoadingTasks, setIsLoadingTasks] = useState(true);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(() => {
    // 从 localStorage 加载活动任务ID（仅作为初始值，后续会验证）
    return loadActiveTaskId();
  });
  
  // 删除确认弹窗状态
  const [deleteConfirmTaskId, setDeleteConfirmTaskId] = useState<string | null>(null);
  
  // 用户并发数信息
  const [maxConcurrentWorkflows, setMaxConcurrentWorkflows] = useState<number>(10);
  
  // 当前任务的状态（从 tasks 中获取）
  const activeTask = tasks.find(t => t.id === activeTaskId) || null;
  
  // 计算当前运行中的任务数
  const runningTasksCount = tasks.filter(t => t.status === 'running').length;
  
  // 表单引用
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  
  // 跟踪每个任务的AbortController，用于取消正在运行的请求
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

  // 更新任务列表并同步到 Context
  const updateTasks = useCallback((newTasks: WorkflowTask[] | ((prev: WorkflowTask[]) => WorkflowTask[])) => {
    if (typeof newTasks === 'function') {
      setTasks(prevTasks => {
        const updatedTasks = newTasks(prevTasks);
        // 同步到 Context
        setTasksContext(updatedTasks);
        return updatedTasks;
      });
    } else {
      setTasks(newTasks);
      setTasksContext(newTasks);
    }
  }, [setTasksContext]);

  // 检查是否有正在运行的任务
  // 取消所有正在运行的任务
  const cancelAllRunningTasks = useCallback(() => {
    tasks.forEach(task => {
      if (task.status === 'running') {
        const abortController = abortControllersRef.current.get(task.id);
        if (abortController) {
          abortController.abort();
          abortControllersRef.current.delete(task.id);
        }
        // 更新任务状态为失败
        updateTasks(prev => prev.map(t => 
          t.id === task.id 
            ? { ...t, status: 'failed' as TaskStatus, error: '任务已取消（因切换页面）', currentStep: '任务已取消' }
            : t
        ));
      }
    });
  }, [tasks, updateTasks]);

  // 监听来自 NavBar 的取消所有任务事件
  useEffect(() => {
    const handleCancelAll = () => {
      cancelAllRunningTasks();
    };
    
    window.addEventListener('cancelAllRunningTasks', handleCancelAll);
    return () => {
      window.removeEventListener('cancelAllRunningTasks', handleCancelAll);
    };
  }, [cancelAllRunningTasks]);

  // 获取用户信息（包括并发数）
  useEffect(() => {
    const loadUserInfo = async () => {
      try {
        const userInfo = await authApi.getCurrentUser();
        if (userInfo.max_concurrent_workflows !== undefined) {
          setMaxConcurrentWorkflows(userInfo.max_concurrent_workflows);
        }
      } catch (error) {
        console.error('获取用户信息失败:', error);
      }
    };
    loadUserInfo();
  }, []);

  // 从后端加载任务列表
  useEffect(() => {
    const loadTasks = async () => {
      try {
        setIsLoadingTasks(true);
        const response = await workflowTasksApi.list();
        
        // 将 API 响应转换为 WorkflowTask 格式
        const convertedTasks: WorkflowTask[] = response.map(task => ({
          id: task.id,
          name: task.name || `任务 ${task.task_id}`,
          status: task.status as TaskStatus,
          createdAt: new Date(task.created_at),
          updatedAt: new Date(task.updated_at),
          document: task.document || '',
          userInfo: task.user_info || '',
          sessionId: task.session_id || '',
          pdfFile: null, // File 对象无法从 API 恢复
          imageFiles: [], // File 对象无法从 API 恢复
          hasOutline: task.has_outline,
          hasExistingTex: task.has_existing_tex,
          temperature: task.temperature ? parseFloat(task.temperature) : undefined,
          maxTokens: task.max_tokens ? parseInt(task.max_tokens) : undefined,
          response: task.response,
          error: task.error,
          currentStep: task.current_step || '',
          logs: task.logs || [],
        }));
        
        updateTasks(convertedTasks);
        
        // 验证并设置活动任务ID
        if (activeTaskId && convertedTasks.some(t => t.id === activeTaskId)) {
          setActiveTaskId(activeTaskId);
        } else if (convertedTasks.length > 0) {
          // 如果没有有效的活动任务，选择第一个
          setActiveTaskId(convertedTasks[0].id);
        } else {
          setActiveTaskId(null);
        }
      } catch (error) {
        console.error('加载任务失败:', error);
        // 如果 API 失败，尝试从 localStorage 加载（作为 fallback）
        const fallbackTasks = loadTasksFromStorage();
        updateTasks(fallbackTasks);
      } finally {
        setIsLoadingTasks(false);
      }
    };
    
    loadTasks();
  }, []); // 只在组件挂载时加载一次

  // 自动保存活动任务ID到 localStorage（当 activeTaskId 改变时）
  useEffect(() => {
    saveActiveTaskId(activeTaskId);
  }, [activeTaskId]);

  // 自动滚动日志到底部
  useEffect(() => {
    if (logContainerRef.current && activeTask) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [activeTask?.logs]);

  // 创建新任务
  const createNewTask = async () => {
    try {
      const taskCount = tasks.length;
      const newTaskData = await workflowTasksApi.create({
        name: generateTaskName(taskCount + 1),
        document: '',
        user_info: '',
        session_id: '',
        has_outline: false,
        has_existing_tex: false,
      });
      
      // 将 API 响应转换为 WorkflowTask 格式
      const newTask: WorkflowTask = {
        id: newTaskData.id,
        name: newTaskData.name || `任务 ${newTaskData.task_id}`,
        status: newTaskData.status as TaskStatus,
        createdAt: new Date(newTaskData.created_at),
        updatedAt: new Date(newTaskData.updated_at),
        document: newTaskData.document || '',
        userInfo: newTaskData.user_info || '',
        sessionId: newTaskData.session_id || '',
        pdfFile: null,
        imageFiles: [],
        hasOutline: newTaskData.has_outline,
        hasExistingTex: newTaskData.has_existing_tex,
        temperature: newTaskData.temperature ? parseFloat(newTaskData.temperature) : undefined,
        maxTokens: newTaskData.max_tokens ? parseInt(newTaskData.max_tokens) : undefined,
        response: newTaskData.response,
        error: newTaskData.error,
        currentStep: newTaskData.current_step || '',
        logs: newTaskData.logs || [],
      };
      
      updateTasks(prev => [...prev, newTask]);
      setActiveTaskId(newTask.id);
    } catch (error: any) {
      console.error('创建任务失败:', error);
      
      // 如果是并发数限制错误，显示提示
      if (error?.response?.status === 429 || error?.response?.status === 400) {
        const errorMessage = error?.response?.data?.detail || error?.message || '已达到最大并发数限制，请等待任务完成后再启动新任务';
        alert(errorMessage);
        return;
      }
      
      // 如果 API 失败，创建一个本地任务（仅用于 UI，不会保存到后端）
      const localTask: WorkflowTask = {
        id: generateTaskId(),
        name: generateTaskName(tasks.length + 1),
        status: 'pending',
        createdAt: new Date(),
        updatedAt: new Date(),
        document: '',
        userInfo: '',
        sessionId: '',
        pdfFile: null,
        imageFiles: [],
        hasOutline: false,
        hasExistingTex: false,
        temperature: undefined,
        maxTokens: undefined,
        response: null,
        error: null,
        currentStep: '',
        logs: [],
      };
      updateTasks(prev => [...prev, localTask]);
      setActiveTaskId(localTask.id);
    }
  };

  // 显示删除确认弹窗
  const showDeleteConfirm = (taskId: string) => {
    setDeleteConfirmTaskId(taskId);
  };

  // 取消删除确认
  const cancelDelete = () => {
    setDeleteConfirmTaskId(null);
  };

  // 处理任务切换（直接切换，不影响正在运行的任务）
  const handleTaskSwitch = (taskId: string) => {
    // 如果切换到同一个任务，直接返回
    if (taskId === activeTaskId) {
      return;
    }
    
    // 直接切换任务，不检查运行中的任务（支持并发执行）
    setActiveTaskId(taskId);
  };

  // 处理页面切换（直接切换，不影响正在运行的任务）
  const handlePageSwitch = (path: string, e: React.MouseEvent) => {
    // 直接允许页面切换，不检查运行中的任务（支持并发执行）
    // 让 Link 正常导航
  };

  // 确认删除任务
  const confirmDeleteTask = async () => {
    const taskId = deleteConfirmTaskId;
    if (!taskId) return;
    
    const task = tasks.find(t => t.id === taskId);
    if (!task) {
      // 任务不存在，关闭弹窗
      setDeleteConfirmTaskId(null);
      return;
    }
    
    // 如果已经在删除中，忽略重复请求
    if (task.status === 'deleting') {
      setDeleteConfirmTaskId(null);
      return;
    }
    
    // 检查是否正在处理文件（PDF或图片）
    if (isProcessingFile(task)) {
      // 正在处理图片或PDF，禁止删除，不关闭弹窗，让用户看到警告
        updateTask(taskId, {
          currentStep: '正在处理文件（PDF/图片），无法删除。请等待处理完成后再试。',
        });
      return;
    }
    
    // 如果任务正在运行中，先取消任务
    if (task.status === 'running') {
      const abortController = abortControllersRef.current.get(taskId);
      if (abortController) {
        abortController.abort();
        abortControllersRef.current.delete(taskId);
      }
      // 更新任务状态为失败
      updateTask(taskId, {
        status: 'failed',
        error: '任务已取消（因删除任务）',
        currentStep: '任务已取消',
      }, true);
    }
    
    // 通过所有检查，关闭确认弹窗
    setDeleteConfirmTaskId(null);
    
    // 保存原始状态，用于错误恢复
    const originalStatus = task.status;
    
    // 设置删除状态（立即更新）
    updateTask(taskId, {
      status: 'deleting',
      currentStep: '正在删除...',
    }, true);
    
    try {
      // 如果任务正在运行，先停止它并等待任务完成
      if (originalStatus === 'running') {
        updateTask(taskId, { currentStep: '正在停止任务...' });
        const abortController = abortControllersRef.current.get(taskId);
        if (abortController) {
          abortController.abort();
          abortControllersRef.current.delete(taskId);
        }
        
        // 等待任务完成或超时（最多等待10秒）
        const waitTime = 10000; // 10秒
        const checkInterval = 500; // 每500ms检查一次
        const maxChecks = waitTime / checkInterval; // 最多检查20次
        
        updateTask(taskId, { currentStep: '等待后端任务完成...' });
        
        let shouldContinue = true;
        for (let i = 0; i < maxChecks && shouldContinue; i++) {
          const remaining = Math.ceil((waitTime - i * checkInterval) / 1000);
          updateTask(taskId, { 
            currentStep: `等待后端任务完成... (${remaining}秒后继续删除)` 
          });
          await new Promise(resolve => setTimeout(resolve, checkInterval));
          
          // 检查任务状态是否已改变（可能已经完成或失败）
          // 使用函数式更新来获取最新状态并检查
          updateTasks(prev => {
            const currentTask = prev.find(t => t.id === taskId);
            if (!currentTask || currentTask.status !== 'running') {
              // 任务已经停止，标记为不需要继续等待
              shouldContinue = false;
            }
            return prev;
          });
        }
        
        updateTask(taskId, { currentStep: '任务已停止，准备删除文件...' });
        // 额外等待1秒，确保后端任务完全停止
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      
      // 如果有sessionId，删除对应的session文件夹
      if (task.sessionId && task.sessionId.trim()) {
        try {
          updateTask(taskId, { currentStep: `正在删除 session 文件夹 (${task.sessionId})...` });
          console.log(`[删除] 开始删除 session: ${task.sessionId}`);
          
          // 尝试删除，最多重试3次
          let deleteSuccess = false;
          let lastError: Error | null = null;
          
          for (let attempt = 1; attempt <= 3; attempt++) {
            try {
              const result = await workflowApi.deleteSession(task.sessionId!);
              console.log(`[删除] Session 删除结果:`, result);
              deleteSuccess = true;
              updateTask(taskId, { currentStep: 'Session 文件夹删除成功' });
              break;
            } catch (err) {
              lastError = err instanceof Error ? err : new Error(String(err));
              console.warn(`[删除] 删除 session ${task.sessionId} 尝试 ${attempt}/3 失败:`, err);
              
              if (attempt < 3) {
                // 等待后重试（指数退避）
                const retryDelay = attempt * 1000; // 1秒、2秒
                updateTask(taskId, { 
                  currentStep: `删除失败，${retryDelay/1000}秒后重试 (${attempt}/3)...` 
                });
                await new Promise(resolve => setTimeout(resolve, retryDelay));
              }
            }
          }
          
          if (!deleteSuccess) {
            console.error(`[删除] 删除 session ${task.sessionId} 最终失败:`, lastError);
            // 即使删除失败，也继续删除任务（可能是文件夹不存在或正在被使用）
            updateTask(taskId, { 
              currentStep: `Session 文件夹删除失败，但继续删除任务。如果文件仍存在，请稍后手动删除。`,
              error: `删除 session 文件夹失败: ${lastError?.message || '未知错误'}`
            });
          }
        } catch (err) {
          console.error(`[删除] 删除 session ${task.sessionId} 时发生异常:`, err);
          updateTask(taskId, { 
            currentStep: `Session 文件夹删除失败，但继续删除任务`,
            error: `删除 session 文件夹时发生异常: ${err instanceof Error ? err.message : '未知错误'}`
          });
        }
      } else {
        console.log(`[删除] 任务没有 sessionId，跳过 session 文件夹删除`);
        updateTask(taskId, { currentStep: '任务没有 session 文件夹，直接删除任务' });
      }
      
      // 等待一小段时间，让用户看到删除过程
      await new Promise(resolve => setTimeout(resolve, 300));
      
      // 清理AbortController
      abortControllersRef.current.delete(taskId);
      
      // 从后端删除任务
      try {
        await workflowTasksApi.delete(taskId);
      } catch (err) {
        console.error(`删除任务 ${taskId} 失败:`, err);
        // 即使后端删除失败，也从本地列表中移除（避免 UI 卡住）
      }
      
      // 从任务列表中删除
      updateTasks(prev => {
        const newTasks = prev.filter(t => t.id !== taskId);
        // 如果删除的是当前任务，切换到其他任务或清空
        if (taskId === activeTaskId) {
          if (newTasks.length > 0) {
            setActiveTaskId(newTasks[0].id);
          } else {
            setActiveTaskId(null);
          }
        }
        return newTasks;
        // 注意：不需要手动保存，useEffect 会自动保存
      });
      
      console.log(`[删除] 任务 ${taskId} 删除完成`);
    } catch (err) {
      // 如果删除过程中出错，恢复状态
      console.error(`[删除] 删除任务 ${taskId} 时出错:`, err);
      updateTask(taskId, {
        status: originalStatus,
        error: `删除失败: ${err instanceof Error ? err.message : '未知错误'}`,
        currentStep: '',
      }, true);
    }
  };

  // 更新任务的防抖定时器
  const updateTimersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());

  // 更新任务（带防抖，避免频繁调用 API）
  const updateTask = useCallback(async (taskId: string, updates: Partial<WorkflowTask>, immediate: boolean = false) => {
    // 先立即更新本地状态（乐观更新）
    updateTasks(prev => prev.map(task => 
      task.id === taskId 
        ? { ...task, ...updates, updatedAt: new Date() }
        : task
    ));

    // 清除之前的定时器
    const existingTimer = updateTimersRef.current.get(taskId);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    // 准备 API 更新数据
    const apiUpdate: any = {};
    if (updates.name !== undefined) apiUpdate.name = updates.name;
    if (updates.document !== undefined) apiUpdate.document = updates.document;
    if (updates.userInfo !== undefined) apiUpdate.user_info = updates.userInfo;
    if (updates.sessionId !== undefined) apiUpdate.session_id = updates.sessionId;
    if (updates.status !== undefined) apiUpdate.status = updates.status;
    if (updates.hasOutline !== undefined) apiUpdate.has_outline = updates.hasOutline;
    if (updates.hasExistingTex !== undefined) apiUpdate.has_existing_tex = updates.hasExistingTex;
    if (updates.temperature !== undefined) apiUpdate.temperature = updates.temperature;
    if (updates.maxTokens !== undefined) apiUpdate.max_tokens = updates.maxTokens;
    if (updates.error !== undefined) apiUpdate.error = updates.error;
    if (updates.currentStep !== undefined) apiUpdate.current_step = updates.currentStep;
    if (updates.logs !== undefined) apiUpdate.logs = updates.logs;
    if (updates.response !== undefined) apiUpdate.response = updates.response;
    
    // 处理文件信息
    if (updates.pdfFile !== undefined) {
      apiUpdate.pdf_file_info = updates.pdfFile ? {
        name: updates.pdfFile.name,
        size: updates.pdfFile.size,
        type: updates.pdfFile.type,
      } : null;
    }
    if (updates.imageFiles !== undefined) {
      apiUpdate.image_files_info = updates.imageFiles.map(file => ({
        name: file.name,
        size: file.size,
        type: file.type,
      }));
    }

    // 如果没有需要更新的字段，直接返回
    if (Object.keys(apiUpdate).length === 0) {
      return;
    }

    // 执行更新函数
    const performUpdate = async () => {
      try {
        await workflowTasksApi.update(taskId, apiUpdate);
        updateTimersRef.current.delete(taskId);
      } catch (error) {
        console.error(`更新任务 ${taskId} 失败:`, error);
        // 更新失败时，可以选择回滚或保持乐观更新
        // 这里保持乐观更新，因为用户已经看到更新了
      }
    };

    if (immediate) {
      // 立即更新（用于重要操作，如状态变更）
      await performUpdate();
    } else {
      // 防抖更新（延迟 500ms）
      const timer = setTimeout(performUpdate, 500);
      updateTimersRef.current.set(taskId, timer);
    }
  }, []);

  // 更新当前任务的字段
  const updateActiveTaskField = <K extends keyof WorkflowTask>(field: K, value: WorkflowTask[K]) => {
    if (activeTaskId) {
      updateTask(activeTaskId, { [field]: value });
    }
  };

  // 处理表单提交
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!activeTask) {
      setActiveTaskId(null);
      return;
    }

    const task = activeTask;
    
    if (!task.document.trim() && !task.pdfFile && task.imageFiles.length === 0) {
      updateTask(task.id, { error: '请至少提供文档内容、上传PDF文件或上传图片文件' });
      return;
    }

    // 生成sessionId（基于task name）
    let sessionId = task.sessionId;
    if (!sessionId || !sessionId.trim()) {
      // 将task name转换为安全的session名称
      const safeName = task.name
        .trim()
        .replace(/[^a-zA-Z0-9\u4e00-\u9fa5\s_-]/g, '') // 移除特殊字符
        .replace(/\s+/g, '_') // 空格替换为下划线
        .substring(0, 50); // 限制长度
      
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
      const uniqueId = Math.random().toString(36).substring(2, 10);
      sessionId = `session_${safeName}_${timestamp}_${uniqueId}`;
      
      // 更新task的sessionId
      updateTask(task.id, { sessionId });
    }

    // 清除之前的错误和响应
    updateTask(task.id, {
      error: null,
      response: null,
      logs: [],
    }, true);

    // 创建AbortController用于取消请求
    const abortController = new AbortController();
    abortControllersRef.current.set(task.id, abortController);

    try {
      await workflowApi.executeStream(
        {
          document: task.document || undefined,
          pdfFile: task.pdfFile || undefined,
          imageFiles: task.imageFiles.length > 0 ? task.imageFiles : undefined,
          session_id: sessionId,
          user_info: task.userInfo || undefined,
          has_outline: task.hasOutline,
          has_existing_tex: task.hasExistingTex,
          temperature: task.temperature,
          max_tokens: task.maxTokens,
          task_id: task.id, // 传递任务ID，后端会更新任务状态
        },
        (chunk: WorkflowProgressChunk) => {
          // 检查是否已取消
          if (abortController.signal.aborted) {
            return;
          }
          
          // 如果收到第一个chunk且任务状态还是pending，更新为running
          // 这确保前端状态与后端同步（后端已经在开始执行前更新了状态）
          // 注意：这里使用updateTasks的回调形式来获取最新状态
          updateTasks(prev => {
            const currentTask = prev.find(t => t.id === task.id);
            if (currentTask && currentTask.status === 'pending') {
              // 更新为running状态
              return prev.map(t => 
                t.id === task.id 
                  ? { ...t, status: 'running' as const, currentStep: '正在初始化工作流...' }
                  : t
              );
            }
            return prev;
          });
          
          if (chunk.type === 'progress') {
            // 更新进度
            if (chunk.message) {
              updateTask(task.id, { currentStep: chunk.message });
              
              // 尝试从消息中提取session_id（如果消息包含"Session ID: xxx"）
              const sessionIdMatch = chunk.message.match(/Session ID:\s*([^\s,]+)/);
              if (sessionIdMatch && sessionIdMatch[1]) {
                updateTask(task.id, { sessionId: sessionIdMatch[1] });
              }
            }
          } else if (chunk.type === 'error') {
            // 处理错误（包括并发数限制错误）
            updateTask(task.id, {
              status: 'failed',
              error: chunk.message || '执行失败',
              currentStep: chunk.message || '执行失败',
            }, true);
            abortControllersRef.current.delete(task.id);
          } else if (chunk.type === 'log') {
            // 添加日志
            updateTasks(prev => prev.map(t => {
              if (t.id === task.id) {
                const newLogs = [...t.logs];
                if (chunk.log) {
                  newLogs.push(chunk.log);
                } else if (chunk.message) {
                  newLogs.push(chunk.message);
                }
                return { ...t, logs: newLogs, updatedAt: new Date() };
              }
              return t;
            }));
          } else if (chunk.type === 'result') {
            // 设置最终结果
            if (chunk.result) {
              // 从result中获取session_id
              const sessionId = chunk.result.session_id || task.sessionId;
              updateTask(task.id, {
                status: 'completed',
                response: chunk.result,
                sessionId: sessionId,
                currentStep: '工作流执行完成！',
              }, true);
              // 清理AbortController
              abortControllersRef.current.delete(task.id);
            }
          }
        },
        (err) => {
          // 如果是取消操作，不更新为失败状态
          if (err.name === 'AbortError' || abortController.signal.aborted) {
            updateTask(task.id, {
              status: 'failed',
              error: '任务已取消',
              currentStep: '任务已取消',
            }, true);
          } else {
            updateTask(task.id, {
              status: 'failed',
              error: err.message,
              currentStep: '',
            }, true);
          }
          // 清理AbortController
          abortControllersRef.current.delete(task.id);
        },
        abortController
      );
    } catch (err) {
      // 如果是取消操作，不更新为失败状态
      if (err instanceof Error && (err.name === 'AbortError' || abortController.signal.aborted)) {
        updateTask(task.id, {
          status: 'failed',
          error: '任务已取消',
          currentStep: '任务已取消',
        }, true);
      } else {
        updateTask(task.id, {
          status: 'failed',
          error: err instanceof Error ? err.message : '发生未知错误',
          currentStep: '',
        }, true);
      }
      // 清理AbortController
      abortControllersRef.current.delete(task.id);
    }
  };

  // 文件处理函数
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.type !== 'application/pdf') {
        updateActiveTaskField('error', '请上传PDF格式的文件');
        e.target.value = '';
        return;
      }
      updateActiveTaskField('pdfFile', file);
      updateActiveTaskField('error', null);
    }
  };

  const handleRemoveFile = () => {
    updateActiveTaskField('pdfFile', null);
    // 移除PDF文件时，同时重置hasOutline为false
    updateActiveTaskField('hasOutline', false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && activeTaskId) {
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp'];
      const validFiles: File[] = [];
      
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (allowedTypes.includes(file.type)) {
          validFiles.push(file);
        } else {
          updateActiveTaskField('error', `文件 ${file.name} 不是支持的图片格式（支持：JPG, PNG, GIF, BMP, WEBP）`);
        }
      }
      
      if (validFiles.length > 0) {
        updateTasks(prev => prev.map(task => {
          if (task.id === activeTaskId) {
            return { ...task, imageFiles: [...task.imageFiles, ...validFiles], error: null, updatedAt: new Date() };
          }
          return task;
        }));
      }
      
      if (imageInputRef.current) {
        imageInputRef.current.value = '';
      }
    }
  };

  const handleRemoveImage = (index: number) => {
    if (activeTask) {
      updateActiveTaskField('imageFiles', activeTask.imageFiles.filter((_, i) => i !== index));
    }
  };

  const handleRemoveAllImages = () => {
    updateActiveTaskField('imageFiles', []);
    if (imageInputRef.current) {
      imageInputRef.current.value = '';
    }
  };

  // 获取状态显示文本和颜色
  const getStatusDisplay = (status: TaskStatus) => {
    switch (status) {
      case 'pending':
        return { text: '待执行', color: 'var(--color-text-tertiary)' };
      case 'running':
        return { text: '运行中', color: 'var(--color-primary)' };
      case 'completed':
        return { text: '已完成', color: 'var(--color-success)' };
      case 'failed':
        return { text: '失败', color: 'var(--color-error)' };
      case 'deleting':
        return { text: '删除中', color: 'var(--color-warning)' };
      default:
        return { text: '未知', color: 'var(--color-text-tertiary)' };
    }
  };

  // 初始化：如果加载完成后没有任务，创建一个
  useEffect(() => {
    if (!isLoadingTasks && tasks.length === 0) {
      createNewTask();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoadingTasks]); // 当加载完成时检查

  // 切换任务时，重置文件输入引用
  useEffect(() => {
    if (activeTask) {
      // 当切换任务时，确保文件输入显示正确的状态
      if (fileInputRef.current && !activeTask.pdfFile) {
        fileInputRef.current.value = '';
      }
      if (imageInputRef.current && activeTask.imageFiles.length === 0) {
        imageInputRef.current.value = '';
      }
    }
  }, [activeTaskId]);

  // 组件卸载时清理所有AbortController
  useEffect(() => {
    return () => {
      // 取消所有正在运行的请求
      abortControllersRef.current.forEach((controller) => {
        controller.abort();
      });
      abortControllersRef.current.clear();
    };
  }, []);

  return (
    <div className="page-container">
      <h1 className="page-title">论文生成工作流</h1>
      <p className="page-description">
        一键执行完整的论文生成流程，包括：论文概览生成 → LaTeX 论文生成 → 需求清单生成。
        支持同时创建和管理多个任务。
      </p>

      <div className="workflow-container" style={{ display: 'flex', gap: '1.5rem', marginTop: '2rem' }}>
        {/* 左侧：任务列表 */}
        <div className="workflow-task-list" style={{ 
          width: '300px', 
          flexShrink: 0,
          backgroundColor: 'var(--color-bg-secondary)',
          borderRadius: 'var(--radius-lg)',
          padding: '1.25rem',
          maxHeight: 'calc(100vh - 200px)',
          overflowY: 'auto',
          border: '1px solid var(--color-border)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', paddingBottom: '1rem', borderBottom: '1px solid var(--color-border)' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', color: 'var(--color-text-primary)', fontWeight: 600 }}>任务列表</h3>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <button
                type="button"
                onClick={createNewTask}
                className="btn btn-primary"
                style={{
                  padding: '0.5rem 0.875rem',
                  fontSize: '0.8125rem'
                }}
              >
                新建任务
              </button>
            </div>
          </div>
          
          {/* 并发数显示 */}
          <div style={{ 
            marginBottom: '1rem', 
            padding: '0.75rem', 
            backgroundColor: 'var(--color-bg-primary)', 
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
            fontSize: '0.8125rem'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--color-text-secondary)' }}>并发数：</span>
              <span style={{ 
                color: runningTasksCount >= maxConcurrentWorkflows ? 'var(--color-error)' : 'var(--color-text-primary)',
                fontWeight: 600
              }}>
                {runningTasksCount} / {maxConcurrentWorkflows}
              </span>
            </div>
            {runningTasksCount >= maxConcurrentWorkflows && (
              <div style={{ 
                marginTop: '0.5rem', 
                padding: '0.5rem', 
                backgroundColor: 'var(--color-error-light)', 
                borderRadius: 'var(--radius-sm)',
                color: 'var(--color-error)',
                fontSize: '0.75rem'
              }}>
                已达到最大并发数限制，请等待任务完成后再启动新任务
              </div>
            )}
          </div>

          {tasks.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--color-text-tertiary)', padding: '2rem 0', fontSize: '0.875rem' }}>
              暂无任务，点击"新建任务"开始
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {tasks.map(task => {
                const statusDisplay = getStatusDisplay(task.status);
                const isActive = task.id === activeTaskId;
                
                return (
                  <div
                    key={task.id}
                    onClick={() => handleTaskSwitch(task.id)}
                    style={{
                      padding: '1rem',
                      backgroundColor: isActive ? 'var(--color-primary-light)' : 'var(--color-bg-primary)',
                      border: `1px solid ${isActive ? 'var(--color-primary)' : 'var(--color-border)'}`,
                      borderRadius: 'var(--radius-md)',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      boxShadow: isActive ? 'var(--shadow-sm)' : 'none',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.backgroundColor = 'var(--color-bg-tertiary)';
                        e.currentTarget.style.borderColor = 'var(--color-text-tertiary)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.backgroundColor = 'var(--color-bg-primary)';
                        e.currentTarget.style.borderColor = 'var(--color-border)';
                      }
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                      <input
                        type="text"
                        value={task.name}
                        onChange={(e) => {
                          e.stopPropagation();
                          updateTask(task.id, { name: e.target.value });
                        }}
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          flex: 1,
                          border: 'none',
                          backgroundColor: 'transparent',
                          fontSize: '0.875rem',
                          fontWeight: isActive ? 600 : 500,
                          color: 'var(--color-text-primary)',
                          padding: '0.25rem',
                          marginRight: '0.5rem',
                        }}
                      />
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          showDeleteConfirm(task.id);
                        }}
                        disabled={task.status === 'deleting' || isProcessingFile(task)}
                        style={{
                          padding: '0.375rem 0.75rem',
                          backgroundColor: (task.status === 'deleting' || isProcessingFile(task)) ? 'var(--color-text-tertiary)' : 'var(--color-error)',
                          color: 'white',
                          border: 'none',
                          borderRadius: 'var(--radius-sm)',
                          cursor: (task.status === 'deleting' || isProcessingFile(task)) ? 'not-allowed' : 'pointer',
                          fontSize: '0.75rem',
                          fontWeight: 500,
                          opacity: (task.status === 'deleting' || isProcessingFile(task)) ? 0.6 : 1,
                          transition: 'all 0.2s ease',
                        }}
                        onMouseEnter={(e) => {
                          if (!(task.status === 'deleting' || isProcessingFile(task))) {
                            e.currentTarget.style.opacity = '0.9';
                            e.currentTarget.style.transform = 'scale(1.02)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!(task.status === 'deleting' || isProcessingFile(task))) {
                            e.currentTarget.style.opacity = '1';
                            e.currentTarget.style.transform = 'scale(1)';
                          }
                        }}
                      >
                        {task.status === 'deleting' ? '删除中...' : '删除'}
                      </button>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8125rem', marginTop: '0.5rem' }}>
                      <span style={{ 
                        color: statusDisplay.color, 
                        fontWeight: 500,
                        padding: '0.125rem 0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: isActive ? 'rgba(37, 99, 235, 0.1)' : 'transparent',
                      }}>
                        {statusDisplay.text}
                      </span>
                      <span style={{ color: 'var(--color-text-tertiary)' }}>
                        {new Date(task.createdAt).toLocaleTimeString()}
                      </span>
                    </div>
                    {(task.status === 'running' || task.status === 'deleting') && task.currentStep && (
                      <div style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--color-text-secondary)', fontStyle: 'italic', paddingTop: '0.5rem', borderTop: '1px solid var(--color-border-light)' }}>
                        {task.currentStep}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 右侧：任务详情 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {activeTask ? (
            <>
              <form onSubmit={handleSubmit}>
                <div className="form-group">
                  <label className="form-label">文档内容（可选，可与PDF同时提供）</label>
                  <textarea
                    className="form-textarea"
                    value={activeTask.document}
                    onChange={(e) => updateActiveTaskField('document', e.target.value)}
                    placeholder="输入您的文档内容，或上传PDF文件，或两者都提供..."
                    rows={10}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">PDF文件（可选，可与文字描述同时提供）</label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf"
                      onChange={handleFileChange}
                      style={{ flex: 1 }}
                    />
                    {activeTask.pdfFile && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1 }}>
                        <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                          {activeTask.pdfFile.name} ({(activeTask.pdfFile.size / 1024 / 1024).toFixed(2)} MB)
                        </span>
                        <button
                          type="button"
                          onClick={handleRemoveFile}
                          style={{
                            padding: '0.375rem 0.75rem',
                            fontSize: '0.8125rem',
                            backgroundColor: 'var(--color-error)',
                            color: 'white',
                            border: 'none',
                            borderRadius: 'var(--radius-sm)',
                            cursor: 'pointer',
                            fontWeight: 500,
                            transition: 'all 0.2s ease',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.opacity = '0.9';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.opacity = '1';
                          }}
                        >
                          移除
                        </button>
                      </div>
                    )}
                  </div>
                  {activeTask.pdfFile && (
                    <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <input
                        type="checkbox"
                        id="pdfIsOutline"
                        checked={activeTask.hasOutline}
                        onChange={(e) => updateActiveTaskField('hasOutline', e.target.checked)}
                        style={{
                          width: '1rem',
                          height: '1rem',
                          cursor: 'pointer',
                        }}
                      />
                      <label
                        htmlFor="pdfIsOutline"
                        style={{
                          fontSize: '0.875rem',
                          color: 'var(--color-text-primary)',
                          cursor: 'pointer',
                          userSelect: 'none',
                        }}
                      >
                        PDF为大纲/初稿（勾选后将跳过LaTeX生成）
                      </label>
                    </div>
                  )}
                  <p style={{ fontSize: '0.8125rem', color: 'var(--color-text-tertiary)', marginTop: '0.5rem', lineHeight: 1.6 }}>
                    提示：可以只提供文字描述，或只上传PDF文件，或两者都提供（内容会合并）
                  </p>
                </div>

                <div className="form-group">
                  <label className="form-label">图片文件（可选，支持多张，可与文字/PDF同时提供）</label>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    <input
                      ref={imageInputRef}
                      type="file"
                      accept="image/jpeg,image/jpg,image/png,image/gif,image/bmp,image/webp"
                      multiple
                      onChange={handleImageChange}
                      style={{ flex: 1, minWidth: '200px' }}
                    />
                    {activeTask.imageFiles.length > 0 && (
                      <button
                        type="button"
                        onClick={handleRemoveAllImages}
                        style={{
                          padding: '0.375rem 0.75rem',
                          fontSize: '0.8125rem',
                          backgroundColor: 'var(--color-error)',
                          color: 'white',
                          border: 'none',
                          borderRadius: 'var(--radius-sm)',
                          cursor: 'pointer',
                          fontWeight: 500,
                          transition: 'all 0.2s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.opacity = '0.9';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.opacity = '1';
                        }}
                      >
                        清除所有图片
                      </button>
                    )}
                  </div>
                  {activeTask.imageFiles.length > 0 && (
                    <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {activeTask.imageFiles.map((file, index) => (
                        <div
                          key={index}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.5rem',
                          padding: '0.75rem',
                          backgroundColor: 'var(--color-bg-secondary)',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--color-border-light)',
                        }}
                      >
                          <span style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)', flex: 1 }}>
                            {file.name} ({(file.size / 1024).toFixed(2)} KB)
                          </span>
                          <button
                            type="button"
                            onClick={() => handleRemoveImage(index)}
                            style={{
                              padding: '0.375rem 0.75rem',
                              fontSize: '0.8125rem',
                              backgroundColor: 'var(--color-error)',
                              color: 'white',
                              border: 'none',
                              borderRadius: 'var(--radius-sm)',
                              cursor: 'pointer',
                              fontWeight: 500,
                              transition: 'all 0.2s ease',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.opacity = '0.9';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.opacity = '1';
                            }}
                          >
                            移除
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <p style={{ fontSize: '0.8125rem', color: 'var(--color-text-tertiary)', marginTop: '0.5rem', lineHeight: 1.6 }}>
                    提示：支持 JPG、PNG、GIF、BMP、WEBP 格式，可同时上传多张图片，图片中的文字会被提取并合并到文档中
                  </p>
                </div>

                <div className="form-group">
                  <label className="form-label">额外信息（可选）</label>
                  <textarea
                    className="form-textarea"
                    value={activeTask.userInfo}
                    onChange={(e) => updateActiveTaskField('userInfo', e.target.value)}
                    placeholder="输入额外的用户信息（用于 LaTeX 生成）..."
                    rows={5}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Session ID（可选）</label>
                  <input
                    type="text"
                    className="form-input"
                    value={activeTask.sessionId}
                    onChange={(e) => updateActiveTaskField('sessionId', e.target.value)}
                    placeholder="留空则自动生成"
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">温度 (0-2)</label>
                    <input
                      type="number"
                      className="form-input"
                      value={activeTask.temperature || ''}
                      onChange={(e) => updateActiveTaskField('temperature', e.target.value ? parseFloat(e.target.value) : undefined)}
                      min="0"
                      max="2"
                      step="0.1"
                      placeholder="使用默认值"
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">最大 Token 数</label>
                    <input
                      type="number"
                      className="form-input"
                      value={activeTask.maxTokens || ''}
                      onChange={(e) => updateActiveTaskField('maxTokens', e.target.value ? parseInt(e.target.value) : undefined)}
                      min="1"
                      placeholder="使用默认值"
                    />
                  </div>
                </div>

                <div className="form-group">
                  <div className="checkbox-group">
                    <input
                      type="checkbox"
                      id="hasOutline"
                      checked={activeTask.hasOutline}
                      onChange={(e) => updateActiveTaskField('hasOutline', e.target.checked)}
                    />
                    <label htmlFor="hasOutline">用户已提供论文大纲（将跳过 LaTeX 生成）</label>
                  </div>
                </div>

                <div className="form-group">
                  <div className="checkbox-group">
                    <input
                      type="checkbox"
                      id="hasExistingTex"
                      checked={activeTask.hasExistingTex}
                      onChange={(e) => updateActiveTaskField('hasExistingTex', e.target.checked)}
                    />
                    <label htmlFor="hasExistingTex">已存在 .tex 文件（将跳过 LaTeX 生成）</label>
                  </div>
                </div>

                <div className="button-group">
                  <button 
                    type="submit" 
                    className="btn btn-primary" 
                    disabled={!activeTask || activeTask.status === 'running'}
                  >
                    {activeTask?.status === 'running' && <span className="loading"></span>}
                    {activeTask?.status === 'running' ? '执行中...' : '执行工作流'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      if (activeTaskId) {
                        updateTask(activeTaskId, {
                          document: '',
                          userInfo: '',
                          sessionId: '',
                          pdfFile: null,
                          imageFiles: [],
                          hasOutline: false,
                          hasExistingTex: false,
                          response: null,
                          error: null,
                          currentStep: '',
                          logs: [],
                        });
                        if (fileInputRef.current) {
                          fileInputRef.current.value = '';
                        }
                        if (imageInputRef.current) {
                          imageInputRef.current.value = '';
                        }
                      }
                    }}
                  >
                    清空表单
                  </button>
                </div>
              </form>

              {activeTask.status === 'running' && activeTask.currentStep && (
                <div className="info" style={{ marginTop: '1.5rem' }}>
                  <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>{activeTask.currentStep}</div>
                </div>
              )}

              {activeTask.status === 'running' && activeTask.logs.length > 0 && (
                <div style={{ marginTop: '1.5rem' }}>
                  <h4 style={{ marginBottom: '0.75rem', color: 'var(--color-text-primary)', fontSize: '1rem', fontWeight: 600 }}>实时日志</h4>
                  <div
                    ref={logContainerRef}
                    style={{
                      maxHeight: '400px',
                      overflowY: 'auto',
                      padding: '1rem 1.25rem',
                      backgroundColor: '#1e293b',
                      color: '#e2e8f0',
                      borderRadius: 'var(--radius-md)',
                      fontFamily: 'SF Mono, Monaco, Inconsolata, Roboto Mono, monospace',
                      fontSize: '0.8125rem',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      lineHeight: 1.6,
                      border: '1px solid #334155',
                    }}
                  >
                    {activeTask.logs.map((log, index) => (
                      <span key={index}>{log}</span>
                    ))}
                  </div>
                </div>
              )}

              {activeTask.error && <div className="error">{activeTask.error}</div>}

              {activeTask.response && (
                <div className="response-container">
                  <div className="response-header">
                    <h3 className="response-title">工作流执行结果</h3>
                    <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.5rem' }}>
                      <div>Session ID: {activeTask.response.session_id}</div>
                      <div>Session 文件夹: {activeTask.response.session_folder}</div>
                    </div>
                  </div>

                  <div style={{ marginTop: '1.5rem' }}>
                    <h4 style={{ marginBottom: '0.75rem', color: 'var(--color-text-primary)', fontSize: '1rem', fontWeight: 600 }}>论文概览</h4>
                    <div className="response-content" style={{ padding: '1.25rem', backgroundColor: 'var(--color-bg-primary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-light)' }}>
                      <div style={{ marginBottom: '0.75rem' }}>
                        <strong style={{ color: 'var(--color-text-primary)', fontSize: '0.875rem' }}>文件名:</strong>
                        <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>{activeTask.response.paper_overview.file_name}</span>
                      </div>
                      <div style={{ marginBottom: '0.75rem' }}>
                        <strong style={{ color: 'var(--color-text-primary)', fontSize: '0.875rem' }}>文件路径:</strong>
                        <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem', wordBreak: 'break-all' }}>{activeTask.response.paper_overview.file_path}</span>
                      </div>
                      {activeTask.response.paper_overview.usage && (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-tertiary)', paddingTop: '0.75rem', borderTop: '1px solid var(--color-border-light)' }}>
                          Token 使用: {activeTask.response.paper_overview.usage.total_tokens || 'N/A'} (
                          {activeTask.response.paper_overview.usage.prompt_tokens || 'N/A'} prompt +{' '}
                          {activeTask.response.paper_overview.usage.completion_tokens || 'N/A'} completion)
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ marginTop: '1.5rem' }}>
                    <h4 style={{ marginBottom: '0.75rem', color: 'var(--color-text-primary)', fontSize: '1rem', fontWeight: 600 }}>LaTeX 论文</h4>
                    <div className="response-content" style={{ padding: '1.25rem', backgroundColor: 'var(--color-bg-primary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-light)' }}>
                      {activeTask.response.latex_paper.is_skipped ? (
                        <div>
                          <div style={{ color: 'var(--color-warning)', marginBottom: '0.75rem', fontSize: '0.875rem', fontWeight: 500 }}>
                            已跳过生成
                          </div>
                          <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                            原因: {activeTask.response.latex_paper.skip_reason || '未知原因'}
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div style={{ marginBottom: '0.75rem' }}>
                            <strong style={{ color: 'var(--color-text-primary)', fontSize: '0.875rem' }}>文件名:</strong>
                            <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>{activeTask.response.latex_paper.file_name}</span>
                          </div>
                          <div style={{ marginBottom: '0.75rem' }}>
                            <strong style={{ color: 'var(--color-text-primary)', fontSize: '0.875rem' }}>文件路径:</strong>
                            <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem', wordBreak: 'break-all' }}>{activeTask.response.latex_paper.file_path}</span>
                          </div>
                          {activeTask.response.latex_paper.usage && (
                            <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-tertiary)', paddingTop: '0.75rem', borderTop: '1px solid var(--color-border-light)' }}>
                              Token 使用: {activeTask.response.latex_paper.usage.total_tokens || 'N/A'} (
                              {activeTask.response.latex_paper.usage.prompt_tokens || 'N/A'} prompt +{' '}
                              {activeTask.response.latex_paper.usage.completion_tokens || 'N/A'} completion)
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ marginTop: '1.5rem' }}>
                    <h4 style={{ marginBottom: '0.75rem', color: 'var(--color-text-primary)', fontSize: '1rem', fontWeight: 600 }}>需求清单</h4>
                    <div className="response-content" style={{ padding: '1.25rem', backgroundColor: 'var(--color-bg-primary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-light)' }}>
                      <div style={{ marginBottom: '0.75rem' }}>
                        <strong style={{ color: 'var(--color-text-primary)', fontSize: '0.875rem' }}>文件名:</strong>
                        <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>{activeTask.response.requirement_checklist.file_name}</span>
                      </div>
                      <div style={{ marginBottom: '0.75rem' }}>
                        <strong style={{ color: 'var(--color-text-primary)', fontSize: '0.875rem' }}>文件路径:</strong>
                        <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-secondary)', fontSize: '0.875rem', wordBreak: 'break-all' }}>{activeTask.response.requirement_checklist.file_path}</span>
                      </div>
                      {activeTask.response.requirement_checklist.usage && (
                        <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-tertiary)', paddingTop: '0.75rem', borderTop: '1px solid var(--color-border-light)' }}>
                          Token 使用: {activeTask.response.requirement_checklist.usage.total_tokens || 'N/A'} (
                          {activeTask.response.requirement_checklist.usage.prompt_tokens || 'N/A'} prompt +{' '}
                          {activeTask.response.requirement_checklist.usage.completion_tokens || 'N/A'} completion)
                        </div>
                      )}
                    </div>
                  </div>

                  <div style={{ marginTop: '1.5rem', padding: '1.25rem', backgroundColor: 'var(--color-primary-light)', borderRadius: 'var(--radius-md)', border: '1px solid #bfdbfe' }}>
                    <h4 style={{ marginBottom: '0.75rem', color: 'var(--color-primary)', fontSize: '1rem', fontWeight: 600 }}>总 Token 使用情况</h4>
                    <div style={{ fontSize: '0.875rem', color: 'var(--color-text-secondary)' }}>
                      总 Token 数: {activeTask.response.total_usage.total_tokens || 'N/A'} (
                      {activeTask.response.total_usage.prompt_tokens || 'N/A'} prompt +{' '}
                      {activeTask.response.total_usage.completion_tokens || 'N/A'} completion)
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-tertiary)', fontSize: '0.875rem' }}>
              <p>请选择一个任务或创建新任务</p>
            </div>
          )}
        </div>
      </div>

      {/* 删除确认弹窗 */}
      {deleteConfirmTaskId && (() => {
        const taskToDelete = tasks.find(t => t.id === deleteConfirmTaskId);
        
        // 检查是否正在处理文件（PDF或图片）
        const isProcessing = isProcessingFile(taskToDelete);
        // 检查是否正在运行中
        const isRunning = taskToDelete?.status === 'running';
        // 是否可以删除（处理文件时不能删除，运行中可以删除但会取消任务）
        const canDelete = !isProcessing;
        
        return (
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000,
            }}
            onClick={cancelDelete}
          >
            <div
              style={{
                backgroundColor: 'white',
                borderRadius: '8px',
                padding: '1.5rem',
                maxWidth: '400px',
                width: '90%',
                boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3 style={{ margin: '0 0 1rem 0', color: '#333' }}>确认删除</h3>
              {isProcessing ? (
                <div style={{ margin: '0 0 1.5rem 0' }}>
                  <div style={{ 
                    padding: '1rem 1.25rem', 
                    backgroundColor: '#fef3c7', 
                    border: '1px solid #fbbf24',
                    borderRadius: 'var(--radius-md)',
                    marginBottom: '1rem',
                  }}>
                    <div style={{ color: '#92400e', fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                      无法删除
                    </div>
                    <div style={{ color: '#92400e', fontSize: '0.8125rem', lineHeight: 1.6 }}>
                      任务正在处理文件（PDF/图片），请等待处理完成后再删除。
                    </div>
                    {taskToDelete?.currentStep && (
                      <div style={{ 
                        marginTop: '0.5rem', 
                        fontSize: '0.85rem', 
                        color: '#856404',
                        fontStyle: 'italic'
                      }}>
                        当前步骤: {taskToDelete.currentStep}
                      </div>
                    )}
                  </div>
                </div>
              ) : isRunning ? (
                <div style={{ margin: '0 0 1.5rem 0' }}>
                  <div style={{ 
                    padding: '1rem 1.25rem', 
                    backgroundColor: '#fef3c7', 
                    border: '1px solid #fbbf24',
                    borderRadius: 'var(--radius-md)',
                    marginBottom: '1rem',
                  }}>
                    <div style={{ color: '#92400e', fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                      警告：任务正在运行中
                    </div>
                    <div style={{ color: '#92400e', fontSize: '0.8125rem', lineHeight: 1.6 }}>
                      删除任务会导致当前运行中的任务被取消，任务将失败。确定要继续吗？
                    </div>
                    <div style={{ 
                      marginTop: '0.75rem', 
                      padding: '0.75rem', 
                      backgroundColor: '#fee2e2', 
                      border: '1px solid #f87171',
                      borderRadius: 'var(--radius-sm)',
                    }}>
                      <div style={{ color: '#991b1b', fontWeight: 600, marginBottom: '0.25rem', fontSize: '0.8125rem' }}>
                        ⚠️ 同时将删除所有后台信息：
                      </div>
                      <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0, fontSize: '0.75rem', color: '#991b1b', lineHeight: 1.5 }}>
                        <li>任务的所有执行记录和状态</li>
                        <li>生成的文档内容（文本、LaTeX、Markdown等）</li>
                        {taskToDelete?.sessionId && (
                          <li>Session 文件夹及所有相关文件: <strong>{taskToDelete.sessionId}</strong></li>
                        )}
                        <li>任务的所有历史数据</li>
                      </ul>
                      <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#991b1b', fontWeight: 600 }}>
                        此操作不可恢复！
                      </div>
                    </div>
                    {taskToDelete?.currentStep && (
                      <div style={{ 
                        marginTop: '0.75rem', 
                        fontSize: '0.8125rem', 
                        color: '#856404',
                      }}>
                        <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>当前步骤：</div>
                        <div style={{ marginLeft: '0.5rem' }}>
                          {taskToDelete.currentStep}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ margin: '0 0 1.5rem 0' }}>
                  <p style={{ margin: '0 0 1rem 0', color: '#666' }}>
                    确定要删除任务 <strong>"{taskToDelete?.name || '未知任务'}"</strong> 吗？
                  </p>
                  <div style={{ 
                    padding: '1rem 1.25rem', 
                    backgroundColor: '#fee2e2', 
                    border: '1px solid #f87171',
                    borderRadius: 'var(--radius-md)',
                  }}>
                    <div style={{ color: '#991b1b', fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                      ⚠️ 重要提示
                    </div>
                    <div style={{ color: '#991b1b', fontSize: '0.8125rem', lineHeight: 1.6 }}>
                      删除任务将同时删除所有相关的后台信息，包括：
                      <ul style={{ margin: '0.5rem 0 0 1.25rem', padding: 0 }}>
                        <li>任务的所有执行记录和状态</li>
                        <li>生成的文档内容（文本、LaTeX、Markdown等）</li>
                        {taskToDelete?.sessionId && (
                          <li>Session 文件夹及所有相关文件: <strong>{taskToDelete.sessionId}</strong></li>
                        )}
                        <li>任务的所有历史数据</li>
                      </ul>
                      <div style={{ marginTop: '0.75rem', fontWeight: 600 }}>
                        此操作不可恢复，请谨慎操作！
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={cancelDelete}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: '#ccc',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                  }}
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={confirmDeleteTask}
                  disabled={!canDelete}
                  style={{
                    padding: '0.5rem 1rem',
                    backgroundColor: canDelete ? (isRunning ? '#f59e0b' : '#f44336') : '#ccc',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: canDelete ? 'pointer' : 'not-allowed',
                    fontSize: '0.9rem',
                    fontWeight: 'bold',
                    opacity: canDelete ? 1 : 0.6,
                  }}
                >
                  {isRunning ? '确定删除（将取消任务）' : '确认删除'}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

export default Workflow;
