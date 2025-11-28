import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from typing import Optional
import time


class ArxivPDFLoader:
    """异步加载 arXiv PDF 文件"""

    # 只使用官方源
    OFFICIAL_URL = "https://arxiv.org/pdf/"

    def __init__(self, pdf_url: str, save_dir: str = "./downloads", proxy: str = None, auto_detect_proxy: bool = True):
        self.pdf_url = pdf_url
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = proxy  # 代理地址，例如 "http://127.0.0.1:7890"
        self.auto_detect_proxy = auto_detect_proxy  # 是否自动检测代理可用性

    async def check_proxy(self) -> bool:
        """
        检测代理是否可用

        Returns:
            bool: True 表示代理可用，False 表示不可用
        """
        if not self.proxy:
            return False

        print(f"正在检测代理: {self.proxy} ...")

        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                # 测试连接到 arxiv.org
                async with session.get(
                        "https://arxiv.org",
                        proxy=self.proxy,
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        print(f"✓ 代理可用")
                        return True
                    else:
                        print(f"✗ 代理返回状态码: {response.status}")
                        return False
        except asyncio.TimeoutError:
            print(f"✗ 代理连接超时")
            return False
        except Exception as e:
            print(f"✗ 代理不可用: {e}")
            return False

    async def download_pdf(self, filename: Optional[str] = None, user_agent: str = None) -> Path:
        """
        异步下载 PDF 文件

        Args:
            filename: 保存的文件名，如果为 None 则从 URL 提取
            user_agent: 自定义 User-Agent，例如 'Lynx' 或 'Mozilla/5.0'

        Returns:
            Path: 保存的文件路径
        """
        if filename is None:
            filename = self.pdf_url.split('/')[-1] + '.pdf'

        filepath = self.save_dir / filename

        # 设置请求头
        headers = {}
        if user_agent:
            headers['User-Agent'] = user_agent
            print(f"使用 User-Agent: {user_agent}")

        # 检测代理是否可用
        use_proxy = None
        if self.auto_detect_proxy and self.proxy:
            proxy_available = await self.check_proxy()
            if proxy_available:
                use_proxy = self.proxy
                print(f"将通过代理下载")
            else:
                print(f"代理不可用，将直接连接")
        elif self.proxy and not self.auto_detect_proxy:
            use_proxy = self.proxy
            print(f"使用代理: {use_proxy}")
        else:
            print(f"直接连接（不使用代理）")

        print(f"\n开始下载: {self.pdf_url}")
        start_time = time.time()

        try:
            # 创建连接器，配置代理
            connector = aiohttp.TCPConnector(ssl=False) if use_proxy else None
            async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
                async with session.get(self.pdf_url, proxy=use_proxy,
                                       timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        raise Exception(f"下载失败，状态码: {response.status}")

                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0

                    async with aiofiles.open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded_size += len(chunk)

                            # 显示下载进度（以 KB 为单位）
                            downloaded_kb = downloaded_size / 1024
                            total_kb = total_size / 1024
                            if total_size > 0:
                                progress = (downloaded_size / total_size) * 100
                                print(f"\r下载进度: {progress:.1f}% ({downloaded_kb:.1f} KB / {total_kb:.1f} KB)",
                                      end='', flush=True)

            elapsed_time = time.time() - start_time
            file_size_mb = filepath.stat().st_size / (1024 * 1024)

            print(f"\n✓ 下载完成!")
            print(f"  文件路径: {filepath}")
            print(f"  文件大小: {file_size_mb:.2f} MB")
            print(f"  耗时: {elapsed_time:.2f} 秒")
            print(f"  下载速度: {file_size_mb / elapsed_time:.2f} MB/s")

            return filepath

        except Exception as e:
            print(f"\n✗ 下载失败: {e}")
            raise

    async def get_metadata(self) -> dict:
        """
        异步获取 PDF 元数据

        Returns:
            dict: 包含文件大小、内容类型等信息
        """
        async with aiohttp.ClientSession() as session:
            async with session.head(self.pdf_url) as response:
                return {
                    'status': response.status,
                    'content_type': response.headers.get('content-type'),
                    'content_length': int(response.headers.get('content-length', 0)),
                    'content_length_mb': int(response.headers.get('content-length', 0)) / (1024 * 1024)
                }


async def main():
    """主函数"""
    # arXiv PDF URL
    pdf_url = "https://arxiv.org/pdf/2504.00824v2"

    # Clash 代理设置
    proxy = "http://127.0.0.1:7890"  # Clash 默认端口

    # 创建加载器实例
    # auto_detect_proxy=True: 自动检测代理是否可用，不可用则直接连接
    # auto_detect_proxy=False: 强制使用代理（不检测）
    loader = ArxivPDFLoader(
        pdf_url,
        proxy=proxy,
        auto_detect_proxy=True  # 自动检测代理
    )

    # 下载 PDF
    filepath = await loader.download_pdf("arxiv_2504.00824v2.pdf", user_agent="Lynx")

    return filepath


async def download_with_proxy(pdf_url: str, filename: str = None, proxy: str = "http://127.0.0.1:7890",
                              auto_detect: bool = True):
    """
    通过 Clash 代理下载（自动检测代理可用性）

    Args:
        pdf_url: PDF 的 URL
        filename: 保存的文件名
        proxy: 代理地址，默认 Clash 的 7890 端口
        auto_detect: 是否自动检测代理可用性
    """
    loader = ArxivPDFLoader(pdf_url, proxy=proxy, auto_detect_proxy=auto_detect)
    return await loader.download_pdf(filename, user_agent="Lynx")


async def batch_download(urls: list[str], proxy: str = "http://127.0.0.1:7890", auto_detect: bool = True):
    """
    批量异步下载多个 PDF 文件

    Args:
        urls: PDF URL 列表
        proxy: 代理地址
        auto_detect: 是否自动检测代理
    """
    tasks = []
    for i, url in enumerate(urls):
        loader = ArxivPDFLoader(url, proxy=proxy, auto_detect_proxy=auto_detect)
        filename = f"paper_{i + 1}.pdf"
        tasks.append(loader.download_pdf(filename))

    # 并发执行所有下载任务
    results = await asyncio.gather(*tasks, return_exceptions=True)

    print("\n批量下载完成:")
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  文件 {i + 1}: 失败 - {result}")
        else:
            print(f"  文件 {i + 1}: 成功 - {result}")


if __name__ == "__main__":
    # 运行单个下载（自动检测代理）
    asyncio.run(main())

    # 其他使用示例：

    # 1. 强制使用代理（不检测）
    # asyncio.run(download_with_proxy(
    #     "https://arxiv.org/pdf/1911.05722.pdf",
    #     "paper.pdf",
    #     auto_detect=False
    # ))

    # 2. 不使用代理（直接连接）
    # asyncio.run(download_with_proxy(
    #     "https://arxiv.org/pdf/1911.05722.pdf",
    #     "paper.pdf",
    #     proxy=None
    # ))