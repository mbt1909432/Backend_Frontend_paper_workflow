import { useState, useEffect } from 'react';
import { tokenUsageApi, TokenUsageResponse, TokenUsageDetail } from '../services/api';
import './TokenUsage.css';

function TokenUsage() {
  const [summary, setSummary] = useState<TokenUsageResponse | null>(null);
  const [allRecords, setAllRecords] = useState<TokenUsageDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(30);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    loadData();
  }, [days]);

  const loadData = async () => {
    setLoading(true);
    setError('');
    try {
      const summaryData = await tokenUsageApi.getSummary(days);
      setSummary(summaryData);
      
      if (showAll) {
        const allData = await tokenUsageApi.getAll(100, 0);
        setAllRecords(allData);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载 token 使用统计失败');
    } finally {
      setLoading(false);
    }
  };

  const formatNumber = (num: number) => {
    return new Intl.NumberFormat('zh-CN').format(num);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('zh-CN');
  };

  if (loading) {
    return (
      <div className="token-usage-container">
        <div className="token-usage-card">
          <div style={{ textAlign: 'center', padding: '2rem' }}>加载中...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="token-usage-container">
        <div className="token-usage-card">
          <div className="error" style={{ padding: '1rem' }}>{error}</div>
        </div>
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  return (
    <div className="token-usage-container">
      <div className="token-usage-card">
        <div className="token-usage-header">
          <h1>Token 使用统计</h1>
          <div className="token-usage-controls">
            <label>
              统计天数:
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem' }}
              >
                <option value={7}>最近 7 天</option>
                <option value={30}>最近 30 天</option>
                <option value={90}>最近 90 天</option>
                <option value={365}>最近 1 年</option>
              </select>
            </label>
            <button
              onClick={() => {
                setShowAll(!showAll);
                if (!showAll) {
                  loadData();
                }
              }}
              className="btn btn-secondary"
              style={{ marginLeft: '1rem' }}
            >
              {showAll ? '隐藏详细记录' : '显示详细记录'}
            </button>
          </div>
        </div>

        {/* Token余额显示 */}
        <div className="token-usage-summary" style={{ 
          backgroundColor: summary.token_balance < 0 ? '#fff3cd' : '#d1ecf1',
          border: `2px solid ${summary.token_balance < 0 ? '#ffc107' : '#0c5460'}`,
          borderRadius: '8px',
          padding: '1.5rem',
          marginBottom: '2rem'
        }}>
          <h2 style={{ 
            marginTop: 0,
            color: summary.token_balance < 0 ? '#856404' : '#0c5460'
          }}>
            Token 剩余额度
          </h2>
          <div style={{ 
            fontSize: '2rem', 
            fontWeight: 'bold',
            color: summary.token_balance < 0 ? '#dc3545' : '#0c5460'
          }}>
            {formatNumber(summary.token_balance)} {summary.token_balance < 0 && '(欠费)'}
          </div>
          {summary.token_balance < 0 && (
            <div style={{ 
              marginTop: '0.5rem',
              color: '#856404',
              fontSize: '0.9rem'
            }}>
              注意：您的账户已欠费，请及时充值
            </div>
          )}
        </div>

        {/* 汇总统计 */}
        <div className="token-usage-summary">
          <h2>汇总统计</h2>
          <div className="summary-grid">
            <div className="summary-item">
              <div className="summary-label">总 Token 数</div>
              <div className="summary-value">{formatNumber(summary.summary.total_tokens)}</div>
            </div>
            <div className="summary-item">
              <div className="summary-label">Prompt Tokens</div>
              <div className="summary-value">{formatNumber(summary.summary.total_prompt_tokens)}</div>
            </div>
            <div className="summary-item">
              <div className="summary-label">Completion Tokens</div>
              <div className="summary-value">{formatNumber(summary.summary.total_completion_tokens)}</div>
            </div>
            <div className="summary-item">
              <div className="summary-label">记录数</div>
              <div className="summary-value">{formatNumber(summary.summary.record_count)}</div>
            </div>
          </div>
        </div>

        {/* 按阶段统计 */}
        {summary.by_stage.length > 0 && (
          <div className="token-usage-section">
            <h2>按阶段统计</h2>
            <table className="token-usage-table">
              <thead>
                <tr>
                  <th>阶段</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>总 Tokens</th>
                  <th>记录数</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_stage.map((item, index) => (
                  <tr key={index}>
                    <td>{item.stage}</td>
                    <td>{formatNumber(item.prompt_tokens)}</td>
                    <td>{formatNumber(item.completion_tokens)}</td>
                    <td>{formatNumber(item.total_tokens)}</td>
                    <td>{formatNumber(item.record_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 按模型统计 */}
        {summary.by_model.length > 0 && (
          <div className="token-usage-section">
            <h2>按模型统计</h2>
            <table className="token-usage-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>总 Tokens</th>
                  <th>记录数</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_model.map((item, index) => (
                  <tr key={index}>
                    <td>{item.model || '未知'}</td>
                    <td>{formatNumber(item.prompt_tokens)}</td>
                    <td>{formatNumber(item.completion_tokens)}</td>
                    <td>{formatNumber(item.total_tokens)}</td>
                    <td>{formatNumber(item.record_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 详细记录 */}
        {showAll && (
          <div className="token-usage-section">
            <h2>详细记录（最近 20 条）</h2>
            <table className="token-usage-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>阶段</th>
                  <th>模型</th>
                  <th>Session ID</th>
                  <th>Prompt Tokens</th>
                  <th>Completion Tokens</th>
                  <th>总 Tokens</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_records.map((record) => (
                  <tr key={record.id}>
                    <td>{formatDate(record.created_at)}</td>
                    <td>{record.stage || '未知'}</td>
                    <td>{record.model || '未知'}</td>
                    <td style={{ maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {record.session_id || '-'}
                    </td>
                    <td>{formatNumber(record.prompt_tokens)}</td>
                    <td>{formatNumber(record.completion_tokens)}</td>
                    <td>{formatNumber(record.total_tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default TokenUsage;

