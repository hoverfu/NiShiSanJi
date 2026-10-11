#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
倪师三纪资料库轻量检索脚本（仅依赖 Python 标准库）。

用法:
    python search.py 关键词1 [关键词2 ...] [--module renji-md|txt|tianji|all]
                                      [--root 仓库根目录] [--limit 15]

输出按"同句命中关键词数量"排序的行级命中，附相对路径、行号与所属章节；
另外列出文件名直接命中的文件（本草等按药物命名的篇目尤其有用）。
"""
import argparse
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HEADING_RE = re.compile(r"^#{1,6}\s+\S")
TXT_HEADING_RE = re.compile(r"第[一二三四五六七八九十百零0-9]+[篇章节]")
SNIPPET_HALF = 60


def detect_root(script_dir: str) -> str:
    """按优先级探测 corpus 根目录。"""
    env = os.environ.get("NIHAIXIA_SANJI_ROOT")
    if env and os.path.isdir(env):
        return env
    for cfg in (os.path.join(script_dir, "corpus-root.txt"),
                os.path.join(os.path.dirname(script_dir), "corpus-root.txt")):
        if os.path.isfile(cfg):
            with open(cfg, "r", encoding="utf-8-sig") as f:
                p = f.read().strip()
            if p and os.path.isdir(p):
                return p
    cur = script_dir
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, "人纪")) and os.path.isdir(os.path.join(cur, "天纪")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


def scan_targets(root: str, module: str):
    """返回 (相对目录, 扩展名) 扫描目标列表。"""
    targets = []
    if module in ("renji-md", "all"):
        targets.append((os.path.join(root, "人纪"), ".md"))
    if module in ("txt", "all"):
        targets.append((os.path.join(root, "人纪文字实录TXT"), ".txt"))
    if module in ("tianji", "all"):
        targets.append((os.path.join(root, "天纪"), ".md"))
    return targets


def iter_files(base: str, ext: str):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".vscode", "img")]
        for name in filenames:
            if name.lower().endswith(ext):
                yield os.path.join(dirpath, name)


def heading_of(line: str, is_txt: bool):
    s = line.strip()
    if not s:
        return None
    if is_txt:
        return s if TXT_HEADING_RE.search(s) else None
    return s[2:].strip() if HEADING_RE.match(s) else None


def snippet(line: str, terms):
    s = line.strip()
    pos = min((s.find(t) for t in terms if s.find(t) >= 0), default=0)
    start = max(0, pos - SNIPPET_HALF)
    end = min(len(s), pos + SNIPPET_HALF)
    return ("…" if start > 0 else "") + s[start:end] + ("…" if end < len(s) else "")


def main():
    ap = argparse.ArgumentParser(description="倪师三纪资料库检索")
    ap.add_argument("terms", nargs="+", help="检索关键词（多个关键词取并集后按同句命中数排序）")
    ap.add_argument("--module", choices=["renji-md", "txt", "tianji", "all"], default="renji-md")
    ap.add_argument("--root", default="", help="corpus 根目录（NiShiSanJi 仓库根）")
    ap.add_argument("--limit", type=int, default=15, help="行级命中最多返回条数（默认15）")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root = args.root or detect_root(script_dir)
    if not root or not os.path.isdir(root):
        print("找不到 corpus 根目录。请用 --root 指定 NiShiSanJi 仓库根目录，"
              "或设置环境变量 NIHAIXIA_SANJI_ROOT，或在脚本旁放置 corpus-root.txt。")
        sys.exit(2)

    terms = [t.lower() for t in args.terms if t.strip()]
    if not terms:
        print("关键词为空。")
        sys.exit(2)

    hits = []          # (覆盖词数, 相对路径, 行号, 章节, 片段)
    name_hits = []     # (相对路径, 预览)
    per_file_count = {}
    files_scanned = 0

    for base, ext in scan_targets(root, args.module):
        if not os.path.isdir(base):
            continue
        is_txt = ext == ".txt"
        for path in iter_files(base, ext):
            files_scanned += 1
            rel = os.path.relpath(path, root).replace("\\", "/")
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            if any(t in stem for t in terms):
                name_hits.append((rel, os.path.basename(path)))
            last_heading = ""
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except OSError:
                continue
            for idx, raw in enumerate(lines, start=1):
                h = heading_of(raw, is_txt)
                if h:
                    last_heading = h
                low = raw.lower()
                matched = [t for t in terms if t in low]
                if matched:
                    per_file_count[rel] = per_file_count.get(rel, 0) + 1
                    hits.append((len(set(matched)), rel, idx, last_heading,
                                 snippet(raw, terms)))

    hits.sort(key=lambda x: (-x[0], x[1], x[2]))

    print(f"检索词: {' / '.join(args.terms)}    模块: {args.module}    扫描文件: {files_scanned}    行命中: {len(hits)}")
    print("=" * 80)

    shown_files = {}
    shown = 0
    for coverage, rel, lineno, htitle, snip in hits:
        cap = shown_files.get(rel, 0)
        if cap >= 3:
            continue
        shown_files[rel] = cap + 1
        shown += 1
        if shown > args.limit:
            break
        tag = f"[{coverage}/{len(terms)}词命中]"
        print(f"{tag} {rel}:{lineno}" + (f"  〔{htitle}〕" if htitle else ""))
        print(f"    {snip}")
        print("-" * 80)

    truncated = [f"{r}（另有{n}处）" for r, n in per_file_count.items()
                 if shown_files.get(r, 0) == 3 and n > 3]
    if truncated:
        print("同文件更多命中: " + "；".join(truncated[:8]))
        print("-" * 80)

    if name_hits:
        print("文件名直接命中（整篇/整药相关）:")
        for rel, name in name_hits[:20]:
            print(f"  - {rel}")
    if not hits and not name_hits:
        print("无命中。可换同义词（如 怕冷→恶寒/畏寒、睡不着→不得眠/不寐），"
              "或加 --module txt 查逐字实录 / --module all 查全部。")


if __name__ == "__main__":
    main()
