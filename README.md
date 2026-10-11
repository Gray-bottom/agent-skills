# agent-skills

这个仓库目前主要是一件事：一个把 Markdown 转成可交付 Word 文档的技能。仓库里另外附带一个小工具，用来跨 agent 管理技能，它服务的是技能本身。

## md-to-deliverable-docx

把对话里写好的 Markdown 用 pandoc 转成 `.docx`。会调 pandoc 不难，这个技能值钱的地方是几个容易翻车的点被写成了硬规则。

**参考模板由使用者提供。** 模板决定字体、字号、行距、标题编号与表格样式，转换前必须先拿到路径。拿不到就停下来，不要退回默认样式硬出，也不要猜路径或沿用历史目录。

**默认走直连**，`pandoc in.md -o out.docx --reference-doc <模板>`。绕道 HTML 的两段式管线（`md -> html -> docx`）会静默毁掉 LaTeX 公式：行内公式塌成纯文本，行间公式以原始 TeX 留在正文里，Word 原生公式块为零。含公式的文档一律不能走那条路。

**直连会丢掉原始 HTML 的 `<sub>`、`<sup>`、`<u>`。** 这几处改用原生 `~x~` 与 `^x^` 语法。

完整规则在 [`skills/md-to-deliverable-docx/SKILL.md`](skills/md-to-deliverable-docx/SKILL.md)，含中文路径的绕行办法和已知失败模式。

### 安装

拷进对应 agent 的全局或项目级目录即可：

| Agent | 全局 | 项目级 |
| --- | --- | --- |
| WorkBuddy | `~/.workbuddy/skills` | `.workbuddy/skills` |
| Claude Code | `~/.claude/skills` | `.claude/skills` |
| Codex | `~/.codex/skills` | `.agents/skills` |
| OpenClaw | `~/.openclaw/skills` | `.agents/skills` |
| Gemini CLI | `~/.gemini/skills` | `.agents/skills` |

```bash
git clone https://github.com/Gray-bottom/agent-skills.git
cp -r agent-skills/skills/md-to-deliverable-docx ~/.claude/skills/
```

也可以用官方 CLI 从 GitHub 地址安装：

```bash
npx @tomaskral/skillmanager@latest install \
  https://github.com/Gray-bottom/agent-skills/tree/main/skills/md-to-deliverable-docx \
  --agent claude
```

### 需要自备

- 参考模板。任意 `.docx` 都行，你要的字体和版式在它里面定义。
- 用到 `==高亮==`、HTML 颜色 span 或 HTML `<img>` 时，另取 [Achuan-2/pandoc_docx_template](https://github.com/Achuan-2/pandoc_docx_template) 的 `markdown-to-docx.lua`。没有它这几处会被静默忽略，改用原生 Markdown 语法表达即可。

## 附带的工具：skillcli

`tools/skillcli.py` 是一个跨 agent 的技能管理 CLI。写它有两个原因：官方 [`@tomaskral/skillmanager`](https://github.com/kadel/skillmanager) 的 `--agent` 只认 `claude`、`openclaw`、`codex`、`gemini`，没有 `workbuddy`，管不到 `~/.workbuddy/skills`；它也没有校验与打包。

子命令是 `list`、`validate`、`install`、`uninstall`、`info`、`pack`。只用 Python 标准库，无依赖。`--agent` 与 `--skills-dir` 放在子命令前后都可以。

```bash
python tools/skillcli.py list
python tools/skillcli.py validate
python tools/skillcli.py install ./some-skill --agent claude --dry-run
python tools/skillcli.py install https://github.com/owner/repo/tree/main/skills/foo --agent workbuddy
python tools/skillcli.py uninstall some-skill --agent codex
python tools/skillcli.py pack md-to-deliverable-docx -o dist
```

目标目录的解析顺序：`--skills-dir`、`--agent` 加 `--scope`、环境变量 `SKILLS_DIR` 或 `SKILLS_AGENT`、所有已存在的 agent 目录，最后报错。`install` 必须给出明确目标；其余命令遇到同名技能分布在多个目录时会拒绝执行并列出候选，避免改错地方。

从私有仓库安装时设置 `GITHUB_TOKEN`。`uninstall` 把技能移进 `<技能目录>/.trash/<名称>-<时间戳>`，不直接删除。`pack` 在校验不通过时拒绝打包，除非加 `--force`。

## 许可

MIT，见 [LICENSE](LICENSE)。
