import { useState, useEffect } from 'react';
import { workflowApi } from '../services/api';

interface Session {
  session_id: string;
  created_at: string;
  size: number;
  file_count: number;
}

interface SessionDetails {
  artifacts: Record<string, any>;
  uploaded_files: Array<{ name: string; size: number }>;
  generated_files: Record<string, { content: string | null; size: number; is_binary?: boolean }>;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function SessionManager() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [deleteConfirmSessionId, setDeleteConfirmSessionId] = useState<string | null>(null);
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [sessionDetails, setSessionDetails] = useState<Record<string, SessionDetails>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});

  // 加载sessions列表
  const loadSessions = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await workflowApi.listSessions();
      setSessions(response.sessions);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载sessions失败');
      console.error('Failed to load sessions:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  // 删除session
  const handleDeleteSession = async (sessionId: string) => {
    try {
      setDeletingSessionId(sessionId);
      await workflowApi.deleteSession(sessionId);
      // 重新加载列表
      await loadSessions();
      setDeleteConfirmSessionId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除session失败');
      console.error('Failed to delete session:', err);
    } finally {
      setDeletingSessionId(null);
    }
  };

  // 显示删除确认
  const showDeleteConfirm = (sessionId: string) => {
    setDeleteConfirmSessionId(sessionId);
  };

  // 取消删除确认
  const cancelDelete = () => {
    setDeleteConfirmSessionId(null);
  };

  // 切换session详情展开/收起
  const toggleSessionDetails = async (sessionId: string) => {
    if (expandedSessionId === sessionId) {
      // 收起
      setExpandedSessionId(null);
    } else {
      // 展开
      setExpandedSessionId(sessionId);
      
      // 如果还没有加载详情，则加载
      if (!sessionDetails[sessionId]) {
        try {
          setLoadingDetails(prev => ({ ...prev, [sessionId]: true }));
          const details = await workflowApi.getSessionDetails(sessionId);
          setSessionDetails(prev => ({ ...prev, [sessionId]: details }));
        } catch (err) {
          setError(err instanceof Error ? err.message : '加载session详情失败');
          console.error('Failed to load session details:', err);
        } finally {
          setLoadingDetails(prev => ({ ...prev, [sessionId]: false }));
        }
      }
    }
  };

  // 下载文件（支持不同类型）
  const handleDownloadFile = async (
    sessionId: string,
    fileName: string,
    fileType: 'uploaded' | 'generated' | 'artifact' = 'uploaded'
  ) => {
    try {
      const blob = await workflowApi.downloadFile(sessionId, fileName, fileType);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : '下载文件失败');
      console.error('Failed to download file:', err);
    }
  };

  return (
    <div className="page-container">
      {/* 标题和刷新按钮 */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '2rem',
        paddingBottom: '1.5rem',
        borderBottom: '1px solid var(--color-border)',
      }}>
        <h1 className="page-title" style={{ margin: 0 }}>Session 管理</h1>
        <button
          onClick={loadSessions}
          disabled={loading}
          className="btn btn-primary"
          style={{
            padding: '0.625rem 1.25rem',
            fontSize: '0.875rem',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="error" style={{ marginBottom: '1.5rem' }}>
          {error}
        </div>
      )}

      {/* Sessions列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-tertiary)', fontSize: '0.875rem' }}>
          加载中...
        </div>
      ) : sessions.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-tertiary)', fontSize: '0.875rem' }}>
          暂无 sessions
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gap: '1rem',
        }}>
          {sessions.map((session) => (
            <div
              key={session.session_id}
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-lg)',
                padding: '1.5rem',
                backgroundColor: 'var(--color-bg-primary)',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                e.currentTarget.style.borderColor = 'var(--color-text-tertiary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = 'none';
                e.currentTarget.style.borderColor = 'var(--color-border)';
              }}
            >
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                gap: '1rem',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: '0.9375rem',
                    fontWeight: 600,
                    color: 'var(--color-text-primary)',
                    marginBottom: '0.75rem',
                    wordBreak: 'break-all',
                    lineHeight: 1.5,
                  }}>
                    {session.session_id}
                  </div>
                  <div style={{
                    display: 'flex',
                    gap: '1.5rem',
                    fontSize: '0.8125rem',
                    color: 'var(--color-text-secondary)',
                    flexWrap: 'wrap',
                  }}>
                    <span>
                      <strong style={{ color: 'var(--color-text-primary)' }}>创建时间:</strong>{' '}
                      {formatDate(session.created_at)}
                    </span>
                    <span>
                      <strong style={{ color: 'var(--color-text-primary)' }}>文件数量:</strong>{' '}
                      {session.file_count}
                    </span>
                    <span>
                      <strong style={{ color: 'var(--color-text-primary)' }}>大小:</strong>{' '}
                      {formatFileSize(session.size)}
                    </span>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0 }}>
                  <button
                    onClick={() => toggleSessionDetails(session.session_id)}
                    className="btn btn-secondary"
                    style={{
                      padding: '0.5rem 1rem',
                      fontSize: '0.8125rem',
                      fontWeight: 500,
                    }}
                  >
                    {expandedSessionId === session.session_id ? '收起详情' : '查看详情'}
                  </button>
                  <button
                    onClick={() => showDeleteConfirm(session.session_id)}
                    disabled={deletingSessionId === session.session_id}
                    className="btn"
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: deletingSessionId === session.session_id ? 'var(--color-text-tertiary)' : 'var(--color-error)',
                      color: 'white',
                      border: 'none',
                      borderRadius: 'var(--radius-sm)',
                      cursor: deletingSessionId === session.session_id ? 'not-allowed' : 'pointer',
                      fontSize: '0.8125rem',
                      fontWeight: 500,
                      opacity: deletingSessionId === session.session_id ? 0.6 : 1,
                    }}
                  >
                    {deletingSessionId === session.session_id ? '删除中...' : '删除'}
                  </button>
                </div>
              </div>
              
              {/* Session详情（可折叠） */}
              {expandedSessionId === session.session_id && (
                <div style={{
                  marginTop: '1.5rem',
                  paddingTop: '1.5rem',
                  borderTop: '1px solid var(--color-border)',
                }}>
                  {loadingDetails[session.session_id] ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>
                      加载中...
                    </div>
                  ) : sessionDetails[session.session_id] ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                      {/* Artifacts */}
                      {Object.keys(sessionDetails[session.session_id].artifacts).length > 0 && (
                        <div>
                          <h4 style={{
                            fontSize: '0.875rem',
                            fontWeight: 600,
                            color: 'var(--color-text-primary)',
                            marginBottom: '0.75rem',
                          }}>
                            Artifacts
                          </h4>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {Object.entries(sessionDetails[session.session_id].artifacts).map(([key, value]) => (
                              <details key={key} style={{
                                border: '1px solid var(--color-border)',
                                borderRadius: 'var(--radius-sm)',
                                padding: '0.75rem',
                                backgroundColor: 'var(--color-bg-secondary)',
                              }}>
                                <summary style={{
                                  cursor: 'pointer',
                                  fontWeight: 500,
                                  color: 'var(--color-text-primary)',
                                  fontSize: '0.8125rem',
                                  marginBottom: '0.5rem',
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                }}>
                                  <span>{key}</span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDownloadFile(session.session_id, key, 'artifact');
                                    }}
                                    className="btn btn-secondary"
                                    style={{
                                      padding: '0.25rem 0.75rem',
                                      fontSize: '0.75rem',
                                    }}
                                  >
                                    下载
                                  </button>
                                </summary>
                                <pre style={{
                                  marginTop: '0.5rem',
                                  padding: '0.75rem',
                                  backgroundColor: 'var(--color-bg-primary)',
                                  borderRadius: 'var(--radius-sm)',
                                  fontSize: '0.75rem',
                                  overflow: 'auto',
                                  maxHeight: '400px',
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word',
                                }}>
                                  {JSON.stringify(value, null, 2)}
                                </pre>
                              </details>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {/* Uploaded Files */}
                      {sessionDetails[session.session_id].uploaded_files.length > 0 && (
                        <div>
                          <h4 style={{
                            fontSize: '0.875rem',
                            fontWeight: 600,
                            color: 'var(--color-text-primary)',
                            marginBottom: '0.75rem',
                          }}>
                            上传的文件
                          </h4>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            {sessionDetails[session.session_id].uploaded_files.map((file) => (
                              <div key={file.name} style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                padding: '0.5rem 0.75rem',
                                border: '1px solid var(--color-border)',
                                borderRadius: 'var(--radius-sm)',
                                backgroundColor: 'var(--color-bg-secondary)',
                              }}>
                                <span style={{
                                  fontSize: '0.8125rem',
                                  color: 'var(--color-text-primary)',
                                }}>
                                  {file.name}
                                </span>
                                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                                  <span style={{
                                    fontSize: '0.75rem',
                                    color: 'var(--color-text-secondary)',
                                  }}>
                                    {formatFileSize(file.size)}
                                  </span>
                                  <button
                                    onClick={() => handleDownloadFile(session.session_id, file.name)}
                                    className="btn btn-secondary"
                                    style={{
                                      padding: '0.25rem 0.75rem',
                                      fontSize: '0.75rem',
                                    }}
                                  >
                                    下载
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {/* Generated Files */}
                      {Object.keys(sessionDetails[session.session_id].generated_files).length > 0 && (
                        <div>
                          <h4 style={{
                            fontSize: '0.875rem',
                            fontWeight: 600,
                            color: 'var(--color-text-primary)',
                            marginBottom: '0.75rem',
                          }}>
                            生成的文件
                          </h4>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {Object.entries(sessionDetails[session.session_id].generated_files).map(([fileName, fileInfo]) => (
                              <details key={fileName} style={{
                                border: '1px solid var(--color-border)',
                                borderRadius: 'var(--radius-sm)',
                                padding: '0.75rem',
                                backgroundColor: 'var(--color-bg-secondary)',
                              }}>
                                <summary style={{
                                  cursor: 'pointer',
                                  fontWeight: 500,
                                  color: 'var(--color-text-primary)',
                                  fontSize: '0.8125rem',
                                  marginBottom: '0.5rem',
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                }}>
                                  <span>{fileName}</span>
                                  <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                                    <span style={{
                                      fontSize: '0.75rem',
                                      color: 'var(--color-text-secondary)',
                                      fontWeight: 'normal',
                                    }}>
                                      {formatFileSize(fileInfo.size)}
                                      {fileInfo.is_binary && ' (二进制文件)'}
                                    </span>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleDownloadFile(session.session_id, fileName, 'generated');
                                      }}
                                      className="btn btn-secondary"
                                      style={{
                                        padding: '0.25rem 0.75rem',
                                        fontSize: '0.75rem',
                                      }}
                                    >
                                      下载
                                    </button>
                                  </div>
                                </summary>
                                {fileInfo.content !== null ? (
                                  <pre style={{
                                    marginTop: '0.5rem',
                                    padding: '0.75rem',
                                    backgroundColor: 'var(--color-bg-primary)',
                                    borderRadius: 'var(--radius-sm)',
                                    fontSize: '0.75rem',
                                    overflow: 'auto',
                                    maxHeight: '400px',
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                  }}>
                                    {fileInfo.content}
                                  </pre>
                                ) : (
                                  <div style={{
                                    marginTop: '0.5rem',
                                    padding: '0.75rem',
                                    color: 'var(--color-text-secondary)',
                                    fontSize: '0.75rem',
                                  }}>
                                    此文件为二进制文件，无法预览
                                  </div>
                                )}
                              </details>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {/* 如果没有内容 */}
                      {Object.keys(sessionDetails[session.session_id].artifacts).length === 0 &&
                       sessionDetails[session.session_id].uploaded_files.length === 0 &&
                       Object.keys(sessionDetails[session.session_id].generated_files).length === 0 && (
                        <div style={{
                          textAlign: 'center',
                          padding: '2rem',
                          color: 'var(--color-text-tertiary)',
                          fontSize: '0.875rem',
                        }}>
                          此session暂无内容
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--color-text-tertiary)' }}>
                      加载失败
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 删除确认弹窗 */}
      {deleteConfirmSessionId && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 1000,
          }}
          onClick={cancelDelete}
        >
          <div
            style={{
              backgroundColor: 'var(--color-bg-primary)',
              borderRadius: 'var(--radius-lg)',
              padding: '2rem',
              maxWidth: '420px',
              width: '90%',
              boxShadow: 'var(--shadow-xl)',
              border: '1px solid var(--color-border)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{
              margin: '0 0 1rem 0',
              fontSize: '1.25rem',
              color: 'var(--color-text-primary)',
              fontWeight: 600,
            }}>
              确认删除
            </h3>
            <p style={{
              margin: '0 0 1.5rem 0',
              color: 'var(--color-text-secondary)',
              lineHeight: '1.6',
              fontSize: '0.875rem',
            }}>
              确定要删除 session <strong style={{ color: 'var(--color-text-primary)' }}>{deleteConfirmSessionId}</strong> 吗？<br />
              此操作将删除该 session 的所有文件，且无法恢复。
            </p>
            <div style={{
              display: 'flex',
              gap: '0.75rem',
              justifyContent: 'flex-end',
            }}>
              <button
                onClick={cancelDelete}
                className="btn btn-secondary"
                style={{
                  padding: '0.625rem 1.25rem',
                  fontSize: '0.875rem',
                }}
              >
                取消
              </button>
              <button
                onClick={() => handleDeleteSession(deleteConfirmSessionId)}
                disabled={deletingSessionId === deleteConfirmSessionId}
                className="btn"
                style={{
                  padding: '0.625rem 1.25rem',
                  backgroundColor: deletingSessionId === deleteConfirmSessionId ? 'var(--color-text-tertiary)' : 'var(--color-error)',
                  color: 'white',
                  fontSize: '0.875rem',
                  opacity: deletingSessionId === deleteConfirmSessionId ? 0.6 : 1,
                }}
              >
                {deletingSessionId === deleteConfirmSessionId ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SessionManager;

