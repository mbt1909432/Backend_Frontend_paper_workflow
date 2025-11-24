import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { userApi, User, CreateUserRequest, UpdateUserRequest, UpdateMaxConcurrentWorkflowsRequest } from '../services/api';
import './UserManagement.css';

function UserManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [showWorkflowModal, setShowWorkflowModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [tokenUser, setTokenUser] = useState<User | null>(null);
  const [workflowUser, setWorkflowUser] = useState<User | null>(null);
  const [deleteConfirmUserId, setDeleteConfirmUserId] = useState<string | null>(null);
  const [tokenBalance, setTokenBalance] = useState<string>('');
  const [maxConcurrentWorkflows, setMaxConcurrentWorkflows] = useState<string>('');
  const navigate = useNavigate();

  const [newUser, setNewUser] = useState<CreateUserRequest>({
    username: '',
    password: '',
    user_type: 'backend',
  });

  const [editUser, setEditUser] = useState<UpdateUserRequest>({
    password: '',
    is_active: true,
    user_type: undefined,
  });

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const data = await userApi.listUsers();
      setUsers(data);
      setError('');
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载用户列表失败');
      if (err.response?.status === 401) {
        navigate('/login');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await userApi.createUser(newUser);
      setShowCreateModal(false);
      setNewUser({ username: '', password: '', user_type: 'backend' });
      setSuccess('用户创建成功');
      loadUsers();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || '创建用户失败');
    }
  };

  const handleEditUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;
    
    try {
      const updateData: UpdateUserRequest = {};
      if (editUser.password) {
        updateData.password = editUser.password;
      }
      if (editUser.is_active !== undefined) {
        updateData.is_active = editUser.is_active;
      }
      if (editUser.user_type !== undefined) {
        updateData.user_type = editUser.user_type;
      }
      
      await userApi.updateUser(editingUser.id, updateData);
      setShowEditModal(false);
      setEditingUser(null);
      setEditUser({ password: '', is_active: true, user_type: undefined });
      setSuccess('用户更新成功');
      loadUsers();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || '更新用户失败');
    }
  };

  const handleDeleteUser = async (userId: string) => {
    try {
      await userApi.deleteUser(userId);
      setDeleteConfirmUserId(null);
      setSuccess('用户删除成功');
      loadUsers();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || '删除用户失败');
    }
  };

  const openEditModal = (user: User) => {
    setEditingUser(user);
    setEditUser({
      password: '',
      is_active: user.is_active,
      user_type: user.user_type,
    });
    setShowEditModal(true);
  };

  const openTokenModal = (user: User) => {
    setTokenUser(user);
    setTokenBalance(user.token_balance.toString());
    setShowTokenModal(true);
  };

  const handleUpdateTokenBalance = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tokenUser) return;
    
    try {
      const balance = parseInt(tokenBalance);
      if (isNaN(balance)) {
        setError('请输入有效的数字');
        return;
      }
      
      await userApi.updateTokenBalance(tokenUser.id, { token_balance: balance });
      setShowTokenModal(false);
      setTokenUser(null);
      setTokenBalance('');
      setSuccess('Token余额更新成功');
      loadUsers();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || '更新Token余额失败');
    }
  };

  const formatTokenBalance = (balance: number): string => {
    if (balance >= 1000000) {
      return `${(balance / 1000000).toFixed(2)}M`;
    } else if (balance >= 1000) {
      return `${(balance / 1000).toFixed(2)}K`;
    }
    return balance.toString();
  };

  const openWorkflowModal = (user: User) => {
    setWorkflowUser(user);
    setMaxConcurrentWorkflows(user.max_concurrent_workflows.toString());
    setShowWorkflowModal(true);
  };

  const handleUpdateMaxConcurrentWorkflows = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workflowUser) return;
    
    try {
      const maxWorkflows = parseInt(maxConcurrentWorkflows);
      if (isNaN(maxWorkflows) || maxWorkflows < 1) {
        setError('请输入有效的数字（必须大于0）');
        return;
      }
      
      await userApi.updateMaxConcurrentWorkflows(workflowUser.id, { max_concurrent_workflows: maxWorkflows });
      setShowWorkflowModal(false);
      setWorkflowUser(null);
      setMaxConcurrentWorkflows('');
      setSuccess('最大并发workflow数更新成功');
      loadUsers();
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || '更新最大并发workflow数失败');
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_user');
    navigate('/login');
  };

  const adminUser = JSON.parse(localStorage.getItem('admin_user') || '{}');

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1 className="page-title">用户管理</h1>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.875rem' }}>
            欢迎，{adminUser.username}
          </span>
          <button className="btn btn-secondary" onClick={handleLogout}>
            退出登录
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
            创建用户
          </button>
        </div>
      </div>

      {error && <div className="error" style={{ marginBottom: '1rem' }}>{error}</div>}
      {success && <div className="success" style={{ marginBottom: '1rem' }}>{success}</div>}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-tertiary)' }}>
          加载中...
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>管理员</th>
              <th>用户类型</th>
              <th>状态</th>
              <th>Token余额</th>
              <th>最大并发Workflow</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td data-label="用户名">{user.username}</td>
                <td data-label="管理员">{user.is_admin ? '是' : '否'}</td>
                <td data-label="用户类型">
                  <span style={{ 
                    color: user.user_type === 'backend' ? '#2563eb' : '#16a34a',
                    fontWeight: '500'
                  }}>
                    {user.user_type === 'backend' ? '后端用户' : '前端用户'}
                  </span>
                </td>
                <td data-label="状态">
                  <span style={{ color: user.is_active ? '#16a34a' : '#dc2626' }}>
                    {user.is_active ? '启用' : '禁用'}
                  </span>
                </td>
                <td data-label="Token余额">
                  <span style={{ 
                    color: user.token_balance < 0 ? '#dc2626' : user.token_balance < 100000 ? '#f59e0b' : '#16a34a',
                    fontWeight: user.token_balance < 0 ? 'bold' : 'normal'
                  }}>
                    {formatTokenBalance(user.token_balance)}
                    {user.token_balance < 0 && ' (欠费)'}
                  </span>
                </td>
                <td data-label="最大并发Workflow">
                  <span style={{ 
                    color: user.max_concurrent_workflows <= 5 ? '#f59e0b' : '#16a34a',
                    fontWeight: 'normal'
                  }}>
                    {user.max_concurrent_workflows}
                  </span>
                </td>
                <td data-label="创建时间">{new Date(user.created_at).toLocaleString('zh-CN')}</td>
                <td data-label="操作">
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                      onClick={() => openEditModal(user)}
                    >
                      编辑
                    </button>
                    <button
                      className="btn btn-primary"
                      style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                      onClick={() => openTokenModal(user)}
                    >
                      充值Token
                    </button>
                    <button
                      className="btn btn-primary"
                      style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                      onClick={() => openWorkflowModal(user)}
                    >
                      设置并发数
                    </button>
                    {!user.is_admin && (
                      <button
                        className="btn btn-danger"
                        style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                        onClick={() => setDeleteConfirmUserId(user.id)}
                      >
                        删除
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* 创建用户弹窗 */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '1.5rem' }}>创建用户</h2>
            <form onSubmit={handleCreateUser}>
              <div className="form-group">
                <label className="form-label">用户名</label>
                <input
                  type="text"
                  className="form-input"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">密码</label>
                <input
                  type="password"
                  className="form-input"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">用户类型</label>
                <select
                  className="form-input"
                  value={newUser.user_type || 'backend'}
                  onChange={(e) => setNewUser({ ...newUser, user_type: e.target.value })}
                  required
                >
                  <option value="backend">后端用户（业务员工）</option>
                  <option value="frontend">前端用户（销售人员对接）</option>
                </select>
                <div style={{ 
                  marginTop: '0.5rem', 
                  fontSize: '0.8125rem', 
                  color: 'var(--color-text-secondary)' 
                }}>
                  后端用户可以使用业务系统（端口3000），前端用户无法访问
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                >
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  创建
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 编辑用户弹窗 */}
      {showEditModal && editingUser && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '1.5rem' }}>编辑用户: {editingUser.username}</h2>
            <form onSubmit={handleEditUser}>
              <div className="form-group">
                <label className="form-label">新密码（留空则不修改）</label>
                <input
                  type="password"
                  className="form-input"
                  value={editUser.password}
                  onChange={(e) => setEditUser({ ...editUser, password: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input
                    type="checkbox"
                    checked={editUser.is_active}
                    onChange={(e) => setEditUser({ ...editUser, is_active: e.target.checked })}
                  />
                  <span>启用</span>
                </label>
              </div>
              <div className="form-group">
                <label className="form-label">用户类型</label>
                <select
                  className="form-input"
                  value={editUser.user_type || editingUser.user_type}
                  onChange={(e) => setEditUser({ ...editUser, user_type: e.target.value })}
                  required
                >
                  <option value="backend">后端用户（业务员工）</option>
                  <option value="frontend">前端用户（销售人员对接）</option>
                </select>
                <div style={{ 
                  marginTop: '0.5rem', 
                  fontSize: '0.8125rem', 
                  color: 'var(--color-text-secondary)' 
                }}>
                  后端用户可以使用业务系统（端口3000），前端用户无法访问
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowEditModal(false)}
                >
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Token余额管理弹窗 */}
      {showTokenModal && tokenUser && (
        <div className="modal-overlay" onClick={() => setShowTokenModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '1.5rem' }}>管理Token余额: {tokenUser.username}</h2>
            <form onSubmit={handleUpdateTokenBalance}>
              <div className="form-group">
                <label className="form-label">当前余额</label>
                <div style={{ 
                  padding: '0.75rem', 
                  backgroundColor: 'var(--color-bg-secondary)', 
                  borderRadius: '0.375rem',
                  color: tokenUser.token_balance < 0 ? '#dc2626' : 'var(--color-text-primary)',
                  fontWeight: tokenUser.token_balance < 0 ? 'bold' : 'normal'
                }}>
                  {formatTokenBalance(tokenUser.token_balance)} Token
                  {tokenUser.token_balance < 0 && ' (欠费)'}
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">设置新余额</label>
                <input
                  type="number"
                  className="form-input"
                  value={tokenBalance}
                  onChange={(e) => setTokenBalance(e.target.value)}
                  placeholder="请输入Token余额"
                  required
                  min="0"
                  step="1"
                />
                <div style={{ 
                  marginTop: '0.5rem', 
                  fontSize: '0.8125rem', 
                  color: 'var(--color-text-secondary)' 
                }}>
                  提示：可以设置为任意数值，包括负数（欠费）
                </div>
              </div>
              <div style={{ 
                display: 'flex', 
                gap: '0.75rem', 
                marginTop: '1rem',
                padding: '0.75rem',
                backgroundColor: 'var(--color-bg-secondary)',
                borderRadius: '0.375rem'
              }}>
                <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                  <strong>快捷充值：</strong>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setTokenBalance('1000000')}
                >
                  +100万
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setTokenBalance('5000000')}
                >
                  +500万
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setTokenBalance('10000000')}
                >
                  +1000万
                </button>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    setShowTokenModal(false);
                    setTokenUser(null);
                    setTokenBalance('');
                  }}
                >
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 最大并发Workflow数管理弹窗 */}
      {showWorkflowModal && workflowUser && (
        <div className="modal-overlay" onClick={() => setShowWorkflowModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '1.5rem' }}>设置最大并发Workflow数: {workflowUser.username}</h2>
            <form onSubmit={handleUpdateMaxConcurrentWorkflows}>
              <div className="form-group">
                <label className="form-label">当前最大并发数</label>
                <div style={{ 
                  padding: '0.75rem', 
                  backgroundColor: 'var(--color-bg-secondary)', 
                  borderRadius: '0.375rem',
                  color: 'var(--color-text-primary)'
                }}>
                  {workflowUser.max_concurrent_workflows}
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">设置新最大并发数</label>
                <input
                  type="number"
                  className="form-input"
                  value={maxConcurrentWorkflows}
                  onChange={(e) => setMaxConcurrentWorkflows(e.target.value)}
                  placeholder="请输入最大并发workflow数"
                  required
                  min="1"
                  step="1"
                />
                <div style={{ 
                  marginTop: '0.5rem', 
                  fontSize: '0.8125rem', 
                  color: 'var(--color-text-secondary)' 
                }}>
                  提示：用户同时最多可以运行此数量的workflow（默认10）
                </div>
              </div>
              <div style={{ 
                display: 'flex', 
                gap: '0.75rem', 
                marginTop: '1rem',
                padding: '0.75rem',
                backgroundColor: 'var(--color-bg-secondary)',
                borderRadius: '0.375rem'
              }}>
                <div style={{ fontSize: '0.8125rem', color: 'var(--color-text-secondary)' }}>
                  <strong>快捷设置：</strong>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setMaxConcurrentWorkflows('5')}
                >
                  5
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setMaxConcurrentWorkflows('10')}
                >
                  10
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setMaxConcurrentWorkflows('20')}
                >
                  20
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem', fontSize: '0.8125rem' }}
                  onClick={() => setMaxConcurrentWorkflows('50')}
                >
                  50
                </button>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => {
                    setShowWorkflowModal(false);
                    setWorkflowUser(null);
                    setMaxConcurrentWorkflows('');
                  }}
                >
                  取消
                </button>
                <button type="submit" className="btn btn-primary">
                  保存
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      {deleteConfirmUserId && (
        <div className="modal-overlay" onClick={() => setDeleteConfirmUserId(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '1rem' }}>确认删除</h2>
            <p style={{ marginBottom: '1.5rem', color: 'var(--color-text-secondary)' }}>
              确定要删除用户 <strong>{users.find(u => u.id === deleteConfirmUserId)?.username}</strong> 吗？此操作无法撤销。
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setDeleteConfirmUserId(null)}
              >
                取消
              </button>
              <button
                className="btn btn-danger"
                onClick={() => handleDeleteUser(deleteConfirmUserId)}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default UserManagement;

