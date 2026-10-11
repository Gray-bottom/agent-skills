# agent-skills

A few agent skills, plus a CLI that manages them across agents.

Nothing here is tied to one product. Every skill is a directory with a `SKILL.md`
in it, and every agent that discovers skills from a `<agent-home>/skills/`
folder can use the same files.

## Contents

| Path | What it is |
| --- | --- |
| `skills/md-to-deliverable-docx/` | Turn Markdown written in a chat into a deliverable Word file with pandoc. Generic, no personal preferences baked in |
| `tools/skillcli.py` | CLI for `list`, `validate`, `install`, `uninstall`, `info` and `pack` |

## Where skills live

| Agent | Global | Project |
| --- | --- | --- |
| WorkBuddy | `~/.workbuddy/skills` | `.workbuddy/skills` |
| Claude Code | `~/.claude/skills` | `.claude/skills` |
| Codex | `~/.codex/skills` | `.agents/skills` |
| OpenClaw | `~/.openclaw/skills` | `.agents/skills` |
| Gemini CLI | `~/.gemini/skills` | `.agents/skills` |

## Install a skill

Copy it into whichever directory above matches your agent:

```bash
git clone https://github.com/Gray-bottom/agent-skills.git
cp -r agent-skills/skills/md-to-deliverable-docx ~/.claude/skills/
```

Or with the official CLI, which installs from a GitHub URL:

```bash
npx @tomaskral/skillmanager@latest install \
  https://github.com/Gray-bottom/agent-skills/tree/main/skills/md-to-deliverable-docx \
  --agent claude
```

## skillcli

Python 3.9 or newer, standard library only, no dependencies.

```bash
python tools/skillcli.py list                    # every known agent whose skills dir exists
python tools/skillcli.py list --json
python tools/skillcli.py validate                # all skills in scope
python tools/skillcli.py validate md-to-deliverable-docx
python tools/skillcli.py info md-to-deliverable-docx
python tools/skillcli.py install ./some-skill --agent claude --dry-run
python tools/skillcli.py install https://github.com/owner/repo/tree/main/skills/foo --agent workbuddy
python tools/skillcli.py uninstall some-skill --agent codex
python tools/skillcli.py pack md-to-deliverable-docx -o dist
```

`install` requires an explicit target, either `--agent` or `--skills-dir`. Everything
else falls back to every agent directory that already exists, and refuses to act when
a skill name appears in more than one of them.

Set `GITHUB_TOKEN` to install from private repositories.

`uninstall` moves the skill to `<skills-dir>/.trash/<name>-<timestamp>` instead of
deleting it, so an accidental removal is recoverable.

`pack` refuses to build a zip when validation fails; pass `--force` to override.

### Why not only use skillmanager

The official [`@tomaskral/skillmanager`](https://github.com/kadel/skillmanager) is
good at install and update, but its `--agent` list stops at `claude`, `openclaw`,
`codex` and `gemini`, and it has no validation or packaging. `skillcli` covers the
same agents plus WorkBuddy, and adds `validate`, `info` and `pack`. They can sit side
by side without interfering.

## What md-to-deliverable-docx is for

Converting Markdown into a `.docx` with pandoc, and getting the awkward cases right.
Three rules carry most of the value:

1. The reference template comes from the user. Ask for its path before converting.
   If it is not given, stop rather than falling back to default styles.
2. Convert directly, `pandoc in.md -o out.docx --reference-doc <template>`.
   Routing through HTML (`md -> html -> docx`) silently destroys LaTeX math: inline
   formulas collapse to plain text and display formulas stay in the document as raw
   TeX. Any document containing math must avoid that route.
3. Direct conversion drops raw HTML `<sub>`, `<sup>` and `<u>`. Use the native
   `~x~` and `^x^` syntax instead.

Full rules, including the CJK path workaround and the known failure modes, are in
`skills/md-to-deliverable-docx/SKILL.md`.

## Not included

- Reference templates are not bundled. Bring your own `.docx`.
- The `markdown-to-docx.lua` filter from
  [Achuan-2/pandoc_docx_template](https://github.com/Achuan-2/pandoc_docx_template)
  is not bundled either. Without it, `==highlight==`, HTML colour spans and HTML
  `<img>` tags are ignored, so use native Markdown syntax for those.

## License

MIT, see [LICENSE](LICENSE).
