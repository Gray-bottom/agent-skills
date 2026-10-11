#!/usr/bin/env python3
"""skillcli - list, validate, install, pack and remove agent skills.

Agent-agnostic. A "skill" is a directory containing SKILL.md with YAML
frontmatter (name, description, and optionally agent_created).

Target resolution, in order:
  1. --skills-dir PATH
  2. --agent NAME [--scope global|project]
  3. environment SKILLS_DIR, or SKILLS_AGENT with SKILLS_SCOPE
  4. every known agent whose skills directory already exists
     (commands that act on one skill need the name to be unambiguous)
  5. otherwise, error out and ask for an explicit target

Read-only on anything outside the target skills directory. `uninstall` moves a
skill into <skills-dir>/.trash with a timestamp instead of deleting it.
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
import urllib.request
import zipfile
from pathlib import Path

# Global and project skills directories per agent. Mirrors the layout used by
# the official skillmanager CLI so the two tools stay compatible.
AGENTS: dict[str, dict[str, str]] = {
    "workbuddy": {"global": "~/.workbuddy/skills", "project": ".workbuddy/skills"},
    "claude": {"global": "~/.claude/skills", "project": ".claude/skills"},
    "codex": {"global": "~/.codex/skills", "project": ".agents/skills"},
    "openclaw": {"global": "~/.openclaw/skills", "project": ".agents/skills"},
    "gemini": {"global": "~/.gemini/skills", "project": ".agents/skills"},
}

GITHUB_URL = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)"
    r"(?:\.git)?(?:/tree/(?P<branch>.+?))?/(?P<sub>.+?)/?$"
)

OK = "  ok  "
WARN = " warn "
FAIL = " FAIL "


def out(msg: str = "") -> None:
    sys.stdout.write(msg + "\n")


def die(msg: str) -> None:
    sys.stderr.write("error: " + msg + "\n")
    raise SystemExit(1)


def agent_dir(agent: str, scope: str = "global") -> Path:
    if agent not in AGENTS:
        die("unknown agent %r, known: %s" % (agent, ", ".join(sorted(AGENTS))))
    raw = AGENTS[agent][scope]
    if raw.startswith("~/"):
        return Path.home() / raw[2:]
    return (Path.cwd() / raw).resolve()


def roots(args: argparse.Namespace, for_install: bool = False) -> list[tuple[str, Path]]:
    """Return [(label, directory)] to operate on."""
    if getattr(args, "skills_dir", None):
        return [("explicit", Path(args.skills_dir).expanduser().resolve())]

    agent = getattr(args, "agent", None) or (
        None if for_install else os.environ.get("SKILLS_AGENT")
    )
    if agent:
        scope = getattr(args, "scope", None) or os.environ.get("SKILLS_SCOPE") or "global"
        return [("%s:%s" % (agent, scope), agent_dir(agent, scope))]

    if not for_install:
        env_dir = os.environ.get("SKILLS_DIR")
        if env_dir:
            return [("env", Path(env_dir).expanduser().resolve())]

    if for_install:
        die(
            "install needs an explicit target. Pass --agent NAME (known: %s) "
            "or --skills-dir PATH." % ", ".join(sorted(AGENTS))
        )

    found: list[tuple[str, Path]] = []
    for name in AGENTS:
        for scope in ("global", "project"):
            d = agent_dir(name, scope)
            if d.is_dir():
                found.append(("%s:%s" % (name, scope), d))
    if not found:
        die(
            "no skills directory found under any known agent. Pass --agent NAME "
            "or --skills-dir PATH."
        )
    return found


def iter_skills(rs: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for label, root in rs:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                items.append((label, d))
    return items


def valid_skills(rs: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    return [(l, d) for l, d in iter_skills(rs) if (d / "SKILL.md").is_file()]


def resolve(name: str, rs: list[tuple[str, Path]]) -> tuple[str, Path]:
    """Find one skill by directory name or by frontmatter name."""
    hits = [
        (label, d)
        for label, d in valid_skills(rs)
        if d.name == name
        or (read_frontmatter(d / "SKILL.md")[0] or {}).get("name") == name
    ]
    if not hits:
        die("no skill named %r in: %s" % (name, ", ".join(str(r) for _, r in rs)))
    if len(hits) > 1:
        die(
            "%r exists in several places, pin one with --agent or --skills-dir:\n  "
            + "\n  ".join("%s -> %s" % (l, d) for l, d in hits)
        )
    return hits[0]


def read_frontmatter(path: Path) -> tuple[dict | None, str]:
    """Parse the leading YAML block. Only the keys we care about are read, but
    folded (>) and literal (|) block scalars are supported because descriptions
    are often written that way."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, text

    fm: dict[str, str] = {}
    block = lines[1:end]
    i = 0
    while i < len(block):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", block[i])
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in {">", ">-", ">+", "|", "|-", "|+", ""}:
            collected: list[str] = []
            i += 1
            while i < len(block):
                nxt = block[i]
                if nxt.strip() == "" or re.match(r"^\s", nxt):
                    collected.append(nxt.strip())
                    i += 1
                    continue
                break
            joiner = "\n" if val.startswith("|") else " "
            fm[key] = joiner.join(x for x in collected if x)
        else:
            fm[key] = val.strip('"').strip("'")
            i += 1
    return fm, "\n".join(lines[end + 1 :])


def check(skill: Path) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        return [(FAIL, "SKILL.md missing")]

    fm, body = read_frontmatter(skill_md)
    if fm is None:
        return [(FAIL, "YAML frontmatter missing or unterminated")]

    if not fm.get("name"):
        results.append((FAIL, "frontmatter has no name"))
    elif fm["name"] != skill.name:
        results.append((FAIL, "name %r does not match directory %r" % (fm["name"], skill.name)))
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
        results.append((WARN, "agent_created not true, the model cannot edit it later"))
    else:
        results.append((OK, "agent_created set"))

    if len(body.strip()) < 50:
        results.append((WARN, "body is nearly empty"))
    else:
        results.append((OK, "body present (%d words)" % len(body.split())))
    return results


def cmd_list(args: argparse.Namespace) -> None:
    rs = roots(args)
    if args.json:
        payload = []
        for label, d in valid_skills(rs):
            fm, _ = read_frontmatter(d / "SKILL.md")
            files = [p for p in d.rglob("*") if p.is_file()]
            payload.append(
                {
                    "agent": label,
                    "dir": str(d),
                    "name": (fm or {}).get("name"),
                    "description": (fm or {}).get("description"),
                    "agent_created": (fm or {}).get("agent_created"),
                    "files": len(files),
                    "bytes": sum(p.stat().st_size for p in files),
                }
            )
        out(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    shown = 0
    for label, root in rs:
        if not root.is_dir():
            continue
        out("%s  (%s)" % (label, root))
        entries = [
            d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(".")
        ]
        if not entries:
            out("  (empty)")
            out("")
            continue
        for d in entries:
            if not (d / "SKILL.md").is_file():
                out("  %-32s  [!] no SKILL.md" % d.name)
                shown += 1
                continue
            fm, _ = read_frontmatter(d / "SKILL.md")
            files = [p for p in d.rglob("*") if p.is_file()]
            desc = " ".join((fm or {}).get("description", "").split())
            flag = "" if (fm or {}).get("name") == d.name else "  [!] name mismatch"
            out(
                "  %-32s %2d file %6.1fK  %s%s"
                % (
                    d.name,
                    len(files),
                    sum(p.stat().st_size for p in files) / 1024.0,
                    desc[:60] + ("..." if len(desc) > 60 else ""),
                    flag,
                )
            )
            shown += 1
        out("")
    if shown == 0:
        out("nothing found in the directories above")


def cmd_validate(args: argparse.Namespace) -> None:
    rs = roots(args)
    targets = [resolve(args.name, rs)] if args.name else valid_skills(rs)
    if not targets:
        die("no skills to validate in: %s" % ", ".join(str(r) for _, r in rs))
    worst = 0
    for label, d in targets:
        out("%s  [%s]" % (d.name, label))
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
        with urllib.request.urlopen(req, timeout=120) as r, archive.open("wb") as f:
            shutil.copyfileobj(r, f)
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            if not members:
                die("empty archive from %s/%s@%s" % (owner, repo, branch))
            root = members[0].name.split("/")[0]
            wanted = root if not sub else "%s/%s" % (root, sub.strip("/"))
            picked = [
                m for m in members if m.name == wanted or m.name.startswith(wanted + "/")
            ]
            if not picked:
                die("path %r not found in %s/%s@%s" % (sub, owner, repo, branch))
            tf.extractall(tmp / "out", members=picked, filter="data")
        src = tmp / "out" / wanted
        if not (src / "SKILL.md").is_file():
            die("no SKILL.md at %r in %s/%s@%s" % (sub or ".", owner, repo, branch))
        shutil.copytree(src, dest)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _github_commit(owner, repo, branch)


def cmd_install(args: argparse.Namespace) -> None:
    source = args.source
    label, root = roots(args, for_install=True)[0]
    root.mkdir(parents=True, exist_ok=True)
    meta: dict = {"installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "agent": label}

    m = GITHUB_URL.match(source)
    local = Path(source).expanduser()

    if m and not local.is_dir():
        branch = m.group("branch") or "main"
        sub = m.group("sub") or ""
        name = args.name or Path(sub).name or m.group("repo")
        meta.update({"source_type": "github", "source": source, "branch": branch, "sub": sub})
    elif local.is_dir():
        src = local.resolve()
        if not (src / "SKILL.md").is_file():
            die("no SKILL.md in %s" % src)
        name = args.name or src.name
        meta.update({"source_type": "local", "source": str(src)})
    else:
        die("source must be a local directory or a github URL, got: %s" % source)

    dest = root / name
    if args.dry_run:
        action = "overwrite" if dest.exists() else "create"
        out("would %s %s -> %s" % (action, source, dest))
        return
    if dest.exists() and not args.force:
        die("%s already exists, pass --force to overwrite" % dest)

    if dest.exists():
        backup = root / ".trash" / ("%s-%s" % (name, time.strftime("%Y%m%d%H%M%S")))
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(backup))
        out("previous copy moved to %s" % backup)

    if meta["source_type"] == "github":
        meta["commit"] = _fetch_github(
            m.group("owner"), m.group("repo"), meta["branch"], meta["sub"], dest
        )
    else:
        shutil.copytree(Path(meta["source"]), dest)

    (dest / ".metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    out("installed %s -> %s" % (name, dest))
    problems = [msg for s, msg in check(dest) if s == FAIL]
    if problems:
        out("validation reported: " + "; ".join(problems))


def cmd_uninstall(args: argparse.Namespace) -> None:
    _, target = resolve(args.name, roots(args))
    trash = target.parent / ".trash"
    if args.dry_run:
        out("would move %s to %s" % (target, trash))
        return
    trash.mkdir(parents=True, exist_ok=True)
    backup = trash / ("%s-%s" % (target.name, time.strftime("%Y%m%d%H%M%S")))
    shutil.move(str(target), str(backup))
    out("moved %s to %s" % (target.name, backup))
    out("to restore, move it back out of .trash")


def cmd_info(args: argparse.Namespace) -> None:
    label, target = resolve(args.name, roots(args))
    fm, _ = read_frontmatter(target / "SKILL.md")
    out("directory : %s" % target)
    out("target    : %s" % label)
    out("name      : %s" % (fm or {}).get("name"))
    out("created   : agent_created=%s" % (fm or {}).get("agent_created"))
    files = [p for p in target.rglob("*") if p.is_file()]
    out(
        "files     : %d (%.1f KB)"
        % (len(files), sum(p.stat().st_size for p in files) / 1024.0)
    )
    for p in sorted(files):
        out("   %s" % p.relative_to(target).as_posix())
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
    _, target = resolve(args.name, roots(args))
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    zip_path = outdir / ("%s-%s.zip" % (target.name, args.version or time.strftime("%Y%m%d")))

    failures = [m for s, m in check(target) if s == FAIL]
    if failures and not args.force:
        die("validation failed, fix first (or pass --force): " + "; ".join(failures))

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
        description="Manage agent skills. Known agents: " + ", ".join(sorted(AGENTS)),
    )
    agent_help = "target agent: " + ", ".join(sorted(AGENTS))
    p.add_argument("--agent", "-a", help=agent_help)
    p.add_argument("--scope", choices=["global", "project"], help="default: global")
    p.add_argument("--skills-dir", help="explicit skills directory, overrides --agent")

    # The same three options are accepted after the subcommand as well. SUPPRESS
    # keeps an absent one from overwriting whatever the main parser already set.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--agent", "-a", default=argparse.SUPPRESS, help=agent_help)
    common.add_argument(
        "--scope", choices=["global", "project"], default=argparse.SUPPRESS, help="default: global"
    )
    common.add_argument(
        "--skills-dir", default=argparse.SUPPRESS, help="explicit skills directory, overrides --agent"
    )

    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", parents=[common], help="list skills across the resolved targets")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("validate", parents=[common], help="check frontmatter and layout")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser(
        "install", parents=[common], help="install from a local directory or github URL"
    )
    s.add_argument("source")
    s.add_argument("--name", help="override the installed directory name")
    s.add_argument("--force", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_install)

    s = sub.add_parser("uninstall", parents=[common], help="move a skill into .trash")
    s.add_argument("name")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_uninstall)

    s = sub.add_parser("info", parents=[common], help="show one skill in detail")
    s.add_argument("name")
    s.set_defaults(func=cmd_info)

    s = sub.add_parser("pack", parents=[common], help="zip a skill for distribution")
    s.add_argument("name")
    s.add_argument("-o", "--outdir", default="dist")
    s.add_argument("--version")
    s.add_argument("--with-metadata", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_pack)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
