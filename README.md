# agent-skills

一批 agent 技能，外加一个跨 agent 管理它们的命令行工具。

这里的东西不绑定任何特定产品。每个技能就是一个含 `SKILL.md` 的目录，任何从 `<agent 目录>/skills/` 发现技能的 agent 都能直接用同一批文件。

## 目录内容

| 路径 | 说明 |
| --- | --- |
| `skills/md-to-deliverable-docx/` | 把对话里写好的 Markdown 用 pandoc 转成可交付的 Word 文档。通用层，不掺个人偏好 |
| `tools/skillcli.py` | 命令行工具，提供 `list`、`validate`、`install`、`uninstall`、`info`、`pack` |

## 技能目录位置

| Agent | 全局 | 项目级 |
| --- | --- | --- |
| WorkBuddy | `~/.workbuddy/skills` | `.workbuddy/skills` |
| Claude Code | `~/.claude/skills` | `.claude/skills` |
| Codex | `~/.codex/skills` | `.agents/skills` |
| OpenClaw | `~/.openclaw/skills` | `.agents/skills` |
| Gemini CLI | `~/.gemini/skills` | `.agents/skills` |

## 安装技能

拷进上表里对应 agent 的目录即可：

```bash
git clone https://github.com/Gray-bottom/agent-skills.git
cp -r agent-skills/skills/md-to-deliverable-docx ~/.claude/skills/
```

也可以用官方 CLI，它支持从 GitHub 地址安装：

```bash
npx @tomaskral/skillmanager@latest install \
  https://github.com/Gray-bottom/agent-skills/tree/main/skills/md-to-deliverable-docx \
  --agent claude
```

## 使用 skillcli

需要 Python 3.9 以上，只用标准库，无依赖。

```bash
python tools/skillcli.py list                    # 列出所有已存在技能目录的 agent
python tools/skillcli.py list --json
python tools/skillcli.py validate                # 校验当前范围内的全部技能
python tools/skillcli.py validate md-to-deliverable-docx
python tools/skillcli.py info md-to-deliverable-docx
python tools/skillcli.py install ./some-skill --agent claude --dry-run
python tools/skillcli.py install https://github.com/owner/repo/tree/main/skills/foo --agent workbuddy
python tools/skillcli.py uninstall some-skill --agent codex
python tools/skillcli.py pack md-to-deliverable-docx -o dist
```

`--agent` 和 `--skills-dir` 放在子命令前后都可以。

目标目录的解析顺序：`--skills-dir`、`--agent` 加 `--scope`、环境变量 `SKILLS_DIR` 或 `SKILLS_AGENT`、所有已存在的 agent 目录，最后是报错提示。`install` 必须给出明确目标。除 `install` 之外的命令，如果一个技能名在多个目录里同时存在，工具会拒绝执行并列出候选，避免改错地方。

从私有仓库安装时设置 `GITHUB_TOKEN` 环境变量。

`uninstall` 把技能移进 `<技能目录>/.trash/<名称>-<时间戳>`，不直接删除，误删可以捞回来。

`pack` 在校验不通过时拒绝打包，除非显式加 `--force`。

### 为什么不只用官方 skillmanager

官方 [`@tomaskral/skillmanager`](https://github.com/kadel/skillmanager) 擅长安装与更新，但它的 `--agent` 只到 `claude`、`openclaw`、`codex`、`gemini` 四个，也没有校验与打包。`skillcli` 覆盖同一批 agent 并加上 WorkBuddy，另外补了 `validate`、`info`、`pack`。两者可以并存，互不干扰。

## md-to-deliverable-docx 解决什么

把 Markdown 转成 `.docx`，重点是把几个容易翻车的地方处理对。三条规则撑起大部分价值：

1. 参考模板由使用者提供。转换前先问路径，没给就停下来，不要退回默认样式硬出。
2. 默认走直连，`pandoc in.md -o out.docx --reference-doc <模板>`。绕道 HTML 的两段式管线（`md -> html -> docx`）会静默毁掉 LaTeX 公式：行内公式塌成纯文本，行间公式以原始 TeX 留在正文里。含公式的文档一律不能走那条路。
3. 直连会丢掉原始 HTML 的 `<sub>`、`<sup>`、`<u>`，改用原生 `~x~` 与 `^x^` 语法。

完整规则在 `skills/md-to-deliverable-docx/SKILL.md`，含中文路径的绕行办法和已知失败模式。

## 不含的内容

- 不附带参考模板。用你自备的 `.docx`。
- 不附带 [Achuan-2/pandoc_docx_template](https://github.com/Achuan-2/pandoc_docx_template) 里的 `markdown-to-docx.lua` 过滤器。没有它时，`==高亮==`、HTML 颜色 span 和 HTML `<img>` 会被忽略，这几处改用原生 Markdown 语法。

## 许可

MIT，见 [LICENSE](LICENSE)。
