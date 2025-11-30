"""
Utility script to collect all innovation_synthesis markdown files for a user.

Usage:
    python scripts/copy_innovation_synthesis.py --user-name dev_tester
    python scripts/copy_innovation_synthesis.py --user-name alice --dest-dir E:/tmp/alice_md
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import List, Tuple


def _default_output_root() -> Path:
    """Return the default base output directory."""
    # scripts/ -> project root
    project_root = Path(__file__).resolve().parents[1]
    return project_root / "app" / "core" / "workflows" / "output"


def _find_innovation_markdowns(user_root: Path) -> List[Tuple[str, Path]]:
    """
    Locate all innovation_synthesis markdown files under the given user root.

    Returns:
        List of tuples (session_name, markdown_path).
    """
    markdowns: List[Tuple[str, Path]] = []
    pattern = "**/final_proposals/innovation_synthesis*.md"
    for md_path in user_root.glob(pattern):
        if not md_path.is_file():
            continue
        session_dir = next(
            (parent.name for parent in md_path.parents if parent.name.startswith("session_")),
            "session_unknown",
        )
        markdowns.append((session_dir, md_path))
    return markdowns


def copy_markdowns(user_name: str, output_root: Path, dest_dir: Path) -> int:
    """
    Copy all innovation_synthesis markdown files for a user into dest_dir.

    Returns:
        Number of files copied.
    """
    user_root = output_root / user_name
    if not user_root.exists():
        raise FileNotFoundError(f"User output folder not found: {user_root}")

    markdowns = _find_innovation_markdowns(user_root)
    if not markdowns:
        print(f"No innovation_synthesis markdowns found under {user_root}")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for session_name, md_path in markdowns:
        suffix = md_path.stem.replace("innovation_synthesis", "").strip("_")
        suffix_part = f"_{suffix}" if suffix else ""
        dest_name = f"{session_name}{suffix_part}_innovation_synthesis.md"
        dest_path = dest_dir / dest_name
        shutil.copy2(md_path, dest_path)
        copied += 1
        print(f"Copied {md_path} -> {dest_path}")

    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect innovation_synthesis markdown files.")
    parser.add_argument(
        "--user-name",
        required=True,
        help="Name of the user folder inside app/core/workflows/output",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=_default_output_root(),
        help="Root folder containing per-user session outputs.",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        help="Destination folder to store collected markdowns. Defaults to <output-root>/<user>/collected_markdown.",
    )
    args = parser.parse_args()

    dest_dir = args.dest_dir or (args.output_root / args.user_name / "collected_markdown")
    copied = copy_markdowns(args.user_name, args.output_root, dest_dir)
    print(f"Done. {copied} file(s) copied to {dest_dir}")


if __name__ == "__main__":
    # 详细使用说明见 docs/copy_innovation_synthesis.md
    main()
    #python scripts/copy_innovation_synthesis.py   --user-name 2025_11_29

