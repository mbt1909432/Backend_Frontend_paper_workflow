import { BrowserRouter as Router, Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import AgentChat from './components/AgentChat';
import PaperOverview from './components/PaperOverview';
import LaTeXPaper from './components/LaTeXPaper';
import RequirementChecklist from './components/RequirementChecklist';
import Workflow from './components/Workflow';
import PDFProcessor from './components/PDFProcessor';
import SessionManager from './components/SessionManager';
import TokenUsage from './components/TokenUsage';
import Login from './components/Login';
import { TaskProvider, useTaskContext } from './contexts/TaskContext';
import './App.css';

function App() {
  const isAuthenticated = () => {
    return !!localStorage.getItem('auth_token');
  };

  return (
    <TaskProvider>
      <Router>
        <div className="app">
          {isAuthenticated() && <NavBar />}
          <main className="main-content">
            <Routes>
              <Route
                path="/login"
                element={
                  isAuthenticated() ? <Navigate to="/" replace /> : <Login />
                }
              />
              <Route
                path="/"
                element={
                  isAuthenticated() ? <Home /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/agent"
                element={
                  isAuthenticated() ? <AgentChat /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/paper-overview"
                element={
                  isAuthenticated() ? <PaperOverview /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/latex-paper"
                element={
                  isAuthenticated() ? <LaTeXPaper /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/requirement-checklist"
                element={
                  isAuthenticated() ? <RequirementChecklist /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/workflow"
                element={
                  isAuthenticated() ? <Workflow /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/pdf-processor"
                element={
                  isAuthenticated() ? <PDFProcessor /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/sessions"
                element={
                  isAuthenticated() ? <SessionManager /> : <Navigate to="/login" replace />
                }
              />
              <Route
                path="/token-usage"
                element={
                  isAuthenticated() ? <TokenUsage /> : <Navigate to="/login" replace />
                }
              />
            </Routes>
          </main>
        </div>
      </Router>
    </TaskProvider>
  );
}

function NavBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { hasRunningTask, getRunningTasks } = useTaskContext();
  const [switchConfirmInfo, setSwitchConfirmInfo] = useState<{
    targetPath: string;
  } | null>(null);

  const navItems = [
    { path: '/', label: '首页' },
    { path: '/workflow', label: '论文生成工作流' },
    { path: '/agent', label: '通用对话 Agent' },
    { path: '/paper-overview', label: '论文概览生成' },
    { path: '/latex-paper', label: 'LaTeX 论文生成' },
    { path: '/requirement-checklist', label: '需求清单生成' },
    { path: '/pdf-processor', label: 'PDF 文字提取' },
    { path: '/sessions', label: 'Session 管理' },
    { path: '/token-usage', label: 'Token 使用统计' },
  ];

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    window.location.href = '/login';
  };

  const handleNavClick = (path: string, e: React.MouseEvent) => {
    // 如果点击的是当前页面，直接返回
    if (path === location.pathname) {
      return;
    }

    // 检查是否有正在运行的任务
    if (hasRunningTask()) {
      e.preventDefault();
      setSwitchConfirmInfo({ targetPath: path });
    }
    // 如果没有运行中的任务，让 Link 正常导航
  };

  const confirmSwitch = () => {
    if (!switchConfirmInfo) return;
    
    // 通知 Workflow 组件取消所有正在运行的任务
    // 通过自定义事件来通知
    window.dispatchEvent(new CustomEvent('cancelAllRunningTasks'));
    
    // 延迟一下再导航，确保取消操作完成
    setTimeout(() => {
      navigate(switchConfirmInfo.targetPath);
      setSwitchConfirmInfo(null);
    }, 100);
  };

  const cancelSwitch = () => {
    setSwitchConfirmInfo(null);
  };

  const authUser = JSON.parse(localStorage.getItem('auth_user') || '{}');
  const runningTasks = getRunningTasks();

  return (
    <>
      <nav className="navbar">
        <div className="navbar-container">
          <Link to="/" className="navbar-brand" onClick={(e) => handleNavClick('/', e)}>
            <span className="brand-text">ResearchFlow</span>
          </Link>
          <div className="navbar-links">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link ${location.pathname === item.path ? 'active' : ''}`}
                onClick={(e) => handleNavClick(item.path, e)}
              >
                {item.label}
              </Link>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginLeft: '1rem' }}>
              <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
                {authUser.username}
              </span>
              <button
                onClick={handleLogout}
                className="btn btn-secondary"
                style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
              >
                退出
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* 切换确认弹窗 */}
      {switchConfirmInfo && (
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
          onClick={cancelSwitch}
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
            <h3 style={{ margin: '0 0 1rem 0', color: '#333' }}>警告</h3>
            <div style={{ margin: '0 0 1.5rem 0' }}>
              <div style={{ 
                padding: '1rem 1.25rem', 
                backgroundColor: '#fef3c7', 
                border: '1px solid #fbbf24',
                borderRadius: 'var(--radius-md)',
                marginBottom: '1rem',
              }}>
                <div style={{ color: '#92400e', fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                  有任务正在运行中
                </div>
                <div style={{ color: '#92400e', fontSize: '0.8125rem', lineHeight: 1.6 }}>
                  切换页面会导致当前运行中的任务被取消，任务将失败。确定要继续吗？
                </div>
                {runningTasks.length > 0 && (
                  <div style={{ 
                    marginTop: '0.75rem', 
                    fontSize: '0.8125rem', 
                    color: '#856404',
                  }}>
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>正在运行的任务：</div>
                    {runningTasks.map(task => (
                      <div key={task.id} style={{ marginLeft: '0.5rem', marginTop: '0.25rem' }}>
                        • {task.name} {task.currentStep && `(${task.currentStep})`}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={cancelSwitch}
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
                onClick={confirmSwitch}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#f59e0b',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  fontWeight: 'bold',
                }}
              >
                确定切换
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Home() {
  return (
    <div className="home-container">
      <div className="home-card">
        <h1 className="home-title">ResearchFlow</h1>
        <p className="home-description">
          基于 AI Agent 的学术论文草稿生成系统，提供智能化的论文撰写工作流，帮助您高效完成论文撰写工作。
        </p>
        <div className="agent-cards">
          <AgentCard
            path="/workflow"
            title="论文生成工作流"
            description="一键执行完整的论文生成流程，包括论文概览、LaTeX 论文和需求清单"
          />
          {/* 以下功能已隐藏（注释掉） */}
          {/* <AgentCard
            path="/agent"
            title="通用对话 Agent"
            description="与 AI 进行对话，支持多轮对话和流式响应"
          /> */}
          {/* <AgentCard
            path="/paper-overview"
            title="论文概览生成"
            description="根据用户文档生成论文概览文件"
          /> */}
          {/* <AgentCard
            path="/latex-paper"
            title="LaTeX 论文生成"
            description="根据论文概览生成完整的 LaTeX 论文"
          /> */}
          {/* <AgentCard
            path="/requirement-checklist"
            title="需求清单生成"
            description="生成需求清单文件，检查论文是否符合要求"
          /> */}
          {/* <AgentCard
            path="/pdf-processor"
            title="PDF 文字提取"
            description="上传 PDF 文件，自动提取所有页面的文字内容"
          /> */}
        </div>
      </div>
    </div>
  );
}

function AgentCard({ path, title, description }: { path: string; title: string; description: string }) {
  const navigate = useNavigate();
  const { hasRunningTask, getRunningTasks } = useTaskContext();
  const [switchConfirmInfo, setSwitchConfirmInfo] = useState<{
    targetPath: string;
  } | null>(null);

  const handleClick = (e: React.MouseEvent) => {
    // 检查是否有正在运行的任务
    if (hasRunningTask()) {
      e.preventDefault();
      setSwitchConfirmInfo({ targetPath: path });
    }
    // 如果没有运行中的任务，让 Link 正常导航
  };

  const confirmSwitch = () => {
    if (!switchConfirmInfo) return;
    
    // 通知 Workflow 组件取消所有正在运行的任务
    window.dispatchEvent(new CustomEvent('cancelAllRunningTasks'));
    
    // 延迟一下再导航，确保取消操作完成
    setTimeout(() => {
      navigate(switchConfirmInfo.targetPath);
      setSwitchConfirmInfo(null);
    }, 100);
  };

  const cancelSwitch = () => {
    setSwitchConfirmInfo(null);
  };

  const runningTasks = getRunningTasks();

  return (
    <>
      <Link to={path} className="agent-card" onClick={handleClick}>
        <h3 className="agent-card-title">{title}</h3>
        <p className="agent-card-description">{description}</p>
      </Link>

      {/* 切换确认弹窗 */}
      {switchConfirmInfo && (
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
          onClick={cancelSwitch}
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
            <h3 style={{ margin: '0 0 1rem 0', color: '#333' }}>警告</h3>
            <div style={{ margin: '0 0 1.5rem 0' }}>
              <div style={{ 
                padding: '1rem 1.25rem', 
                backgroundColor: '#fef3c7', 
                border: '1px solid #fbbf24',
                borderRadius: 'var(--radius-md)',
                marginBottom: '1rem',
              }}>
                <div style={{ color: '#92400e', fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.875rem' }}>
                  有任务正在运行中
                </div>
                <div style={{ color: '#92400e', fontSize: '0.8125rem', lineHeight: 1.6 }}>
                  切换页面会导致当前运行中的任务被取消，任务将失败。确定要继续吗？
                </div>
                {runningTasks.length > 0 && (
                  <div style={{ 
                    marginTop: '0.75rem', 
                    fontSize: '0.8125rem', 
                    color: '#856404',
                  }}>
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>正在运行的任务：</div>
                    {runningTasks.map(task => (
                      <div key={task.id} style={{ marginLeft: '0.5rem', marginTop: '0.25rem' }}>
                        • {task.name} {task.currentStep && `(${task.currentStep})`}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={cancelSwitch}
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
                onClick={confirmSwitch}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#f59e0b',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  fontWeight: 'bold',
                }}
              >
                确定切换
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default App;

