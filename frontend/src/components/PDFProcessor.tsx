import { useState } from 'react';
import { pdfProcessApi } from '../services/api';
import type { PDFProcessRequest, PDFProcessResponse } from '../types';

function PDFProcessor() {
  const [file, setFile] = useState<File | null>(null);
  const [textPrompt, setTextPrompt] = useState('');
  const [temperature, setTemperature] = useState(0.3);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [dpi, setDpi] = useState(300);
  const [response, setResponse] = useState<PDFProcessResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<string>('');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      if (selectedFile.type !== 'application/pdf') {
        setError('请选择 PDF 文件');
        return;
      }
      setFile(selectedFile);
      setError(null);
      setResponse(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError('请选择 PDF 文件');
      return;
    }

    setLoading(true);
    setError(null);
    setResponse(null);
    setProgress('正在上传 PDF 文件...');

    try {
      const options: PDFProcessRequest = {
        text_prompt: textPrompt || undefined,
        temperature,
        max_tokens: maxTokens,
        dpi,
      };

      setProgress('正在将 PDF 转换为 PNG 图片...');
      const result = await pdfProcessApi.process(file, options);
      
      setResponse(result);
      setProgress(`处理完成！共处理 ${result.page_count} 页`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '处理失败');
      setProgress('');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!response) return;

    const blob = new Blob([response.response], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pdf_extracted_text_${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="container">
      <div className="card">
        <h1 className="card-title">PDF 文字提取</h1>
        <p className="card-description">
          上传 PDF 文件，系统会自动将 PDF 转换为图片，使用 Vision Agent 提取每页的文字描述，并拼接成完整文本。
        </p>

        <form onSubmit={handleSubmit} className="form">
          <div className="form-group">
            <label htmlFor="file" className="form-label">
              选择 PDF 文件
            </label>
            <input
              type="file"
              id="file"
              accept=".pdf"
              onChange={handleFileChange}
              className="form-input-file"
              disabled={loading}
            />
            {file && (
              <div className="file-info">
                <span>已选择: {file.name}</span>
                <span>大小: {(file.size / 1024 / 1024).toFixed(2)} MB</span>
              </div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="textPrompt" className="form-label">
              文本提示（可选）
            </label>
            <textarea
              id="textPrompt"
              value={textPrompt}
              onChange={(e) => setTextPrompt(e.target.value)}
              placeholder="可选的文本提示，用于指导图片分析。如果不提供，将使用默认提示来提取文字描述。"
              className="form-textarea"
              rows={3}
              disabled={loading}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="temperature" className="form-label">
                温度参数
              </label>
              <input
                type="number"
                id="temperature"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                min="0"
                max="2"
                step="0.1"
                className="form-input"
                disabled={loading}
              />
              <small className="form-hint">OCR 建议使用较低温度（0.3）</small>
            </div>

            <div className="form-group">
              <label htmlFor="maxTokens" className="form-label">
                最大 Token 数（每页）
              </label>
              <input
                type="number"
                id="maxTokens"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                min="1"
                className="form-input"
                disabled={loading}
              />
            </div>

            <div className="form-group">
              <label htmlFor="dpi" className="form-label">
                DPI 分辨率
              </label>
              <input
                type="number"
                id="dpi"
                value={dpi}
                onChange={(e) => setDpi(parseInt(e.target.value))}
                min="72"
                max="600"
                step="1"
                className="form-input"
                disabled={loading}
              />
              <small className="form-hint">推荐 300 DPI</small>
            </div>
          </div>

          {error && <div className="error-message">{error}</div>}
          {progress && <div className="progress-message">{progress}</div>}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || !file}
          >
            {loading ? '处理中...' : '开始处理'}
          </button>
        </form>

        {response && (
          <div className="result-section">
            <div className="result-header">
              <h2>处理结果</h2>
              <button onClick={handleDownload} className="btn btn-secondary">
                下载文本
              </button>
            </div>
            
            <div className="result-info">
              <div className="info-item">
                <span className="info-label">总页数:</span>
                <span className="info-value">{response.page_count}</span>
              </div>
              {response.total_usage && (
                <div className="info-item">
                  <span className="info-label">Token 使用:</span>
                  <span className="info-value">
                    {response.total_usage.total_tokens || 0} tokens
                    {' '}
                    (输入: {response.total_usage.input_tokens || 0}, 
                    输出: {response.total_usage.output_tokens || 0})
                  </span>
                </div>
              )}
            </div>

            <div className="result-content">
              <h3>完整文本内容</h3>
              <div className="text-content">
                {response.response.split('\n').map((line, idx) => (
                  <div key={idx}>{line || '\u00A0'}</div>
                ))}
              </div>
            </div>

            {response.page_descriptions.length > 0 && (
              <div className="result-content">
                <h3>分页内容</h3>
                {response.page_descriptions.map((desc, idx) => (
                  <div key={idx} className="page-description">
                    <h4>第 {idx + 1} 页</h4>
                    <div className="text-content">
                      {desc.split('\n').map((line, lineIdx) => (
                        <div key={lineIdx}>{line || '\u00A0'}</div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default PDFProcessor;

