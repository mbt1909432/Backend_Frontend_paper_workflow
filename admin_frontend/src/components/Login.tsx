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
      const response = await authApi.login(username, password);
      console.log('Login response:', response);
      
      if (!response || !response.access_token) {
        console.error('Invalid response format:', response);
        throw new Error('登录响应格式错误：缺少 access_token');
      }
      
      localStorage.setItem('admin_token', response.access_token);
      localStorage.setItem('admin_user', JSON.stringify({
        username: response.username || username,
        is_admin: response.is_admin || false,
      }));
      
      console.log('Token saved successfully');
      console.log('Current token:', localStorage.getItem('admin_token'));
      
      // 使用 replace: true 确保替换历史记录
      navigate('/users', { replace: true });
      
      // 如果 navigate 没有立即生效，使用 window.location 作为备选
      setTimeout(() => {
        if (window.location.pathname === '/login') {
          console.warn('Navigate did not work, using window.location');
          window.location.href = '/users';
        }
      }, 100);
    } catch (err: any) {
      console.error('Login error:', err);
      console.error('Error details:', {
        message: err.message,
        response: err.response,
        data: err.response?.data,
      });
      setError(err.response?.data?.detail || err.message || '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <h1 className="login-title">管理员登录</h1>
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

