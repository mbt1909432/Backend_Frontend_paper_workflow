import { useState } from 'react';
import { agentApi } from '../services/api';
import type { ChatRequest, ChatResponse, StreamChunk } from '../types';

function AgentChat() {
  const [message, setMessage] = useState('');
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [response, setResponse] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useStream, setUseStream] = useState(true);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(2000);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;

    setLoading(true);
    setError(null);
    setResponse('');

    try {
      const request: ChatRequest = {
        message,
        conversation_id: conversationId,
        temperature,
        max_tokens: maxTokens,
      };

      if (useStream) {
        let fullResponse = '';
        await agentApi.chatStream(
          request,
          (chunk: StreamChunk) => {
            fullResponse += chunk.chunk;
            setResponse(fullResponse);
            if (chunk.done && chunk.usage) {
              setLoading(false);
            }
          },
          (err) => {
            setError(err.message);
            setLoading(false);
          }
        );
      } else {
        const result: ChatResponse = await agentApi.chat(request);
        setResponse(result.response);
        setConversationId(result.conversation_id);
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
        <span>💬</span>
        通用对话 Agent
      </h1>
      <p className="page-description">
        与 AI 进行对话，支持多轮对话和流式响应。可以设置温度参数和最大 token 数。
      </p>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">消息内容</label>
          <textarea
            className="form-textarea"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="输入您的问题或消息..."
            rows={5}
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
            发送消息
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setMessage('');
              setResponse('');
              setConversationId(undefined);
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
            <h3 className="response-title">AI 回复</h3>
            {conversationId && (
              <span style={{ fontSize: '0.85rem', color: '#666' }}>
                会话 ID: {conversationId}
              </span>
            )}
          </div>
          <div className="response-content">{response}</div>
        </div>
      )}
    </div>
  );
}

export default AgentChat;

