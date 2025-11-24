import { useState } from 'react';
import { requirementChecklistApi } from '../services/api';
import type { RequirementChecklistRequest, RequirementChecklistResponse, StreamChunk } from '../types';

function RequirementChecklist() {
  const [paperOverview, setPaperOverview] = useState('');
  const [latexContent, setLatexContent] = useState('');
  const [userOriginalInput, setUserOriginalInput] = useState('');
  const [response, setResponse] = useState<RequirementChecklistResponse | null>(null);
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
      const request: RequirementChecklistRequest = {
        paper_overview: paperOverview,
        latex_content: latexContent || undefined,
        user_original_input: userOriginalInput || undefined,
        temperature,
        max_tokens: maxTokens,
      };

      if (useStream) {
        let fullResponse = '';
        await requirementChecklistApi.generateStream(
          request,
          (chunk: StreamChunk) => {
            fullResponse += chunk.chunk;
            if (chunk.done) {
              try {
                const parsed = JSON.parse(fullResponse);
                setResponse(parsed);
              } catch {
                // 解析 markdown 格式（```path 和 ```markdown 块）
                const pathPattern = /```path\s*\n?(.*?)\n?```/s;
                const markdownPattern = /```markdown\s*\n?(.*?)\n?```/s;
                
                const pathMatch = fullResponse.match(pathPattern);
                const markdownMatch = fullResponse.match(markdownPattern);
                
                if (pathMatch && markdownMatch) {
                  const file_name = pathMatch[1].trim();
                  const file_content = markdownMatch[1].trim();
                  
                  setResponse({
                    file_name: file_name || 'requirement_checklist.md',
                    file_content: file_content,
                    raw_response: fullResponse,
                  });
                } else {
                  // 如果解析失败，显示原始内容
                  setResponse({
                    file_name: 'requirement_checklist.md',
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
        const result: RequirementChecklistResponse = await requirementChecklistApi.generate(request);
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
        <span>✅</span>
        需求清单生成
      </h1>
      <p className="page-description">
        根据论文概览和 LaTeX 论文内容（或用户原始输入）生成需求清单，检查论文是否符合要求。
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">论文概览内容 *</label>
          <textarea
            className="form-textarea"
            value={paperOverview}
            onChange={(e) => setPaperOverview(e.target.value)}
            placeholder="输入从 Paper Overview Agent 得到的文本内容..."
            rows={6}
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label">LaTeX 内容（可选）</label>
          <textarea
            className="form-textarea"
            value={latexContent}
            onChange={(e) => setLatexContent(e.target.value)}
            placeholder="输入从 LaTeX Paper Generator Agent 得到的 LaTeX 内容（如果 Agent 没有跳过）..."
            rows={6}
          />
        </div>

        <div className="form-group">
          <label className="form-label">用户原始输入（可选）</label>
          <textarea
            className="form-textarea"
            value={userOriginalInput}
            onChange={(e) => setUserOriginalInput(e.target.value)}
            placeholder="如果 LaTeX Paper Generator Agent 跳过了生成，则使用此输入..."
            rows={4}
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
            生成需求清单
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setPaperOverview('');
              setLatexContent('');
              setUserOriginalInput('');
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

export default RequirementChecklist;

