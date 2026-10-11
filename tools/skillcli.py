#!/usr/bin/env python3
"""skillcli - manage WorkBuddy local skills.

Commands: list / validate / install / uninstall / info / pack

The official skillmanager CLI recognizes only claude, openclaw, codex and gemini
as target agents, so it cannot touch ~/.workbuddy/skills. This tool covers that
gap and adds packaging. Skills live in WORKBUDDY_SKILLS_DIR, default
~/.workbuddy/skills.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

SKILLS_DIR = Path(
    os.environ.get("WORKBUDDY_SKILLS_DIR", Path.home() / ".workbuddy" / "skills")
).expanduser()

TRASH_DIR = SKILLS_DIR / ".trash"
GITHUB_URL = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)"
    r"(?:\.git)?(?:/tree/(?P<branch>.+?))?(?:/(?P<sub>.+))?/?$"
)

OK = "  ok  "
WARN = " warn "
FAIL = " FAIL "


def out(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")


def die(msg: str) -> "typing.NoReturn":  # noqa: F821
    sys.stderr.write("error: " + msg + "\n")
    raise SystemExit(1)


def skill_dirs() -> list[Path]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(
        d
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "SKILL.md").is_file()
    )


def resolve(name: str) -> Path:
    """Find a skill by directory name or by the name in its frontmatter."""
    target = SKILLS_DIR / name
    if (target / "SKILL.md").is_file():
        return target
    for d in skill_dirs():
        fm, _ = read_frontmatter(d / "SKILL.md")
        if fm and fm.get("name") == name:
            return d
    die("no skill named %r under %s" % (name, SKILLS_DIR))


def read_frontmatter(path: Path) -> tuple[dict | None, str]:
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    fm: dict[str, str] = {}
    for line in parts[1].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm, parts[2]


def check(skill: Path) -> list[tuple[str, str]]:
    """Return a list of (status, message)."""
    results: list[tuple[str, str]] = []
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        return [(FAIL, "SKILL.md missing")]

    fm, body = read_frontmatter(skill_md)
    if fm is None:
        results.append((FAIL, "YAML frontmatter missing or unterminated"))
        return results

    if not fm.get("name"):
        results.append((FAIL, "frontmatter has no name"))
    elif fm["name"] != skill.name:
        results.append(
            (FAIL, "name %r does not match directory %r" % (fm["name"], skill.name))
        )
    else:
        results.append((OK, "name matches directory"))

    desc = fm.get("description", "")
    if not desc:
        results.append((FAIL, "frontmatter has no description"))
    elif len(desc) < 40:
        results.append((WARN, "description is short (%d chars)" % len(desc)))
    else:
        results.append((OK, "description present (%d chars)" % len(desc)))

    if fm.get("agent_created") != "true":
        results.append((WARN, "agent_created: true not set, model cannot edit it"))
    else:
        results.append((OK, "agent_created set"))

    if len(body.strip()) < 50:
        results.append((WARN, "body is nearly empty"))
    else:
        results.append((OK, "body present (%d words)" % len(body.split())))

    stray = [
        p.name
        for p in skill.iterdir()
        if p.is_file() and p.suffix not in {".md", ".json", ".txt", ".lua", ".py", ".sh"}
    ]
    if stray:
        results.append((WARN, "unexpected files: " + ", ".join(stray)))
    return results


def cmd_list(args: argparse.Namespace) -> None:
    skills = skill_dirs()
    if args.json:
        payload = []
        for d in skills:
            fm, body = read_frontmatter(d / "SKILL.md")
            payload.append(
                {
                    "dir": d.name,
                    "name": (fm or {}).get("name"),
                    "description": (fm or {}).get("description"),
                    "agent_created": (fm or {}).get("agent_created"),
                    "files": len([p for p in d.rglob("*") if p.is_file()]),
                    "bytes": sum(p.stat().st_size for p in d.rglob("*") if p.is_file()),
                    "missing_skill_md": False,
                }
            )
        out(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not skills:
        out("no skills under %s" % SKILLS_DIR)
        return

    broken = [
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".") and not (d / "SKILL.md").is_file()
    ]
    out("skills dir: %s" % SKILLS_DIR)
    out("%-32s %8s %6s  %s" % ("NAME", "FILES", "SIZE", "DESCRIPTION"))
    for d in skills:
        fm, _ = read_frontmatter(d / "SKILL.md")
        files = [p for p in d.rglob("*") if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        desc = (fm or {}).get("description", "")
        desc = " ".join(desc.split())
        flag = ""
        if (fm or {}).get("name") != d.name:
            flag = "  [!]"
        out(
            "%-32s %8d %6.1fK  %s%s"
            % (d.name, len(files), size / 1024.0, desc[:68] + ("..." if len(desc) > 68 else ""), flag)
        )
    if broken:
        out("\nwithout SKILL.md: " + ", ".join(broken))


def cmd_validate(args: argparse.Namespace) -> None:
    skills = [resolve(args.name)] if args.name else skill_dirs()
    if not skills:
        die("no skills to validate")
    worst = 0
    for d in skills:
        out(d.name)
        for status, msg in check(d):
            out("  %s %s" % (status, msg))
            if status == FAIL:
                worst = 1
        out("")
    raise SystemExit(worst)


def _github_commit(owner: str, repo: str, branch: str) -> str | None:
    url = "https://api.github.com/repos/%s/%s/commits/%s" % (owner, repo, branch)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.load(r).get("sha")
    except Exception:
        return None


def _fetch_github(owner: str, repo: str, branch: str, sub: str, dest: Path) -> str | None:
    tarball = "https://codeload.github.com/%s/%s/tar.gz/refs/heads/%s" % (owner, repo, branch)
    req = urllib.request.Request(tarball)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    tmp = Path(tempfile.mkdtemp(prefix="skillcli-"))
    try:
        archive = tmp / "src.tar.gz"
        with urllib.request.urlopen(req, timeout=90) as r, archive.open("wb") as f:
            shutil.copyfileobj(r, f)
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            root = members[0].name.split("/")[0] if members else None
            wanted = root if not sub else "%s/%s" % (root, sub.strip("/"))
            picked = [m for m in members if m.name == wanted or m.name.startswith(wanted + "/")]
            if not picked:
                die("path %r not found in %s/%s@%s" % (sub, owner, repo, branch))
            tf.extractall(tmp / "out", members=picked, filter="data")
        src = tmp / "out" / wanted
        if not (src / "SKILL.md").is_file():
            die("SKILL.md not found at %r in %s/%s@%s" % (sub or ".", owner, repo, branch))
        shutil.copytree(src, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _github_commit(owner, repo, branch)


def cmd_install(args: argparse.Namespace) -> None:
    source = args.source
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    meta: dict = {"installed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}

    m = GITHUB_URL.match(source)
    if m and not Path(source).exists():
        owner = m.group("owner")
        repo = m.group("repo")
        branch = m.group("branch") or "main"
        sub = m.group("sub") or ""
        name = args.name or Path(sub).name or repo
        meta.update({"source_type": "github", "source": source, "branch": branch, "sub": sub})
    elif Path(source).expanduser().is_dir():
        src = Path(source).expanduser().resolve()
        if not (src / "SKILL.md").is_file():
            die("no SKILL.md in %s" % src)
        name = args.name or src.name
        meta.update({"source_type": "local", "source": str(src)})
    else:
        die("source must be a local directory or a github URL: %s" % source)

    dest = SKILLS_DIR / name
    if dest.exists() and not args.force:
        die("%s already exists, pass --force to overwrite" % dest)
    if args.dry_run:
        out("would install %s -> %s" % (source, dest))
        return

    if dest.exists():
        backup = TRASH_DIR / ("%s-%s" % (name, time.strftime("%Y%m%d%H%M%S")))
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(backup))
        out("previous copy moved to %s" % backup)

    if meta["source_type"] == "github":
        sha = _fetch_github(m.group("owner"), m.group("repo"), meta["branch"], meta["sub"], dest)
        meta["commit"] = sha
    else:
        shutil.copytree(Path(meta["source"]), dest)

    (dest / ".metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out("installed %s -> %s" % (name, dest))
    for status, msg in check(dest):
        if status == FAIL:
            out("  %s %s" % (status, msg))

    if not args.json_only and name == "docx-preferences":
        out("note: docx-preferences is meant to be edited by its user")


def cmd_uninstall(args: argparse.Namespace) -> None:
    target = resolve(args.name)
    if args.dry_run:
        out("would move %s to %s" % (target, TRASH_DIR))
        return
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    backup = TRASH_DIR / ("%s-%s" % (target.name, time.strftime("%Y%m%d%H%M%S")))
    shutil.move(str(target), str(backup))
    out("moved %s to %s" % (target.name, backup))
    out("restore with: move it back, or re-run install")


def cmd_info(args: argparse.Namespace) -> None:
    target = resolve(args.name)
    fm, body = read_frontmatter(target / "SKILL.md")
    out("directory : %s" % target)
    out("name      : %s" % (fm or {}).get("name"))
    out("created   : %s" % (fm or {}).get("agent_created"))
    files = [p for p in target.rglob("*") if p.is_file()]
    out("files     : %d (%.1f KB)" % (len(files), sum(p.stat().st_size for p in files) / 1024.0))
    for p in sorted(files):
        out("   %s" % p.relative_to(target))
    meta = target / ".metadata.json"
    if meta.is_file():
        data = json.loads(meta.read_text(encoding="utf-8"))
        out("source    : %s (%s)" % (data.get("source"), data.get("source_type")))
        if data.get("commit"):
            out("commit    : %s" % data["commit"][:12])
    out("")
    out("description:")
    out("  " + " ".join((fm or {}).get("description", "").split()))


def cmd_pack(args: argparse.Namespace) -> None:
    target = resolve(args.name)
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    zip_path = outdir / ("%s-%s.zip" % (target.name, args.version or time.strftime("%Y%m%d")))

    failures = [m for s, m in check(target) if s == FAIL]
    if failures and not args.force:
        die("validation failed, fix these first: " + "; ".join(failures))

    wrote = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(target.rglob("*")):
            if not p.is_file():
                continue
            if p.name == ".metadata.json" and not args.with_metadata:
                continue
            arc = "%s/%s" % (target.name, p.relative_to(target).as_posix())
            z.write(p, arc)
            wrote.append(arc)
    out("packed %d file(s) -> %s" % (len(wrote), zip_path))
    for a in wrote:
        out("   " + a)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skillcli",
        description="Manage WorkBuddy skills in %s" % SKILLS_DIR,
    )
    p.add_argument("--skills-dir", help="override the skills directory")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", help="list installed skills")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("validate", help="check frontmatter and layout")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("install", help="install from a local dir or github URL")
    s.add_argument("source")
    s.add_argument("--name")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--json-only", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("uninstall", help="move a skill to .trash")
    s.add_argument("name")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_uninstall)

    s = sub.add_parser("info", help="show one skill in detail")
    s.add_argument("name")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("pack", help="zip a skill for distribution")
    s.add_argument("name")
    s.add_argument("-o", "--outdir", default="dist")
    s.add_argument("--version")
    s.add_argument("--with-metadata", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_pack)
    return p


def main() -> None:
    global SKILLS_DIR, TRASH_DIR
    args = build_parser().parse_args()
    if getattr(args, "skills_dir", None):
        SKILLS_DIR = Path(args.skills_dir).expanduser().resolve()
        TRASH_DIR = SKILLS_DIR / ".trash"
    args.func(args)


if __name__ == "__main__":
    main()
