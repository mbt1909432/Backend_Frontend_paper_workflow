import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../services/api';
import './Login.css';

function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      console.log('[Login] 开始登录请求...');
      const response = await authApi.login(username, password);
      console.log('[Login] 登录响应:', response);
      
      // 验证响应格式
      if (!response || !response.access_token) {
        console.error('[Login] 响应格式错误:', response);
        setError('登录响应格式错误，请重试');
        setLoading(false);
        return;
      }
      
      // 检查用户类型：前端用户不能访问此系统
      if (response.user_type === 'frontend') {
        setError('前端用户无法访问此系统，请联系管理员');
        setLoading(false);
        return;
      }
      
      // 保存 token 和用户信息
      localStorage.setItem('auth_token', response.access_token);
      localStorage.setItem('auth_user', JSON.stringify({
        username: response.username,
        is_admin: response.is_admin,
        user_type: response.user_type,
      }));
      
      console.log('[Login] Token 已保存到 localStorage');
      console.log('[Login] 当前路径:', window.location.pathname);
      
      // 尝试使用 navigate 跳转
      navigate('/');
      
      // 备选方案：如果 navigate 不工作，使用 window.location.href
      setTimeout(() => {
        if (window.location.pathname === '/login') {
          console.warn('[Login] navigate 未生效，使用 window.location.href 跳转');
          window.location.href = '/';
        }
      }, 100);
    } catch (err: any) {
      console.error('[Login] 登录错误:', err);
      console.error('[Login] 错误详情:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status,
      });
      setError(err.response?.data?.detail || '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <h1 className="login-title">登录</h1>
        <p className="login-subtitle">ResearchFlow</p>
        
        {error && <div className="error">{error}</div>}
        
        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label className="form-label">用户名</label>
            <input
              type="text"
              className="form-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          
          <div className="form-group">
            <label className="form-label">密码</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: '100%', marginTop: '1rem' }}
          >
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;

