import { createContext, useContext, useState, ReactNode } from 'react';
import type { WorkflowTask } from '../types';

interface TaskContextType {
  tasks: WorkflowTask[];
  setTasks: (tasks: WorkflowTask[]) => void;
  hasRunningTask: () => boolean;
  getRunningTasks: () => WorkflowTask[];
}

const TaskContext = createContext<TaskContextType | undefined>(undefined);

export function TaskProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);

  const hasRunningTask = (): boolean => {
    return tasks.some(task => task.status === 'running');
  };

  const getRunningTasks = (): WorkflowTask[] => {
    return tasks.filter(task => task.status === 'running');
  };

  return (
    <TaskContext.Provider value={{ tasks, setTasks, hasRunningTask, getRunningTasks }}>
      {children}
    </TaskContext.Provider>
  );
}

export function useTaskContext() {
  const context = useContext(TaskContext);
  if (context === undefined) {
    throw new Error('useTaskContext must be used within a TaskProvider');
  }
  return context;
}

