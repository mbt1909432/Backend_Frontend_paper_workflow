"""
PDF 转 PNG 工具函数
使用 PyMuPDF (fitz) 和 PIL 将 PDF 文件转换为 PNG 图片
"""
import os
from pathlib import Path
from typing import List, Optional
import fitz  # PyMuPDF
from PIL import Image
from app.utils.logger import logger


def pdf_to_pngs(
    pdf_path: str,
    output_dir: Optional[str] = None,
    dpi: int = 300
) -> List[str]:
    """
    将 PDF 文件的所有页面转换为 PNG 图片
    
    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录，如果为 None，则在 PDF 同目录下创建新文件夹
        dpi: 输出图片的 DPI（分辨率），默认 300
        
    Returns:
        PNG 文件路径列表
    """
    try:
        # 确保 PDF 文件存在
        if not os.path.exists(pdf_path):
            logger.error(f"PDF file not found: {pdf_path}")
            return []
        
        # 获取 PDF 文件名（不含扩展名）
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # 确定输出目录
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(pdf_path), f"{pdf_name}_pngs")
        
        # 创建输出目录（如果它不存在）
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logger.info(f"Created output directory: {output_dir}")
        
        # 打开 PDF 文档
        pdf_document = fitz.open(pdf_path)
        output_paths = []
        
        # 循环遍历 PDF 的所有页面
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            
            # 生成指定 DPI 的像素图
            pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
            
            # 将像素图转换为 Pillow 图像
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            
            # 生成输出文件名，例如：my_doc_page_1.png
            output_filename = f"{pdf_name}_page_{page_num + 1}.png"
            output_path = os.path.join(output_dir, output_filename)
            
            # 保存图片
            image.save(output_path, "PNG")
            output_paths.append(output_path)
            
            # 清理资源
            image.close()
            pixmap = None
            
            logger.info(f"Converted page {page_num + 1} to {output_filename}")
        
        # 关闭 PDF 文档
        pdf_document.close()
        
        logger.info(f"Successfully converted {len(output_paths)} pages to PNG files")
        return output_paths
        
    except Exception as e:
        logger.error(f"Error converting PDF to PNGs: {str(e)}")
        return []

