import { useState } from 'react';
import { paperOverviewApi } from '../services/api';
import type { PaperOverviewRequest, PaperOverviewResponse, StreamChunk } from '../types';

function PaperOverview() {
  const [document, setDocument] = useState('');
  const [response, setResponse] = useState<PaperOverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useStream, setUseStream] = useState(true);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(30000);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!document.trim()) return;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const request: PaperOverviewRequest = {
        document,
        temperature,
        max_tokens: maxTokens,
      };

      if (useStream) {
        let fullResponse = '';
        await paperOverviewApi.generateStream(
          request,
          (chunk: StreamChunk) => {
            fullResponse += chunk.chunk;
            // 尝试解析流式响应中的文件名和内容
            if (chunk.done) {
              try {
                // 流式响应可能包含完整的 JSON，需要解析
                const parsed = JSON.parse(fullResponse);
                setResponse(parsed);
              } catch {
                // 如果不是 JSON，解析 markdown 格式（```path 和 ```text 块）
                const pathPattern = /```path\s*\n?(.*?)\n?```/s;
                const textPattern = /```text\s*\n?(.*?)\n?```/s;
                
                const pathMatch = fullResponse.match(pathPattern);
                const textMatch = fullResponse.match(textPattern);
                
                if (pathMatch && textMatch) {
                  const file_name = pathMatch[1].trim();
                  const file_content = textMatch[1].trim();
                  
                  setResponse({
                    file_name: file_name || 'paper_overview.md',
                    file_content: file_content,
                    raw_response: fullResponse,
                  });
                } else {
                  // 如果解析失败，显示原始内容
                  setResponse({
                    file_name: 'paper_overview.md',
                    file_content: fullResponse,
                    raw_response: fullResponse,
                  });
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
        const result: PaperOverviewResponse = await paperOverviewApi.generate(request);
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
        <span>📄</span>
        论文概览生成
      </h1>
      <p className="page-description">
        根据您提供的文档内容，生成论文概览文件。输入您的文档内容，AI 将生成结构化的论文概览。
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">文档内容</label>
          <textarea
            className="form-textarea"
            value={document}
            onChange={(e) => setDocument(e.target.value)}
            placeholder="输入您的文档内容..."
            rows={10}
          />
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
            生成论文概览
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setDocument('');
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
            <span style={{ fontSize: '0.85rem', color: '#666' }}>
              文件名: {response.file_name}
            </span>
          </div>
          <div className="response-content">{response.file_content}</div>
          {response.usage && (
            <div className="response-meta">
              Token 使用: {response.usage.total_tokens || 'N/A'} (
              {response.usage.prompt_tokens || 'N/A'} prompt +{' '}
              {response.usage.completion_tokens || 'N/A'} completion)
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default PaperOverview;

