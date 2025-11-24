import { useState } from 'react';
import { latexPaperApi } from '../services/api';
import type { LaTeXPaperRequest, LaTeXPaperResponse, StreamChunk } from '../types';

function LaTeXPaper() {
  const [paperOverview, setPaperOverview] = useState('');
  const [userInfo, setUserInfo] = useState('');
  const [hasOutline, setHasOutline] = useState(false);
  const [hasExistingTex, setHasExistingTex] = useState(false);
  const [response, setResponse] = useState<LaTeXPaperResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useStream, setUseStream] = useState(true);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(30000);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!paperOverview.trim()) return;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const request: LaTeXPaperRequest = {
        paper_overview: paperOverview,
        user_info: userInfo || undefined,
        has_outline: hasOutline,
        has_existing_tex: hasExistingTex,
        temperature,
        max_tokens: maxTokens,
      };

      if (useStream) {
        let fullResponse = '';
        await latexPaperApi.generateStream(
          request,
          (chunk: StreamChunk) => {
            fullResponse += chunk.chunk;
            if (chunk.done) {
              try {
                const parsed = JSON.parse(fullResponse);
                setResponse(parsed);
              } catch {
                // 检查是否包含 SKIPPED 标记
                if (fullResponse.includes('SKIPPED')) {
                  const skipReasonMatch = fullResponse.match(/SKIPPED:\s*(.*?)(?:\n|$)/s);
                  setResponse({
                    file_name: 'paper.tex',
                    file_content: '',
                    raw_response: fullResponse,
                    is_skipped: true,
                    skip_reason: skipReasonMatch ? skipReasonMatch[1].trim() : '未知原因',
                  });
                } else {
                  // 解析 markdown 格式（```path 和 ```latex 块）
                  const pathPattern = /```path\s*\n?(.*?)\n?```/s;
                  const latexPattern = /```latex\s*\n?(.*?)\n?```/s;
                  
                  const pathMatch = fullResponse.match(pathPattern);
                  const latexMatch = fullResponse.match(latexPattern);
                  
                  if (pathMatch && latexMatch) {
                    const file_name = pathMatch[1].trim();
                    const file_content = latexMatch[1].trim();
                    
                    setResponse({
                      file_name: file_name || 'paper.tex',
                      file_content: file_content,
                      raw_response: fullResponse,
                      is_skipped: false,
                    });
                  } else {
                    // 如果解析失败，显示原始内容
                    setResponse({
                      file_name: 'paper.tex',
                      file_content: fullResponse,
                      raw_response: fullResponse,
                      is_skipped: false,
                    });
                  }
                }
              }
              setLoading(false);
            }
          },
          (err) => {
            setError(err.message);
            setLoading(false);
          }
        );
      } else {
        const result: LaTeXPaperResponse = await latexPaperApi.generate(request);
        setResponse(result);
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '发生未知错误');
      setLoading(false);
    }
  };

  return (
    <div className="page-container">
      <h1 className="page-title">
        <span>📝</span>
        LaTeX 论文生成
      </h1>
      <p className="page-description">
        根据论文概览生成完整的 LaTeX 论文文件。如果提供了大纲或存在现有的 .tex 文件，可能会跳过生成。
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">论文概览内容 *</label>
          <textarea
            className="form-textarea"
            value={paperOverview}
            onChange={(e) => setPaperOverview(e.target.value)}
            placeholder="输入从 Paper Overview Agent 得到的文本内容..."
            rows={8}
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label">用户额外信息（可选）</label>
          <textarea
            className="form-textarea"
            value={userInfo}
            onChange={(e) => setUserInfo(e.target.value)}
            placeholder="输入您希望添加到论文中的额外信息..."
            rows={4}
          />
        </div>

        <div className="form-group">
          <div className="checkbox-group">
            <input
              type="checkbox"
              id="hasOutline"
              checked={hasOutline}
              onChange={(e) => setHasOutline(e.target.checked)}
            />
            <label htmlFor="hasOutline">用户已提供论文大纲</label>
          </div>
        </div>

        <div className="form-group">
          <div className="checkbox-group">
            <input
              type="checkbox"
              id="hasExistingTex"
              checked={hasExistingTex}
              onChange={(e) => setHasExistingTex(e.target.checked)}
            />
            <label htmlFor="hasExistingTex">存在现有的 .tex 文件</label>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label className="form-label">温度 (0-2)</label>
            <input
              type="number"
              className="form-input"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              min="0"
              max="2"
              step="0.1"
            />
          </div>
          <div className="form-group">
            <label className="form-label">最大 Token 数</label>
            <input
              type="number"
              className="form-input"
              value={maxTokens}
              onChange={(e) => setMaxTokens(parseInt(e.target.value))}
              min="1"
            />
          </div>
        </div>

        <div className="form-group">
          <div className="checkbox-group">
            <input
              type="checkbox"
              id="useStream"
              checked={useStream}
              onChange={(e) => setUseStream(e.target.checked)}
            />
            <label htmlFor="useStream">使用流式响应</label>
          </div>
        </div>

        <div className="button-group">
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading && <span className="loading"></span>}
            生成 LaTeX 论文
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setPaperOverview('');
              setUserInfo('');
              setHasOutline(false);
              setHasExistingTex(false);
              setResponse(null);
              setError(null);
            }}
          >
            清空
          </button>
        </div>
      </form>

      {error && <div className="error">{error}</div>}

      {response && (
        <div className="response-container">
          <div className="response-header">
            <h3 className="response-title">生成结果</h3>
            {response.is_skipped ? (
              <span style={{ color: '#f59e0b', fontWeight: 'bold' }}>已跳过</span>
            ) : (
              <span style={{ fontSize: '0.85rem', color: '#666' }}>
                文件名: {response.file_name || 'N/A'}
              </span>
            )}
          </div>
          {response.is_skipped ? (
            <div style={{ padding: '1rem', background: '#fff3cd', borderRadius: '8px', color: '#856404' }}>
              <strong>跳过原因:</strong> {response.skip_reason || '未知原因'}
            </div>
          ) : (
            <>
              <div className="response-content">{response.file_content || '无内容'}</div>
              {response.usage && (
                <div className="response-meta">
                  Token 使用: {response.usage.total_tokens || 'N/A'} (
                  {response.usage.prompt_tokens || 'N/A'} prompt +{' '}
                  {response.usage.completion_tokens || 'N/A'} completion)
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default LaTeXPaper;

