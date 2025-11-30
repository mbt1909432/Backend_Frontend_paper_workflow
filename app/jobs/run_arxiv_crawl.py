import argparse
import asyncio
from pathlib import Path

from app.config.settings import proxy_manager, settings
from app.services.crawler_service import MonthlyArxivSyncService


def parse_args():
    parser = argparse.ArgumentParser(description="Run the arXiv crawler once.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip database writes and optionally dump JSON output.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="When --dry-run is used, save crawler result to this JSON file.",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    await ensure_proxy_ready()

    service = MonthlyArxivSyncService()
    output_path = None
    if args.dry_run:
        if args.output:
            output_path = str(Path(args.output).resolve())
        else:
            repo_root = Path(__file__).resolve().parents[2]
            output_path = str(repo_root / "lab" / "arxiv_papers.json")
    await service.run_once(persist=not args.dry_run, output_path=output_path)


async def ensure_proxy_ready() -> None:
    """检测代理可用性，不可用时自动切换为直连模式。"""
    if not settings.arxiv_use_proxy:
        return

    if not settings.proxy_enabled:
        print("已启用 arXiv 代理但 PROXY_ENABLED=false，爬虫会直接访问公网。")
        return

    print(f"检测代理可用性: {settings.proxy_url} ...")
    available = await proxy_manager.is_proxy_available(force_check=True)
    if available:
        print("✓ 代理可用，继续执行爬虫。")
        return

    print("✗ 代理不可用，自动切换为直连模式。")
    settings.arxiv_use_proxy = False
    print("已关闭 ARXIV_USE_PROXY，后续请求将直接访问 arXiv。")


if __name__ == "__main__":
    asyncio.run(main())
