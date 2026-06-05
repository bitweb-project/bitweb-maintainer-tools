#!/usr/bin/env python3
"""
Release Notes Generator
========================
Generates Bitcoin Core-style release notes with full audit table.

Usage:
  python release_notes.py --repo /path/to/coin --from v0.9.0
  python release_notes.py --repo /path/to/coin --from abc1234 --to def5678
  python release_notes.py --repo /path/to/coin --last 10

At the end, the script will ask you to enter the version number.
Output: release-notes.md
"""

import os
import re
import hashlib
import subprocess
import argparse


# ══════════════════════════════════════════════════════════════════════════════
#  COIN CONFIGURATION — edit these before use
# ══════════════════════════════════════════════════════════════════════════════

COIN_NAME        = "Bitweb"                              # Short name — used for paths, binaries, dirs
COIN_FULLNAME    = "Bitweb Core"                         # Full display name — used in text
COIN_TICKER      = "BTE"                                 # Ticker symbol
COIN_WEBSITE     = "https://bitwebcore.net"                  # Main website (optional, can be empty)
COIN_GITHUB      = "bitweb-project/bitweb"                  # GitHub user/repo (primary)
COIN_ISSUES      = "https://github.com/bitweb-project/bitweb/issues"
COIN_RELEASES    = "https://github.com/bitweb-project/bitweb/releases"  # Primary download

# OS compatibility (edit to match your supported platforms)
COMPAT_LINUX     = "Linux Kernel 3.17+"
COMPAT_MACOS     = "macOS 13+"
COMPAT_WINDOWS   = "Windows 10+"

# ══════════════════════════════════════════════════════════════════════════════
#  BINARY EXTENSIONS BLACKLIST
# ══════════════════════════════════════════════════════════════════════════════

BINARY_EXTENSIONS = {
    ".svg", ".svgz",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".zst",
    ".a", ".so", ".dll", ".dylib", ".lib",
    ".o", ".obj", ".pyc", ".pyo",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tiff", ".webp",
    ".mp3", ".mp4", ".wav", ".ogg", ".mov", ".avi",
    ".pdf", ".xlsx", ".xls", ".docx", ".pptx",
    ".sqlite", ".db",
    ".lock",
}

# Change type constants
CT_MODIFIED = "modified"
CT_BINARY   = "binary"
CT_RENAMED  = "renamed"
CT_ADDED    = "new_file"
CT_DELETED  = "deleted"


# ══════════════════════════════════════════════════════════════════════════════
#  GIT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True)
    return result.stdout.decode('utf-8', errors='replace').strip()


def get_full_hash(repo, ref):
    return run(["git", "rev-parse", ref], repo)


def get_slug(repo):
    url = run(["git", "remote", "get-url", "origin"], repo)
    url = re.sub(r"\.git$", "", url)
    url = re.sub(r"^https?://github\.com/", "", url)
    url = re.sub(r"^git@github\.com:", "", url)
    return url or COIN_GITHUB


def get_commits_between(repo, from_ref, to_ref):
    out = run(["git", "log", "--format=%H|%s|%ci|%an", f"{from_ref}..{to_ref}"], repo)
    result = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            result.append({
                "hash":   parts[0].strip(),
                "title":  parts[1].strip(),
                "date":   parts[2].strip()[:10],
                "author": parts[3].strip(),
            })
    return list(reversed(result))


def get_last_n_commits(repo, n):
    out = run(["git", "log", "--format=%H|%s|%ci|%an", f"-{n}"], repo)
    result = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            result.append({
                "hash":   parts[0].strip(),
                "title":  parts[1].strip(),
                "date":   parts[2].strip()[:10],
                "author": parts[3].strip(),
            })
    return list(reversed(result))


def get_contributors(repo, from_ref, to_ref):
    """Returns sorted list of unique contributors."""
    out = run(["git", "log", "--format=%aN", f"{from_ref}..{to_ref}"], repo)
    names = sorted(set(line.strip() for line in out.splitlines() if line.strip()))
    return names


# ══════════════════════════════════════════════════════════════════════════════
#  DIFF PARSER
# ══════════════════════════════════════════════════════════════════════════════

def is_binary_by_ext(path):
    _, ext = os.path.splitext(path.lower())
    return ext in BINARY_EXTENSIONS


def get_changed_files(repo, commit):
    diff = run(["git", "diff", "-M", f"{commit}^", commit, "--unified=0"], repo)
    files = []
    current = None

    def flush():
        if current is not None:
            current["added"]   = sorted(set(current["added"]))
            current["removed"] = sorted(set(current["removed"]))
            files.append(current)

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            flush()
            current = {"type": CT_MODIFIED, "path": None, "old_path": None,
                       "added": [], "removed": []}
            continue
        if current is None:
            continue

        if line.startswith("+++ b/"):
            current["path"] = line[6:]
            if is_binary_by_ext(current["path"]):
                current["type"] = CT_BINARY
            continue
        if line.startswith("--- a/"):
            old = line[6:]
            if old != "/dev/null":
                current["old_path"] = old
            continue
        if line.startswith("+++ /dev/null"):
            current["type"] = CT_DELETED
            if current["old_path"]:
                current["path"] = current["old_path"]
            continue
        if line.startswith("Binary files"):
            current["type"] = CT_BINARY
            m = re.match(r"Binary files a/(.+) and b/(.+) differ", line)
            if m:
                current["old_path"] = m.group(1)
                current["path"]     = m.group(2)
            continue
        if line.startswith("rename from "):
            current["old_path"] = line[12:]
            current["type"]     = CT_RENAMED
            continue
        if line.startswith("rename to "):
            current["path"] = line[10:]
            if is_binary_by_ext(current["path"]):
                current["type"] = CT_BINARY
            continue
        if line.startswith("new file mode"):
            if current["type"] != CT_BINARY:
                current["type"] = CT_ADDED
            continue
        if line.startswith("deleted file mode"):
            current["type"] = CT_DELETED
            continue

        if current["type"] not in (CT_MODIFIED, CT_ADDED, CT_RENAMED):
            continue

        hunk = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if hunk:
            old_start = int(hunk.group(1))
            old_count = int(hunk.group(2)) if hunk.group(2) is not None else 1
            new_start = int(hunk.group(3))
            new_count = int(hunk.group(4)) if hunk.group(4) is not None else 1
            for ln in range(old_start, old_start + old_count):
                if ln > 0:
                    current["removed"].append(ln)
            for ln in range(new_start, new_start + new_count):
                if ln > 0:
                    current["added"].append(ln)

    flush()
    return files


# ══════════════════════════════════════════════════════════════════════════════
#  URL / FORMATTING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def compress_lines(lines):
    if not lines:
        return []
    ranges, start, end = [], lines[0], lines[0]
    for ln in lines[1:]:
        if ln == end + 1:
            end = ln
        else:
            ranges.append((start, end))
            start = end = ln
    ranges.append((start, end))
    return ranges


def fmt_ranges(ranges):
    return ", ".join(str(s) if s == e else f"{s}-{e}" for s, e in ranges)


def gh_diff_url(slug, commit, path, side, line_s, line_e=None):
    p = path.replace("\\", "/")
    fh = hashlib.sha256(p.encode()).hexdigest()
    anchor = f"diff-{fh}{side}{line_s}"
    if line_e and line_e != line_s:
        anchor += f"-{side}{line_e}"
    return f"https://github.com/{slug}/commit/{commit}#{anchor}"


def gh_commit_url(slug, commit):
    return f"https://github.com/{slug}/commit/{commit}"


def render_file_row(slug, commit, f):
    ctype    = f["type"]
    path     = f["path"] or ""
    old_path = f["old_path"] or ""
    c_url    = gh_commit_url(slug, commit)

    if ctype == CT_BINARY:
        if old_path and old_path != path:
            label = f"`{old_path}` → `{path}`"
        else:
            label = f"[`{path}`]({c_url})"
        return f"| {label} | 🔄 binary / full replacement |"

    if ctype == CT_DELETED:
        return f"| ~~`{path}`~~ | 🗑 deleted |"

    if ctype == CT_ADDED:
        added = f["added"]
        if added:
            ranges = compress_lines(added)
            s, e = ranges[0]
            url = gh_diff_url(slug, commit, path, "R", s, e)
            line_str = f"[+{fmt_ranges(ranges)}]({url})"
        else:
            url = c_url
            line_str = "🆕 new file"
        return f"| [`{path}`]({url}) | {line_str} |"

    if ctype == CT_RENAMED:
        added = f["added"]
        if added:
            ranges = compress_lines(added)
            s, e = ranges[0]
            url = gh_diff_url(slug, commit, path, "R", s, e)
            line_str = f"[+{fmt_ranges(ranges)}]({url})"
        else:
            url = c_url
            line_str = "📝 renamed only"
        if old_path and old_path != path:
            file_label = f"`{old_path}` → [`{path}`]({url})"
        else:
            file_label = f"[`{path}`]({url})"
        return f"| {file_label} | {line_str} |"

    # Modified
    added   = f["added"]
    removed = f["removed"]
    if added:
        ranges = compress_lines(added)
        s, e = ranges[0]
        url = gh_diff_url(slug, commit, path, "R", s, e)
        line_str = f"[+{fmt_ranges(ranges)}]({url})"
    elif removed:
        ranges = compress_lines(removed)
        s, e = ranges[0]
        url = gh_diff_url(slug, commit, path, "L", s, e)
        line_str = f"[-{fmt_ranges(ranges)}]({url})"
    else:
        url = c_url
        line_str = "—"
    return f"| [`{path}`]({url}) | {line_str} |"


# ══════════════════════════════════════════════════════════════════════════════
#  DOCUMENT RENDERER
# ══════════════════════════════════════════════════════════════════════════════

def render_header(version, slug):
    # COIN_FULLNAME → text/display  e.g. "MyCoin Core"
    # COIN_NAME     → paths/bins    e.g. "MyCoin"
    # coin_lc       → dirs/commands e.g. "mycoin"
    title     = f"{COIN_FULLNAME} version v{version} Release Notes"
    underline = "=" * len(title)
    coin_lc   = COIN_NAME.lower()

    lines = [
        title,
        underline,
        "",
        f"{COIN_FULLNAME} version v{version} is now available from:",
        "",
        f"  <{COIN_RELEASES}/tag/v{version}>",
    ]

    # Optional website mirror link
    if COIN_WEBSITE:
        lines += [
            "",
            f"  <{COIN_WEBSITE}/bin/{coin_lc}-{version}/>  (mirror)",
        ]

    lines += [
        "",
        "This release includes new features, various bug fixes and performance",
        "improvements, as well as updated translations.",
        "",
        "Please report bugs using the issue tracker at GitHub:",
        "",
        f"  <{COIN_ISSUES}>",
        "",
        "To receive security and update notifications, please subscribe to:",
        "",
        f"  <{COIN_RELEASES}>",
        "",
        "",
        "How to Upgrade",
        "==============",
        "",
        "⚠️  BACKUP YOUR WALLET BEFORE UPGRADING",
        "",
        "1. Shut down your wallet completely and wait until it has fully closed",
        "   (this might take a few minutes).",
        "",
        "2. Back up your wallet.dat file before upgrading.",
        "   Default wallet.dat locations:",
        "",
        f"     Windows : %APPDATA%\\{COIN_NAME}\\wallet\\wallet.dat",
        f"     macOS   : ~/Library/Application Support/{COIN_NAME}/wallet/wallet.dat",
        f"     Linux   : ~/.{coin_lc}/wallet/wallet.dat",
        "",
        "   If you configured a custom data directory (-datadir), your wallet.dat",
        "   is located at: <your-custom-datadir>/wallet/wallet.dat",
        "",
        "3. Copy wallet.dat to a safe location (external drive, encrypted backup)",
        "   before proceeding with the upgrade.",
        "",
        "Then run the installer (on Windows) or just copy over",
        f"`/Applications/{COIN_NAME}-Qt` (on macOS) or `{coin_lc}d`/`{coin_lc}-qt` (on Linux).",
        "",
        "",
        "Compatibility",
        "=============",
        "",
        f"{COIN_FULLNAME} is supported and tested on operating systems using the",
        f"{COMPAT_LINUX}, {COMPAT_MACOS}, and {COMPAT_WINDOWS}.",
        f"{COIN_FULLNAME} should also work on most other Unix-like systems but is not as",
        "frequently tested on them.",
        "",
        "",
        "Notable Changes",
        "===============",
        "",
    ]

    return "\n".join(lines)


def render_commit_section(slug, commit_info, changed_files):
    commit = commit_info["hash"]
    title  = commit_info["title"]
    date   = commit_info["date"]
    short  = commit[:7]
    c_url  = gh_commit_url(slug, commit)

    rows = [render_file_row(slug, commit, f) for f in changed_files]
    if not rows:
        rows = ["| *no file changes detected* | — |"]

    # Stats line
    n_modified = sum(1 for f in changed_files if f["type"] == CT_MODIFIED)
    n_added    = sum(1 for f in changed_files if f["type"] == CT_ADDED)
    n_deleted  = sum(1 for f in changed_files if f["type"] == CT_DELETED)
    n_renamed  = sum(1 for f in changed_files if f["type"] == CT_RENAMED)
    n_binary   = sum(1 for f in changed_files if f["type"] == CT_BINARY)
    total_add  = sum(len(f["added"])   for f in changed_files)
    total_del  = sum(len(f["removed"]) for f in changed_files)

    stats = []
    if n_modified: stats.append(f"✏️ {n_modified} modified")
    if n_added:    stats.append(f"🆕 {n_added} new")
    if n_deleted:  stats.append(f"🗑 {n_deleted} deleted")
    if n_renamed:  stats.append(f"📝 {n_renamed} renamed")
    if n_binary:   stats.append(f"🔄 {n_binary} binary")
    stats.append(f"+{total_add} / -{total_del} lines")

    return "\n".join([
        f"### {title}",
        "",
        f"> [`{short}`]({c_url}) · {date}",
        "",
        "| File | Lines |",
        "|------|-------|",
        *rows,
        "",
        f"*{len(changed_files)} file(s) · {' · '.join(stats)}*",
        "",
        "---",
        "",
    ])


def render_credits(contributors):
    lines = [
        "Credits",
        "=======",
        "",
        "Thanks to everyone who directly contributed to this release:",
        "",
    ]
    for name in contributors:
        lines.append(f"- {name}")
    lines += [
        "",
        f"{COIN_FULLNAME} is based on Bitcoin Core.",
        "Original Bitcoin Core developers:",
        "  <https://github.com/bitcoin/bitcoin/graphs/contributors>",
        "",
    ]
    return "\n".join(lines)


def render_doc(version, slug, commits_data, contributors, from_label, to_label):
    parts = [render_header(version, slug)]

    for commit_info, changed_files in commits_data:
        parts.append(render_commit_section(slug, commit_info, changed_files))

    parts.append(render_credits(contributors))
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo",   default=".")
    parser.add_argument("--from",   dest="from_ref", default=None,
                        help="Start point (commit/tag). Excluded from results.")
    parser.add_argument("--to",     dest="to_ref",   default="HEAD")
    parser.add_argument("--last",   type=int,        default=None,
                        help="Use last N commits instead of a range")
    parser.add_argument("--slug",   default=None,    help="Override GitHub user/repo")
    parser.add_argument("--output", default="release-notes.md")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    slug = args.slug or get_slug(repo) or COIN_GITHUB
    print(f"🐙  {slug}")
    print(f"🪙  {COIN_FULLNAME} ({COIN_TICKER})")

    # ── Collect commits ──────────────────────────────────────────────────────
    if args.last:
        commits = get_last_n_commits(repo, args.last)
        from_label = f"last {args.last}"
        to_label   = "HEAD"
        fh = get_full_hash(repo, "HEAD~" + str(args.last))
        th = get_full_hash(repo, "HEAD")
    elif args.from_ref:
        fh = get_full_hash(repo, args.from_ref)
        th = get_full_hash(repo, args.to_ref)
        commits = get_commits_between(repo, fh, th)
        from_label = f"{args.from_ref} ({fh[:7]})"
        to_label   = f"{args.to_ref} ({th[:7]})"
    else:
        print("❌  Use --from <commit/tag> or --last <N>")
        return

    if not commits:
        print("⚠️  No commits found.")
        return

    print(f"📋  {len(commits)} commit(s) found\n")

    # ── Parse each commit ────────────────────────────────────────────────────
    commits_data = []
    for c in commits:
        changed = get_changed_files(repo, c["hash"])
        n_bin   = sum(1 for f in changed if f["type"] == CT_BINARY)
        added   = sum(len(f["added"])   for f in changed)
        removed = sum(len(f["removed"]) for f in changed)
        extra   = f"  🔄 {n_bin} binary" if n_bin else ""
        print(f"  {c['hash'][:7]}  {c['date']}  {c['title']}")
        print(f"           {len(changed)} file(s)  +{added}/-{removed} lines{extra}")
        commits_data.append((c, changed))

    # ── Contributors ─────────────────────────────────────────────────────────
    contributors = get_contributors(repo, fh, th)

    # ── Ask for version ──────────────────────────────────────────────────────
    print()
    print("─" * 50)
    version = input(f"  Enter version for {COIN_FULLNAME} release notes (e.g. 1.0.0): ").strip()
    if not version:
        version = "0.0.0"
    print("─" * 50)

    # ── Render and save ──────────────────────────────────────────────────────
    md  = render_doc(version, slug, commits_data, contributors, from_label, to_label)
    out = os.path.join(repo, args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n✅  Saved: {out}")
    print(f"📄  {COIN_FULLNAME} v{version} — {len(commits)} commit(s) · {len(contributors)} contributor(s)")


if __name__ == "__main__":
    main()
