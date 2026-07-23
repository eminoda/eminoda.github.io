#!/usr/bin/env python3
"""Copy GEO markdown and generate llms.txt with shared inclusion rules."""

from __future__ import annotations

import argparse
import re
import shutil
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

CUTOFF = date(2026, 7, 1)
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
TITLE_RE = re.compile(r"^title:\s*(.+)$", re.MULTILINE)
DATE_RE = re.compile(r"^date:\s*(.+)$", re.MULTILINE)
DRAFT_RE = re.compile(r"^draft:\s*(.+)$", re.MULTILINE)


def parse_front_matter(text: str) -> dict[str, str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    block = match.group(1)
    meta: dict[str, str] = {}
    title = TITLE_RE.search(block)
    if title:
        meta["title"] = title.group(1).strip().strip("\"'")
    date_m = DATE_RE.search(block)
    if date_m:
        meta["date"] = date_m.group(1).strip().strip("\"'")
    draft = DRAFT_RE.search(block)
    if draft:
        meta["draft"] = draft.group(1).strip().lower()
    return meta


def parse_date(value: str) -> date | None:
    value = value.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            # normalize +08:00 -> +0800 for %z on older Python
            candidate = value
            if fmt.endswith("%z") and re.search(r"[+-]\d{2}:\d{2}$", candidate):
                candidate = candidate[:-3] + candidate[-2:]
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    # fallback: leading YYYY-MM-DD
    m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
    if m:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    return None


def is_included(path: Path, meta: dict[str, str]) -> bool:
    if path.name != "index.md":
        return False
    if path.name.startswith("_"):
        return False
    parts = path.parts
    if "Templates" in parts or ".obsidian" in parts or ".cursor" in parts:
        return False
    if meta.get("draft") in {"true", "yes", "1"}:
        return False
    title = meta.get("title")
    if not title:
        return False
    post_date = parse_date(meta["date"]) if "date" in meta else None
    if post_date is None or post_date < CUTOFF:
        return False
    return True


def category_for(rel: Path) -> str:
    # blogs/frontend/devops/vpn/slug/index.md -> frontend/devops
    parts = rel.parts
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if parts:
        return parts[0]
    return "uncategorized"


def collect_posts(content_blogs: Path) -> list[tuple[Path, dict[str, str], Path]]:
    posts: list[tuple[Path, dict[str, str], Path]] = []
    for md in content_blogs.rglob("index.md"):
        if md.name.startswith("_"):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = md.read_text(encoding="utf-8", errors="replace")
        meta = parse_front_matter(text)
        if not is_included(md, meta):
            continue
        rel = md.relative_to(content_blogs)
        posts.append((md, meta, rel))
    posts.sort(key=lambda item: (category_for(item[2]), item[1].get("date", ""), item[1]["title"]))
    return posts


def write_llms_txt(posts: list[tuple[Path, dict[str, str], Path]], out: Path, base_url: str) -> None:
    base = base_url.rstrip("/")
    grouped: dict[str, list[tuple[dict[str, str], Path]]] = defaultdict(list)
    for _, meta, rel in posts:
        grouped[category_for(rel)].append((meta, rel))

    lines = [
        "# eminoda blogs",
        "",
        f"> Posts from {CUTOFF.isoformat()} onward (Markdown for AI / GEO)",
        "",
    ]
    for category in sorted(grouped):
        lines.append(f"## {category}")
        lines.append("")
        for meta, rel in grouped[category]:
            # rel is frontend/.../slug/index.md -> URL /blogs/frontend/.../slug/index.md
            url = f"{base}/blogs/{rel.as_posix()}"
            lines.append(f"- [{meta['title']}]({url})")
        lines.append("")

    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-blogs", type=Path, default=Path("content/blogs"))
    parser.add_argument("--public", type=Path, default=Path("public"))
    parser.add_argument(
        "--base-url",
        default="https://eminoda.github.io",
        help="Site base URL without trailing slash",
    )
    args = parser.parse_args()

    content_blogs = args.content_blogs
    public = args.public
    if not content_blogs.is_dir():
        raise SystemExit(f"content blogs not found: {content_blogs}")
    if not public.is_dir():
        raise SystemExit(f"public dir not found: {public}")

    posts = collect_posts(content_blogs)
    for src, _, rel in posts:
        dest = public / "blogs" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    write_llms_txt(posts, public / "llms.txt", args.base_url)
    print(f"GEO: copied {len(posts)} markdown file(s), wrote {public / 'llms.txt'}")


if __name__ == "__main__":
    main()
