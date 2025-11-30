import os
import re
import json
import time
import asyncio
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from openai import AsyncOpenAI


# 统一的请求头与代理配置
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/91.0.4472.124 Safari/537.36')
}


def build_proxies(use_proxy: bool):
    """根据配置返回代理字典"""
    if not use_proxy:
        return None
    return {
        'http': 'http://127.0.0.1:7890',
        'https': 'http://127.0.0.1:7890'
    }


def scrape_arxiv_page(url, use_proxy=True):
    """
    爬取单个页面的论文

    Args:
        url: arXiv 页面 URL
        use_proxy: 是否使用代理（默认 True）

    Returns:
        包含论文数据的字典
    """
    # 设置请求头，模拟浏览器
    proxies = build_proxies(use_proxy)

    try:
        # 发送请求
        if use_proxy:
            print(f"正在通过代理访问: {url}")
        else:
            print(f"正在直接访问: {url}")

        response = requests.get(url, headers=HEADERS, proxies=proxies, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'

        # 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # 存储所有论文
        papers = []

        # 找到所有论文条目
        # 每篇论文在一个 <dt> 和 <dd> 标签对中
        dt_tags = soup.find_all('dt')
        dd_tags = soup.find_all('dd')

        print(f"  本页找到 {len(dt_tags)} 篇论文")

        for dt, dd in zip(dt_tags, dd_tags):
            paper = {}

            # 提取 arXiv ID
            arxiv_link = dt.find('a', title='Abstract')
            if arxiv_link:
                paper['arxiv_id'] = arxiv_link.text.strip()
                paper['arxiv_url'] = 'https://arxiv.org/abs/' + paper['arxiv_id']

            # 提取 PDF、HTML、other 链接
            pdf_link = dt.find('a', title='Download PDF')
            if pdf_link:
                paper['pdf_url'] = 'https://arxiv.org' + pdf_link['href']

            # 提取标题
            title_tag = dd.find('div', class_='list-title')
            if title_tag:
                paper['title'] = title_tag.text.replace('Title:', '').strip()

            # 提取作者
            authors_tag = dd.find('div', class_='list-authors')
            if authors_tag:
                authors = []
                for author in authors_tag.find_all('a'):
                    authors.append(author.text.strip())
                paper['authors'] = authors

            # 提取主题分类
            subjects_tag = dd.find('div', class_='list-subjects')
            if subjects_tag:
                paper['subjects'] = subjects_tag.text.replace('Subjects:', '').strip()

            # 提取评论（如果有）
            comments_tag = dd.find('div', class_='list-comments')
            if comments_tag:
                paper['comments'] = comments_tag.text.replace('Comments:', '').strip()

            # 提取摘要链接指向的 Journal-ref（如果有）
            journal_tag = dd.find('div', class_='list-journal-ref')
            if journal_tag:
                paper['journal_ref'] = journal_tag.text.replace('Journal-ref:', '').strip()

            papers.append(paper)

        # 提取日期信息
        h3_tags = soup.find_all('h3')
        date_info = {}
        if h3_tags:
            date_text = h3_tags[0].text.strip()
            date_info['scrape_date'] = date_text

        return {
            'date_info': date_info,
            'papers': papers
        }

    except requests.exceptions.RequestException as e:
        print(f"  请求错误: {e}")
        return None
    except Exception as e:
        print(f"  解析错误: {e}")
        return None


def fetch_paper_detail(arxiv_url, use_proxy=True):
    """
    访问单篇论文页面，提取标题与摘要等详情
    """
    proxies = build_proxies(use_proxy)

    try:
        response = requests.get(arxiv_url, headers=HEADERS, proxies=proxies, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        details = {}

        title_tag = soup.find('h1', class_='title mathjax') or soup.find('h1', class_='title')
        if title_tag:
            details['detail_title'] = title_tag.text.replace('Title:', '').strip()

        abstract_tag = soup.find('blockquote', class_='abstract mathjax') or soup.find('blockquote', class_='abstract')
        if abstract_tag:
            details['abstract'] = abstract_tag.text.replace('Abstract:', '').strip()

        date_tag = soup.find('div', class_='dateline')
        if date_tag:
            details['detail_dateline'] = date_tag.text.strip()

        details['detail_fetched_at'] = datetime.utcnow().isoformat()

        return details

    except requests.exceptions.RequestException as e:
        print(f"  详情页请求错误 ({arxiv_url}): {e}")
        return None
    except Exception as e:
        print(f"  详情页解析错误 ({arxiv_url}): {e}")
        return None


def load_existing_data(filename):
    """读取已存在的 JSON 数据，便于去重"""
    if not filename or not os.path.exists(filename):
        return None

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"警告: {filename} 不是有效的 JSON，忽略已有数据")
        return None
    except Exception as exc:
        print(f"读取 {filename} 失败: {exc}")
        return None


JSON_BLOCK_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def build_summary_prompt(title: str, abstract: str) -> str:
    """构建给 LLM 的摘要提示词"""
    return (
        "As a top-tier AI writing expert, please summarize the most critical "
        "and fundamental AI algorithms based on the content below.\n\n"
        f"Title: {title}\n"
        f"Abstract: {abstract}\n\n"
        "Output 3-5 short technical phrases (≤8 words) exactly like:\n"
        "1. Multi-Agent Reinforcement Learning (MARL)\n"
        "2. Multi-Objective Bayesian Optimization\n"
        "3. Bayesian Networks & Uncertainty Quantification\n"
        "4. Transformer-based Scenario Generator\n"
        "These phrases should capture objectives, core methods, or fundamental "
        "contributions; keep them in the same numbered style.\n\n"
        "Respond ONLY with a JSON object wrapped inside a ```json code fence, "
        "using this schema:\n"
        "{\n"
        '  "summary_points": [\n'
        '    "Multi-Agent Reinforcement Learning (MARL)",\n'
        '    "Multi-Objective Bayesian Optimization",\n'
        '    "Bayesian Networks & Uncertainty Quantification"\n'
        "  ]\n"
        "}\n"
        "Do not include any other text. The value of summary_points must be a "
        "JSON list, not a quoted string."
    )


def extract_json_from_response(text: str):
    """从 LLM 返回文本中提取 JSON 对象"""
    if not text:
        return None
    match = JSON_BLOCK_PATTERN.search(text)
    if not match:
        return None
    json_str = match.group(1).strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def load_local_env(env_filename='.env'):
    """Load environment variables from a .env file in this directory."""
    env_path = Path(__file__).resolve().parent / env_filename
    if not env_path.exists():
        return

    with env_path.open('r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()


async def summarize_papers_with_llm(papers,
                                    model=None,
                                    temperature=0.3,
                                    max_tokens=512,
                                    sleep_time=0,
                                    concurrency=5):
    """
    使用 LLM 对新增论文生成摘要（异步并发版本）
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("未检测到 OPENAI_API_KEY，跳过 LLM 摘要生成")
        return

    client_kwargs = {'api_key': api_key}
    base_url = os.getenv('OPENAI_BASE_URL') or os.getenv('OPENAI_API_BASE')
    if base_url:
        client_kwargs['base_url'] = base_url

    client = AsyncOpenAI(**client_kwargs)
    default_model = model or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    semaphore = asyncio.Semaphore(max(concurrency, 1))
    total = len(papers)

    async def summarize_single(idx, paper):
        title = paper.get('detail_title') or paper.get('title')
        abstract = paper.get('abstract')

        if not title or not abstract:
            print(f"  [{idx}] 标题或摘要缺失，跳过 LLM 摘要")
            return

        prompt = build_summary_prompt(title, abstract)
        print(f"  [{idx}/{total}] 生成 LLM 摘要 ({title[:50]}...)")

        async with semaphore:
            try:
                response = await client.chat.completions.create(
                    model=default_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                summary_text = response.choices[0].message.content.strip()
                structured = extract_json_from_response(summary_text)
                summary_points = structured.get('summary_points') if structured else None
                if isinstance(summary_points, list) and summary_points:
                    paper['ai_summary_structured'] = summary_points
                    paper['algorithm_phrase'] = summary_points
                else:
                    paper['algorithm_phrase'] = summary_text
            except Exception as exc:
                print(f"    摘要生成失败: {exc}")

            if sleep_time:
                await asyncio.sleep(sleep_time)

    await asyncio.gather(*(summarize_single(idx, paper) for idx, paper in enumerate(papers, 1)))


def build_hot_phrase_prompt(phrases, target_count=10):
    """构建热门算法短语提炼 Prompt"""
    preview = "\n".join(f"{idx + 1}. {phrase}" for idx, phrase in enumerate(phrases))
    return (
        "You are a trend analyst for cutting-edge AI research.\n"
        "You will receive a deduplicated list of algorithm phrases extracted from "
        "recent arXiv cs.AI papers. Identify the hottest, most representative directions "
        "that capture where attention converges right now.\n\n"
        "Input phrases:\n"
        f"{preview}\n\n"
        "Output between 10 and 20 concise phrases (≤8 words) using the same style as the "
        "input, sorted from hottest to less hot. Prefer merging near-duplicates and "
        "emphasize technical specificity.\n"
        "Respond ONLY with a JSON object wrapped in ```json code fences:\n"
        "{\n"
        '  "hot_phrases": [\n'
        '    "Multi-Agent Reinforcement Learning (MARL)",\n'
        '    "Graph Neural PDE Solvers",\n'
        '    "End-to-End Generative Planners"\n'
        "  ]\n"
        "}\n"
        "Do not include any commentary."
    )


async def aggregate_trending_phrases_with_llm(phrases,
                                              model=None,
                                              temperature=0.2,
                                              max_tokens=512,
                                              top_k=10):
    """调用 LLM 聚合热门算法短语"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("未检测到 OPENAI_API_KEY，跳过热门算法聚合")
        return None

    if not phrases:
        print("没有可供聚合的 algorithm_phrase 数据")
        return None

    client_kwargs = {'api_key': api_key}
    base_url = os.getenv('OPENAI_BASE_URL') or os.getenv('OPENAI_API_BASE')
    if base_url:
        client_kwargs['base_url'] = base_url

    client = AsyncOpenAI(**client_kwargs)
    default_model = model or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    target_count = max(10, min(top_k or 10, 20))
    prompt = build_hot_phrase_prompt(phrases[:200], target_count=target_count)

    try:
        response = await client.chat.completions.create(
            model=default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        content = response.choices[0].message.content.strip()
        structured = extract_json_from_response(content)
        hot_list = structured.get('hot_phrases') if structured else None
        if isinstance(hot_list, list) and hot_list:
            return hot_list[:target_count]
        print("热门算法聚合返回无法解析的 JSON，退回原始内容")
        return content
    except Exception as exc:
        print(f"热门算法聚合失败: {exc}")
        return None
    finally:
        await client.close()


class ArxivCrawler:
    """
    面向 arXiv cs.AI 分类的可配置抓取器，负责分页抓取、去重、详情补全与可选 LLM 摘要。

    Args mirror `scrape_arxiv_cs_ai` 的各项参数。
    """

    def __init__(self,
                 base_url='https://arxiv.org/list/cs.AI/recent',
                       max_papers=300,
                       papers_per_page=50,
                       use_proxy=True,
                 sleep_time=2,
                 fetch_details=True,
                 detail_sleep=1,
                 existing_data_path='arxiv_papers.json',
                 summarize_new=False,
                 summary_model=None,
                 summary_temperature=0.3,
                 summary_max_tokens=512,
                 summary_sleep=0,
                 summary_concurrency=5,
                 aggregate_hot=True,
                 hot_model=None,
                 hot_temperature=0.2,
                 hot_max_tokens=512,
                 hot_top_k=10):
        self.base_url = base_url
        self.max_papers = max_papers
        self.papers_per_page = papers_per_page
        self.use_proxy = use_proxy
        self.sleep_time = sleep_time
        self.fetch_details = fetch_details
        self.detail_sleep = detail_sleep
        self.existing_data_path = existing_data_path
        self.summarize_new = summarize_new
        self.summary_model = summary_model
        self.summary_temperature = summary_temperature
        self.summary_max_tokens = summary_max_tokens
        self.summary_sleep = summary_sleep
        self.summary_concurrency = summary_concurrency
        self.aggregate_hot = aggregate_hot
        self.hot_model = hot_model
        self.hot_temperature = hot_temperature
        self.hot_max_tokens = hot_max_tokens
        self.hot_top_k = hot_top_k

        self.all_papers = []
        self.processed_count = 0
        self.date_info = {}
        self.existing_data = None
        self.existing_papers = []
        self.seen_ids = set()
        self.hot_phrases = None

    def _initialize_existing_data(self):
        self.existing_data = load_existing_data(self.existing_data_path)
        if self.existing_data:
            print(f"已加载已有数据文件: {self.existing_data_path} "
                  f"(记录 {len(self.existing_data.get('papers', []))} 篇论文)")
        else:
            if self.existing_data_path and os.path.exists(self.existing_data_path):
                print(f"警告: {self.existing_data_path} 加载失败，视为无历史数据")
            else:
                print(f"未找到已有数据文件: {self.existing_data_path}，将全量爬取")

        self.existing_papers = self.existing_data.get('papers', []) if self.existing_data else []
        existing_ids = {p.get('arxiv_id') for p in self.existing_papers if p.get('arxiv_id')}
        self.seen_ids = set(existing_ids)

    def _build_page_url(self, page_index):
        if page_index == 0:
            return self.base_url
        skip = page_index * self.papers_per_page
        return f"{self.base_url}?skip={skip}&show={self.papers_per_page}"

    def _handle_page(self, page_index, num_pages):
        print(f"\n[第 {page_index + 1}/{num_pages} 页]")
        url = self._build_page_url(page_index)
        page_data = scrape_arxiv_page(url, self.use_proxy)

        if not page_data or not page_data['papers']:
            print(f"  第 {page_index + 1} 页爬取失败，跳过")
            return False

        if page_index == 0:
            self.date_info = page_data['date_info']

        for paper in page_data['papers']:
            if self.processed_count >= self.max_papers:
                break
            self.processed_count += 1

            arxiv_id = paper.get('arxiv_id')
            if not arxiv_id:
                continue
            if arxiv_id in self.seen_ids:
                print(f"  跳过已有论文: {arxiv_id}")
                continue
            self.seen_ids.add(arxiv_id)
            self.all_papers.append(paper)

        print(f"  已累计爬取: {len(self.all_papers)} 篇论文（处理 {self.processed_count}/{self.max_papers} 篇目标条目）")
        if self.processed_count >= self.max_papers:
            if self.all_papers:
                print(f"\n已在前 {self.max_papers} 篇中找到 {len(self.all_papers)} 篇新增论文，停止爬取")
            else:
                print(f"\n前 {self.max_papers} 篇均为已有论文，无新增数据，停止爬取")
            return True
        return False

    def _fetch_details_for_new_papers(self):
        if not (self.fetch_details and self.all_papers):
            return
        print(f"\n开始爬取 {len(self.all_papers)} 篇论文的详情页")
        for idx, paper in enumerate(self.all_papers, 1):
            arxiv_url = paper.get('arxiv_url')
            if not arxiv_url:
                continue
            print(f"  [{idx}/{len(self.all_papers)}] 获取 {arxiv_url}")
            detail = fetch_paper_detail(arxiv_url, use_proxy=self.use_proxy)
            if detail:
                paper.update(detail)
            if self.detail_sleep and idx < len(self.all_papers):
                time.sleep(self.detail_sleep)

    def _summarize_new_papers(self):
        if not (self.summarize_new and self.all_papers):
            return
        asyncio.run(
            summarize_papers_with_llm(
                papers=self.all_papers,
                model=self.summary_model,
                temperature=self.summary_temperature,
                max_tokens=self.summary_max_tokens,
                sleep_time=self.summary_sleep,
                concurrency=self.summary_concurrency
            )
        )

    def _collect_algorithm_phrases(self, papers):
        phrases = []
        for paper in papers:
            alg = paper.get('algorithm_phrase')
            if isinstance(alg, list):
                phrases.extend([p.strip() for p in alg if isinstance(p, str) and p.strip()])
            elif isinstance(alg, str):
                segments = [seg.strip("-• \t") for seg in alg.split('\n')]
                phrases.extend([seg for seg in segments if seg])
        # 去重但保持顺序
        seen = set()
        deduped = []
        for phrase in phrases:
            if phrase in seen:
                continue
            seen.add(phrase)
            deduped.append(phrase)
        return deduped

    def _aggregate_hot_phrases(self, combined_papers):
        if not (self.aggregate_hot and combined_papers):
            return
        phrases = self._collect_algorithm_phrases(combined_papers)
        if not phrases:
            print("未收集到任何 algorithm_phrase，跳过热门聚合")
            return
        print("\n开始 LLM 聚合热门算法短语")
        total_phrases = len(phrases)
        prompt_phrases = min(total_phrases, 200)
        print(f"  已收集 {total_phrases} 条 algorithm_phrase 供聚合，"
              f"本次传入 LLM: {prompt_phrases}")
        self.hot_phrases = asyncio.run(
            aggregate_trending_phrases_with_llm(
                phrases=phrases,
                model=self.hot_model or self.summary_model,
                temperature=self.hot_temperature,
                max_tokens=self.hot_max_tokens,
                top_k=self.hot_top_k
            )
        )
        if isinstance(self.hot_phrases, list):
            print("热门算法短语：")
            for idx, phrase in enumerate(self.hot_phrases, 1):
                print(f"  🔥 {idx}. {phrase}")

    def get_hot_phrases(self, limit=5):
        """
        获取最近一次聚合得到的热门算法短语，默认返回前 5 条。
        """
        if not self.hot_phrases:
            return []
        limit = max(1, limit or 5)
        return self.hot_phrases[:limit]

    def run(self):
        """
        执行完整抓取流程，返回包含新增与历史论文的汇总结果。
        """
        self._initialize_existing_data()

        num_pages = (self.max_papers + self.papers_per_page - 1) // self.papers_per_page
        print(f"{'=' * 80}")
        print("开始爬取 arXiv cs.AI 论文")
        print(f"目标: 前 {self.max_papers} 篇论文")
        print(f"预计爬取: {num_pages} 页")
        print(f"{'=' * 80}\n")

        for page in range(num_pages):
            should_stop = self._handle_page(page, num_pages)
            if should_stop:
                break
            if page < num_pages - 1:
                print(f"  等待 {self.sleep_time} 秒...")
                time.sleep(self.sleep_time)

        self._fetch_details_for_new_papers()
        self._summarize_new_papers()

        if not self.all_papers:
            print("无新增论文，跳过详情页抓取和 LLM 摘要。")

        combined_papers = self.all_papers + self.existing_papers
        self._aggregate_hot_phrases(combined_papers)
        return {
            'date_info': self.date_info or (self.existing_data.get('date_info') if self.existing_data else {}),
            'total_papers': len(combined_papers),
            'papers': combined_papers,
            'new_papers': self.all_papers,
            'hot_phrases': self.hot_phrases
        }


def save_to_json(data, filename='arxiv_papers.json'):
    """保存数据到 JSON 文件"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"数据已保存到 {filename}")


def print_papers(data):
    """打印论文信息"""
    if not data:
        print("没有数据")
        return

    print(f"\n{'=' * 80}")
    print(f"日期: {data['date_info'].get('scrape_date', 'Unknown')}")
    print(f"总共 {data['total_papers']} 篇论文")
    print(f"{'=' * 80}\n")

    if data.get('hot_phrases'):
        print("最新热门算法短语 TOP 10:")
        for idx, phrase in enumerate(data['hot_phrases'], 1):
            print(f"  🔥 {idx}. {phrase}")
        print(f"{'-' * 80}\n")

    for i, paper in enumerate(data['papers'], 1):
        print(f"[{i}] {paper.get('arxiv_id', 'N/A')}")
        print(f"标题: {paper.get('title', 'N/A')}")
        print(f"作者: {', '.join(paper.get('authors', []))}")
        print(f"分类: {paper.get('subjects', 'N/A')}")
        if 'comments' in paper:
            print(f"备注: {paper['comments']}")
        print(f"链接: {paper.get('arxiv_url', 'N/A')}")
        print(f"PDF: {paper.get('pdf_url', 'N/A')}")
        if paper.get('algorithm_phrase'):
            print(f"AI 总结: {paper['algorithm_phrase']}")
        print("-" * 80)


if __name__ == '__main__':
    load_local_env()

    api_key = os.getenv('OPENAI_API_KEY')
    base_url = os.getenv('OPENAI_BASE_URL') or os.getenv('OPENAI_API_BASE')
    model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    def mask(value):
        if not value:
            return '未设置'
        if len(value) <= 8:
            return value
        return f"{value[:4]}...{value[-4:]}"

    print("\n当前环境变量：")
    print(f"  OPENAI_API_KEY: {mask(api_key)}")
    print(f"  OPENAI_BASE_URL: {base_url or '未设置'}")
    print(f"  OPENAI_MODEL: {model or '未设置'}\n")

    crawler = ArxivCrawler(
        max_papers=25,
        papers_per_page=25,
        use_proxy=True,
        sleep_time=2,
        summarize_new=True,
        summary_model=model
    )
    data = crawler.run()

    if data:
        print_papers({
            'date_info': data['date_info'],
            'total_papers': data['total_papers'],
            'papers': data['papers'][:5]
        })

        save_to_json(data)
        print(f"\n完整数据已保存，共 {data['total_papers']} 篇论文")
    else:
        print("爬取失败")