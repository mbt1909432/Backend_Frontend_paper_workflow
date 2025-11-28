#!/usr/bin/env python3
"""
测试修复后的 arXiv 下载功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.services.arxiv_service import search_and_download

def test_download():
    """测试下载功能"""
    print("开始测试 arXiv 下载功能...")
    
    # 创建测试输出目录
    test_outdir = Path("test_output")
    test_outdir.mkdir(exist_ok=True)
    
    try:
        # 测试搜索和下载
        results = search_and_download(
            keyword="large language models academic writing support",
            outdir=test_outdir,
            max_results=5,
            recent_limit=2,
            filter_surveys=True,
        )
        
        print(f"\n测试完成！成功下载 {len(results)} 篇论文")
        
        for i, paper in enumerate(results, 1):
            print(f"{i}. {paper.title}")
            print(f"   作者: {paper.authors}")
            print(f"   PDF: {paper.pdf_path}")
            print(f"   BibTeX: {paper.bibtex_path}")
            print()
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_download()
