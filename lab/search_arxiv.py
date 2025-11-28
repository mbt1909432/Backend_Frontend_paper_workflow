"""按关键词搜索 arXiv，再通过 DBLP 过滤后下载 PDF + BibTeX 的脚本。

流程：
1. 修改下方 `SETTINGS`（关键词、最大结果数、排序方式、输出目录等）。
2. 如需只保留按提交时间最近的若干条，把 `recent_limit` 设为对应数量。
3. 运行 `python lab/search_arxiv.py`。
4. 先 `pip install arxiv requests beautifulsoup4`。
5. 管道：查询 -> 获取 arXiv 条目 -> DBLP 校验 -> 仅对命中条目下载。
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import arxiv
import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger("arxiv_dblp_pipeline")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}


def sanitize_id(entry_id: str) -> str:
    """把 arXiv 条目 ID 转成可用作文件名的安全字符串。"""
    short_id = entry_id.rsplit("/", 1)[-1]
    # Keep alphanumerics, dash, underscore, dot, and replace the rest with dash.
    return re.sub(r"[^0-9A-Za-z._-]", "-", short_id)


def save_bibtex_text(entry_id: str, bibtex_text: str, target_dir: Path) -> Path:
    """把传入的 BibTeX 文本保存到目录中并返回路径。"""
    bib_path = target_dir / f"{sanitize_id(entry_id)}.bib"
    bib_path.write_text(bibtex_text, encoding="utf-8")
    return bib_path


def process_entry(entry: arxiv.Result, output_dir: Path, dblp_bibtex: str) -> None:
    """处理单条搜索结果：下载 arXiv PDF 并存储 DBLP BibTeX。"""
    safe_id = sanitize_id(entry.entry_id)
    paper_dir = output_dir / safe_id
    paper_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("  -> 创建目录 `%s`", paper_dir)

    try:
        entry.download_pdf(dirpath=str(paper_dir), filename=f"{safe_id}.pdf")
        LOGGER.info("  -> PDF 下载成功")
    except Exception as exc:  # noqa: BLE001 - surface download issues
        LOGGER.error("  -> PDF 下载失败: %s", exc)
        return

    try:
        bib_path = save_bibtex_text(entry.entry_id, dblp_bibtex, paper_dir)
        LOGGER.info("  -> DBLP BibTeX 已保存到 `%s`", bib_path.name)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("  -> BibTeX 保存失败: %s", exc)


def extract_first_author(entry: arxiv.Result) -> str:
    """获取条目的第一作者姓名（若不存在则返回空字符串）。"""
    if not entry.authors:
        return ""
    first_author = entry.authors[0]
    return getattr(first_author, "name", str(first_author))


def search_dblp_bibtex(title: str, author: str, timeout: int = 30) -> str | None:
    """在 DBLP 搜索匹配条目，找到则返回 BibTeX 文本。"""
    query = f"{title} {author}".strip()
    encoded_query = urllib.parse.quote_plus(query)
    search_url = f"https://dblp.org/search?q={encoded_query}"
    LOGGER.info("  -> DBLP 检索: %s", search_url)

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("  -> DBLP 搜索失败: %s", exc)
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    result_items = soup.select(".publ-list .entry")
    LOGGER.info("  -> DBLP 返回 %d 条候选", len(result_items))

    for item in result_items:
        bibtex_link = item.select_one('nav.publ a[href*="bibtex"]')
        if not bibtex_link:
            continue
        bibtex_url = urllib.parse.urljoin("https://dblp.org", bibtex_link["href"])
        LOGGER.info("  -> 获取 BibTeX: %s", bibtex_url)
        try:
            bibtex_resp = requests.get(bibtex_url, headers=HEADERS, timeout=timeout)
            bibtex_resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("  -> BibTeX 获取失败: %s", exc)
            continue

        bibtex_soup = BeautifulSoup(bibtex_resp.text, "html.parser")
        bibtex_content = bibtex_soup.select_one("#bibtex-section pre")
        if bibtex_content:
            bib_text = bibtex_content.text.strip()
            LOGGER.info("  -> 成功获取 BibTeX，准备下载")
            return bib_text

    LOGGER.info("  -> 未找到可用的 DBLP BibTeX")
    return None


class SortOption(Enum):
    """arXiv 查询可选排序，按官方 API 的排序字段 + 顺序封装。"""

    RELEVANCE = (arxiv.SortCriterion.Relevance, arxiv.SortOrder.Descending)
    NEWEST_FIRST = (arxiv.SortCriterion.SubmittedDate, arxiv.SortOrder.Descending)
    OLDEST_FIRST = (arxiv.SortCriterion.SubmittedDate, arxiv.SortOrder.Ascending)

    @property
    def criterion(self) -> arxiv.SortCriterion:
        return self.value[0]

    @property
    def order(self) -> arxiv.SortOrder:
        return self.value[1]


@dataclass
class SearchSettings:
    """脚本参数：关键词、最多下载几条、输出目录、排序方式等。"""

    query: str
    max_results: int = 5
    outdir: Path = Path("lab_downloads")
    sort_option: SortOption = SortOption.RELEVANCE
    recent_limit: int | None = None  # 仅保留最近的 N 条（按提交时间降序）


# 可在此处修改默认参数，运行脚本即按最新设置执行。
SETTINGS = SearchSettings(
    query="rag",
    max_results=10,
    outdir=Path("lab_downloads"),
    sort_option=SortOption.RELEVANCE,
    recent_limit=3,
)


def main(settings: SearchSettings = SETTINGS) -> None:
    """主流程：根据设置执行 arXiv 搜索，然后逐条下载。"""
    if not settings.query.strip():
        raise ValueError("Please set SETTINGS.query before running the script.")

    settings.outdir.mkdir(parents=True, exist_ok=True)
    LOGGER.info("开始查询关键词: %s", settings.query)

    search = arxiv.Search(
        query=settings.query,
        max_results=settings.max_results,
        sort_by=settings.sort_option.criterion,
        sort_order=settings.sort_option.order,
    )
    client = arxiv.Client()
    results = list(client.results(search))

    if not results:
        LOGGER.info("未找到任何 arXiv 结果")
        return

    LOGGER.info("共返回 %d 条候选，输出目录为 `%s`", len(results), settings.outdir)

    entries_with_dblp: list[tuple[arxiv.Result, str]] = []

    for entry in results:
        safe_id = sanitize_id(entry.entry_id)
        LOGGER.info("处理条目 [%s] %s", safe_id, entry.title)
        first_author = extract_first_author(entry)
        LOGGER.info("  -> 第一作者: %s", first_author or "未知")

        dblp_bibtex = search_dblp_bibtex(entry.title, first_author)
        if not dblp_bibtex:
            LOGGER.info("  -> DBLP 未匹配，跳过下载")
            continue

        entries_with_dblp.append((entry, dblp_bibtex))

    if not entries_with_dblp:
        LOGGER.info("没有通过 DBLP 校验的条目")
        return

    if settings.recent_limit and settings.recent_limit > 0:
        entries_with_dblp = sorted(
            entries_with_dblp,
            key=lambda item: item[0].published or datetime.min,
            reverse=True,
        )[: settings.recent_limit]
        LOGGER.info("仅保留最近 %d 条条目用于后续处理", len(entries_with_dblp))

    for entry, dblp_bibtex in entries_with_dblp:
        process_entry(entry, settings.outdir, dblp_bibtex)


if __name__ == "__main__":
    main()


