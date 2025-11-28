from __future__ import annotations

"""
arXiv 搜索与下载服务封装。

从 lab/search_arxiv.py 抽取核心逻辑，提供可复用的 service API：
- search_and_download(keyword, outdir, max_results=10, recent_limit=3)
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
import re
import urllib.parse
import signal
import time

import arxiv  # type: ignore
import requests  # type: ignore
from bs4 import BeautifulSoup  # type: ignore
import asyncio
import aiohttp
import aiofiles
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.utils.logger import logger, setup_logger
from app.config.settings import settings, proxy_manager


ARXIV_LOGGER = setup_logger("arxiv_service")


class RateLimiter:
    """arXiv API 速率限制器"""
    
    def __init__(self, requests_per_second: float = 0.5):
        """
        Args:
            requests_per_second: 每秒允许的请求数（默认0.5，即2秒一次请求）
        """
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0
    
    async def wait_if_needed(self):
        """如果需要，等待到下次允许请求的时间"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            wait_time = self.min_interval - time_since_last
            ARXIV_LOGGER.info(f"速率限制：等待 {wait_time:.1f} 秒...")
            await asyncio.sleep(wait_time)
        
        self.last_request_time = time.time()


# 全局速率限制器实例
rate_limiter = RateLimiter(requests_per_second=0.5)  # 2秒一次请求


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# 默认代理设置（Clash 默认端口）
# 代理配置现在从 settings 中获取


def _sanitize_id(entry_id: str) -> str:
    """把 arXiv 条目 ID 转成可用作文件名的安全字符串。"""
    short_id = entry_id.rsplit("/", 1)[-1]
    return re.sub(r"[^0-9A-Za-z._-]", "-", short_id)


# 代理检测功能现在由 ProxyManager 处理


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type(arxiv.HTTPError),
    reraise=True
)
async def _search_arxiv_with_retry(search: arxiv.Search) -> List[arxiv.Result]:
    """
    带重试机制的 arXiv 搜索函数
    
    Args:
        search: arXiv 搜索对象
        
    Returns:
        搜索结果列表
        
    Raises:
        arxiv.HTTPError: 当所有重试都失败时
    """
    # 应用速率限制
    await rate_limiter.wait_if_needed()
    
    ARXIV_LOGGER.info(f"正在搜索 arXiv: {search.query}")
    
    try:
        client = arxiv.Client()
        results = list(client.results(search))
        ARXIV_LOGGER.info(f"搜索成功，返回 {len(results)} 条结果")
        return results
    except arxiv.HTTPError as e:
        if "429" in str(e):
            ARXIV_LOGGER.warning(f"遇到速率限制 (HTTP 429)，将重试...")
            # 额外等待时间
            await asyncio.sleep(10)
        raise


async def _download_pdf_async(entry, dirpath: str, filename: str, timeout: int = 300) -> bool:
    """
    异步下载 PDF 文件，使用全局代理管理器
    
    Args:
        entry: arxiv.Result 对象
        dirpath: 下载目录
        filename: 文件名
        timeout: 超时时间（秒）
    
    Returns:
        bool: 下载是否成功
    """
    # 构建PDF下载URL
    arxiv_id = entry.entry_id.split('/')[-1]  # 提取ID，如 "2504.00824v2"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    file_path = Path(dirpath) / filename
    
    # 检查文件是否已存在且完整
    if file_path.exists() and file_path.stat().st_size > 1024:  # 至少1KB
        ARXIV_LOGGER.info(f"  -> PDF文件已存在，跳过下载: {filename}")
        return True
    
    # 使用全局代理管理器检测代理可用性
    proxy_available = await proxy_manager.is_proxy_available()
    use_proxy = proxy_manager.get_proxy_url() if proxy_available else None
    
    if proxy_available:
        ARXIV_LOGGER.info(f"  -> ✓ 使用代理下载: {settings.proxy_url}")
    else:
        if settings.proxy_enabled:
            ARXIV_LOGGER.info(f"  -> ✗ 代理不可用，直接连接")
        else:
            ARXIV_LOGGER.info(f"  -> 直接连接（代理已禁用）")
    
    ARXIV_LOGGER.info(f"  -> 开始异步下载: {pdf_url}")
    start_time = time.time()
    
    try:
        # 设置请求头
        headers = {
            'User-Agent': 'Lynx/2.8.9rel.1 libwww-FM/2.14 SSL-MM/1.4.1'  # 使用简单的 User-Agent
        }
        
        # 创建连接器
        connector = aiohttp.TCPConnector(ssl=False) if use_proxy else None
        
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            async with session.get(
                pdf_url, 
                proxy=use_proxy,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status != 200:
                    ARXIV_LOGGER.error(f"  -> 下载失败，状态码: {response.status}")
                    return False
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                last_progress_log = 0
                
                ARXIV_LOGGER.info(f"  -> 文件大小: {total_size / (1024 * 1024):.1f}MB")
                
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        # 每下载10%显示一次进度
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            if progress - last_progress_log >= 10:
                                elapsed_now = time.time() - start_time
                                speed = (downloaded_size / (1024 * 1024)) / elapsed_now if elapsed_now > 0 else 0
                                ARXIV_LOGGER.info(f"  -> 下载进度: {progress:.0f}% ({downloaded_size / (1024 * 1024):.1f}MB/{total_size / (1024 * 1024):.1f}MB, {speed:.1f}MB/s)")
                                last_progress_log = progress
        
        elapsed = time.time() - start_time
        if file_path.exists():
            file_size = file_path.stat().st_size / (1024 * 1024)  # MB
            speed = file_size / elapsed if elapsed > 0 else 0
            ARXIV_LOGGER.info(f"  -> PDF下载耗时: {elapsed:.1f}秒 ({file_size:.1f}MB, {speed:.1f}MB/s)")
            return True
        else:
            ARXIV_LOGGER.error("  -> PDF下载失败：文件未创建")
            return False
            
    except asyncio.TimeoutError:
        ARXIV_LOGGER.error(f"  -> PDF下载超时 ({timeout}秒)")
        return False
    except Exception as e:
        ARXIV_LOGGER.error(f"  -> PDF下载异常: {e}")
        return False


def _download_pdf_with_timeout(entry, dirpath: str, filename: str, timeout: int = 60) -> bool:
    """
    使用 arxiv 库原生方法下载 PDF，带超时控制。
    
    Args:
        entry: arxiv.Result 对象
        dirpath: 下载目录
        filename: 文件名
        timeout: 超时时间（秒）
    
    Returns:
        bool: 下载是否成功
    """
    file_path = Path(dirpath) / filename
    
    # 检查文件是否已存在且完整
    if file_path.exists() and file_path.stat().st_size > 1024:  # 至少1KB
        ARXIV_LOGGER.info(f"  -> PDF文件已存在，跳过下载: {filename}")
        return True
    
    def timeout_handler(signum, frame):
        raise TimeoutError(f"PDF下载超时 ({timeout}秒)")
    
    try:
        start_time = time.time()
        ARXIV_LOGGER.info(f"  -> 使用 arxiv 库下载 PDF...")
        
        # 设置超时信号（仅在非Windows系统）
        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
        
        # 使用 arxiv 库的原生下载方法
        entry.download_pdf(dirpath=dirpath, filename=filename)
        
        elapsed = time.time() - start_time
        if file_path.exists():
            file_size = file_path.stat().st_size / (1024 * 1024)  # MB
            speed = file_size / elapsed if elapsed > 0 else 0
            ARXIV_LOGGER.info(f"  -> PDF下载耗时: {elapsed:.1f}秒 ({file_size:.1f}MB, {speed:.1f}MB/s)")
            return True
        else:
            ARXIV_LOGGER.error("  -> PDF下载失败：文件未创建")
            return False
            
    except TimeoutError as e:
        ARXIV_LOGGER.error(f"  -> {e}")
        return False
    except Exception as e:
        ARXIV_LOGGER.error(f"  -> PDF下载异常: {e}")
        return False
    finally:
        # 清除超时信号
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)


def _download_pdf_with_proxy(entry, dirpath: str, filename: str, timeout: int = 300) -> bool:
    """
    使用代理下载 PDF 的同步包装函数
    
    Args:
        entry: arxiv.Result 对象
        dirpath: 下载目录
        filename: 文件名
        timeout: 超时时间（秒）
    
    Returns:
        bool: 下载是否成功
    """
    try:
        # 检查是否已经有运行中的事件循环
        try:
            loop = asyncio.get_running_loop()
            # 如果有运行中的循环，使用 run_coroutine_threadsafe
            import concurrent.futures
            import threading
            
            def run_in_thread():
                # 在新线程中创建新的事件循环
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        _download_pdf_async(entry, dirpath, filename, timeout)
                    )
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result(timeout=timeout + 10)  # 额外10秒缓冲
                
        except RuntimeError:
            # 没有运行中的事件循环，可以直接使用 asyncio.run
            return asyncio.run(_download_pdf_async(entry, dirpath, filename, timeout))
            
    except Exception as e:
        ARXIV_LOGGER.error(f"  -> 异步下载失败: {e}")
        return False


def _generate_arxiv_bibtex(entry: arxiv.Result) -> str:
    """基于 arXiv entry 生成基本的 BibTeX 条目。"""
    safe_id = _sanitize_id(entry.entry_id)
    authors_str = " and ".join(getattr(a, "name", str(a)) for a in entry.authors or [])
    year = entry.published.year if entry.published else "????"
    month = entry.published.strftime("%b").lower() if entry.published else "jan"
    
    bibtex = f"""@article{{arxiv:{safe_id},
    title = {{{entry.title}}},
    author = {{{authors_str}}},
    year = {{{year}}},
    month = {{{month}}},
    eprint = {{{safe_id}}},
    archivePrefix = {{arXiv}},
    primaryClass = {{cs.AI}},
    url = {{https://arxiv.org/abs/{safe_id}}},
    note = {{arXiv preprint arXiv:{safe_id}}}
}}"""
    return bibtex


def _save_bibtex_text(entry_id: str, bibtex_text: str, target_dir: Path) -> Path:
    """把传入的 BibTeX 文本保存到目录中并返回路径。"""
    bib_path = target_dir / f"arxiv_{_sanitize_id(entry_id)}.bib"
    bib_path.write_text(bibtex_text, encoding="utf-8")
    return bib_path


def _extract_first_author(entry: arxiv.Result) -> str:
    """获取条目的第一作者姓名（若不存在则返回空字符串）。"""
    if not entry.authors:
        return ""
    first_author = entry.authors[0]
    return getattr(first_author, "name", str(first_author))


def _is_survey_paper(title: str, summary: str = "") -> bool:
    """
    判断是否为 survey 类型的论文。
    
    通过标题和摘要中的关键词来识别 survey 论文。
    """
    survey_keywords = [
        "survey", "review", "overview", "comprehensive study", 
        "systematic review", "literature review", "state of the art",
        "recent advances", "recent developments", "comprehensive analysis",
        "taxonomy", "categorization", "classification of"
    ]
    
    text_to_check = f"{title} {summary}".lower()
    
    for keyword in survey_keywords:
        if keyword in text_to_check:
            return True
    
    return False


def _search_dblp_bibtex(title: str, author: str, timeout: int = 30) -> Optional[str]:
    """在 DBLP 搜索匹配条目，找到则返回 BibTeX 文本。"""
    query = f"{title} {author}".strip()
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://dblp.org/search?q={encoded_query}"
    ARXIV_LOGGER.info("  -> DBLP 检索: %s", search_url)

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        ARXIV_LOGGER.error("  -> DBLP 搜索失败: %s", exc)
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    result_items = soup.select(".publ-list .entry")
    ARXIV_LOGGER.info("  -> DBLP 返回 %d 条候选", len(result_items))

    for item in result_items:
        bibtex_link = item.select_one('nav.publ a[href*="bibtex"]')
        if not bibtex_link:
            continue
        bibtex_url = urllib.parse.urljoin("https://dblp.org", bibtex_link["href"])
        ARXIV_LOGGER.info("  -> 获取 BibTeX: %s", bibtex_url)
        try:
            bibtex_resp = requests.get(bibtex_url, headers=HEADERS, timeout=timeout)
            bibtex_resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            ARXIV_LOGGER.error("  -> BibTeX 获取失败: %s", exc)
            continue

        bibtex_soup = BeautifulSoup(bibtex_resp.text, "html.parser")
        bibtex_content = bibtex_soup.select_one("#bibtex-section pre")
        if bibtex_content:
            bib_text = bibtex_content.text.strip()
            ARXIV_LOGGER.info("  -> 成功获取 BibTeX")
            return bib_text

    ARXIV_LOGGER.info("  -> 未找到可用的 DBLP BibTeX")
    return None


@dataclass
class ArxivPaperMetadata:
    keyword: str
    arxiv_id: str
    title: str
    authors: str
    published: Optional[datetime]
    bibtex_path: str
    pdf_path: str
    status: str = "ok"

    def to_manifest_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # datetime 转字符串，方便 JSON 序列化
        if isinstance(self.published, datetime):
            data["published"] = self.published.isoformat()
        else:
            data["published"] = None
        return data


async def search_and_download_async(
    keyword: str,
    outdir: Path,
    max_results: int = 10,
    recent_limit: int = 3,
    filter_surveys: bool = True,
    skip_dblp_check: bool = False,
) -> List[ArxivPaperMetadata]:
    """
    对单个 keyword 执行 arXiv 搜索 + DBLP 校验 + PDF/BibTeX 下载。

    Args:
        keyword: 搜索关键词
        outdir: 输出目录
        max_results: 最大搜索结果数
        recent_limit: 保留最近的论文数量
        filter_surveys: 是否过滤 survey 类型论文
        skip_dblp_check: 是否跳过 DBLP 检查（如果为 True，则不会检查 DBLP 匹配）

    Returns:
        通过 DBLP 校验且成功下载的论文元数据列表（如果 skip_dblp_check=True，则返回所有论文）。
    """
    outdir.mkdir(parents=True, exist_ok=True)
    ARXIV_LOGGER.info("开始查询关键词: %s (outdir=%s)", keyword, outdir)

    search = arxiv.Search(
        query=keyword,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
        sort_order=arxiv.SortOrder.Descending,
    )
    
    try:
        results = await _search_arxiv_with_retry(search)
    except arxiv.HTTPError as e:
        ARXIV_LOGGER.error(f"arXiv 搜索失败: {e}")
        return []

    if not results:
        ARXIV_LOGGER.info("未找到任何 arXiv 结果")
        return []

    ARXIV_LOGGER.info("共返回 %d 条候选", len(results))

    entries_with_dblp: list[tuple[arxiv.Result, str]] = []

    for entry in results:
        safe_id = _sanitize_id(entry.entry_id)
        ARXIV_LOGGER.info("处理条目 [%s] %s", safe_id, entry.title)
        
        # 过滤 survey 类型论文（如果启用）
        if filter_surveys and _is_survey_paper(entry.title, entry.summary or ""):
            ARXIV_LOGGER.info("  -> 检测到 survey 论文，跳过")
            continue
        
        first_author = _extract_first_author(entry)
        ARXIV_LOGGER.info("  -> 第一作者: %s", first_author or "未知")

        if skip_dblp_check:
            # 跳过 DBLP 检查，生成基于 arXiv 的基本 BibTeX
            ARXIV_LOGGER.info("  -> 跳过 DBLP 检查（skip_dblp_check=True），生成 arXiv BibTeX")
            dblp_bibtex = _generate_arxiv_bibtex(entry)
            entries_with_dblp.append((entry, dblp_bibtex))
        else:
            dblp_bibtex = _search_dblp_bibtex(entry.title, first_author)
            if not dblp_bibtex:
                ARXIV_LOGGER.info("  -> DBLP 未匹配，跳过下载")
                continue
            entries_with_dblp.append((entry, dblp_bibtex))

    if not entries_with_dblp:
        ARXIV_LOGGER.info("没有通过 DBLP 校验的条目")
        return []

    # 仅保留最近 N 条
    if recent_limit and recent_limit > 0:
        entries_with_dblp = sorted(
            entries_with_dblp,
            key=lambda item: item[0].published or datetime.min,
            reverse=True,
        )[:recent_limit]
        ARXIV_LOGGER.info("仅保留最近 %d 条条目用于后续处理", len(entries_with_dblp))

    results_meta: List[ArxivPaperMetadata] = []

    for i, (entry, dblp_bibtex) in enumerate(entries_with_dblp, 1):
        safe_id = _sanitize_id(entry.entry_id)
        paper_dir = outdir / safe_id
        paper_dir.mkdir(parents=True, exist_ok=True)

        ARXIV_LOGGER.info("开始下载第 %d/%d 篇论文: %s", i, len(entries_with_dblp), entry.title)
        pdf_path = paper_dir / f"arxiv_{safe_id}.pdf"

        ARXIV_LOGGER.info("  -> 正在下载 PDF...")
        # 首先尝试使用代理下载（异步方式，更快更稳定）
        download_success = _download_pdf_with_proxy(
            entry, 
            str(paper_dir), 
            pdf_path.name, 
            timeout=300  # 5分钟超时
        )
        
        # 如果代理下载失败，回退到原生方法
        if not download_success:
            ARXIV_LOGGER.warning("  -> 代理下载失败，尝试原生下载方法...")
            download_success = _download_pdf_with_timeout(entry, str(paper_dir), pdf_path.name, timeout=120)
        
        if not download_success:
            ARXIV_LOGGER.error("  -> PDF 下载失败，跳过此论文")
            continue
        ARXIV_LOGGER.info("  -> PDF 下载成功: %s", pdf_path)

        try:
            ARXIV_LOGGER.info("  -> 正在保存 BibTeX...")
            bib_path = _save_bibtex_text(entry.entry_id, dblp_bibtex, paper_dir)
            if skip_dblp_check:
                ARXIV_LOGGER.info("  -> arXiv BibTeX 已保存到 `%s`", bib_path.name)
            else:
                ARXIV_LOGGER.info("  -> DBLP BibTeX 已保存到 `%s`", bib_path.name)
        except Exception as exc:  # noqa: BLE001
            ARXIV_LOGGER.error("  -> BibTeX 保存失败: %s", exc)
            continue

        authors_str = ", ".join(getattr(a, "name", str(a)) for a in entry.authors or [])

        meta = ArxivPaperMetadata(
            keyword=keyword,
            arxiv_id=_sanitize_id(entry.entry_id),
            title=entry.title,
            authors=authors_str,
            published=entry.published,
            bibtex_path=str(bib_path),
            pdf_path=str(pdf_path),
            status="ok",
        )
        results_meta.append(meta)
        ARXIV_LOGGER.info("  -> 论文处理完成: %s", entry.title)

    ARXIV_LOGGER.info("所有论文处理完成，共成功下载 %d 篇", len(results_meta))
    return results_meta


def search_and_download(
    keyword: str,
    outdir: Path,
    max_results: int = 10,
    recent_limit: int = 3,
    filter_surveys: bool = True,
    skip_dblp_check: bool = False,
) -> List[ArxivPaperMetadata]:
    """
    同步版本的搜索和下载函数（向后兼容）
    
    Args:
        keyword: 搜索关键词
        outdir: 输出目录
        max_results: 最大搜索结果数
        recent_limit: 保留最近的论文数量
        filter_surveys: 是否过滤 survey 类型论文
        skip_dblp_check: 是否跳过 DBLP 检查（如果为 True，则不会检查 DBLP 匹配）

    Returns:
        通过 DBLP 校验且成功下载的论文元数据列表（如果 skip_dblp_check=True，则返回所有论文）。
    """
    try:
        # 检查是否在事件循环中
        loop = asyncio.get_running_loop()
        # 如果在事件循环中，使用线程池执行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                search_and_download_async(keyword, outdir, max_results, recent_limit, filter_surveys, skip_dblp_check)
            )
            return future.result()
    except RuntimeError:
        # 没有运行中的事件循环，直接运行
        return asyncio.run(
            search_and_download_async(keyword, outdir, max_results, recent_limit, filter_surveys, skip_dblp_check)
        )


