# workbuddy-skills

WorkBuddy 本地技能合集，附带一个管理这些技能的命令行工具。

A collection of local skills for WorkBuddy, plus a small CLI that manages them.

## 内容 / Contents

| 路径 | 说明 |
| --- | --- |
| `skills/md-to-deliverable-docx/` | 把会话里写好的 Markdown 转成可交付的 Word 文档。通用层，不含任何个人偏好，可直接复用 |
| `tools/skillcli.py` | 管理 `~/.workbuddy/skills` 的命令行工具：`list` / `validate` / `install` / `uninstall` / `info` / `pack` |

## 为什么需要 skillcli

官方的 [`@tomaskral/skillmanager`](https://github.com/kadel/skillmanager) 只能把技能装进 `claude`、`openclaw`、`codex`、`gemini` 这几个 agent 的目录，`--agent` 里没有 `workbuddy`，因此管不了 `~/.workbuddy/skills`。skillcli 补上这一环，并额外提供 frontmatter 校验与打包。

只用 Python 标准库，无需安装依赖。

## 安装技能

直接放进技能目录：

```bash
git clone https://github.com/<owner>/workbuddy-skills.git
cp -r workbuddy-skills/skills/md-to-deliverable-docx ~/.workbuddy/skills/
```

或者用官方 CLI 装到别的 agent：

```bash
npx @tomaskral/skillmanager@latest install \
  https://github.com/<owner>/workbuddy-skills/tree/main/skills/md-to-deliverable-docx \
  --agent claude
```

## 使用 skillcli

需要 Python 3.9 以上。技能目录默认 `~/.workbuddy/skills`，可用 `--skills-dir` 或环境变量 `WORKBUDDY_SKILLS_DIR` 覆盖。

```bash
python tools/skillcli.py list                    # 列出已装技能
python tools/skillcli.py list --json             # 机器可读
python tools/skillcli.py validate                # 校验全部技能的 frontmatter 与结构
python tools/skillcli.py validate some-skill     # 只校验一个
python tools/skillcli.py info some-skill         # 详情、文件清单、来源与 commit
python tools/skillcli.py install ./some-skill --dry-run
python tools/skillcli.py install https://github.com/owner/repo/tree/main/skills/foo
python tools/skillcli.py uninstall some-skill    # 移入 .trash，不直接删除
python tools/skillcli.py pack md-to-deliverable-docx -o dist
```

安装私有仓库时设置 `GITHUB_TOKEN` 环境变量。`uninstall` 把技能移到 `<skills-dir>/.trash/` 并打上时间戳，而不是删掉。

## md-to-deliverable-docx 解决什么

把 Markdown 正文用 pandoc 转成 `.docx`，核心是三条判断：

1. 参考模板由使用者提供，转换前必须拿到路径；没有就停下来等，不用默认样式硬出。
2. 默认走**直连** `pandoc in.md -o out.docx --reference-doc <模板>`。两段式 `md→html→docx` 会把 LaTeX 公式拍成纯文本或以原始 TeX 留在正文里，含公式的文档一律不能走。
3. 直连会静默丢掉原始 HTML 的 `<sub>` `<sup>` `<u>`，改用原生 `~x~` / `^x^` 语法。

完整规则见 `skills/md-to-deliverable-docx/SKILL.md`。

## 不含的内容

- 参考模板不随本仓库分发，需使用者自备。本机自用的那套来自 [Achuan-2/pandoc_docx_template](https://github.com/Achuan-2/pandoc_docx_template)。
- 该仓库的 `markdown-to-docx.lua` 过滤器同样未包含。需要它支持的 `==高亮==`、HTML 颜色 span、HTML `<img>` 时请自行获取。

## 许可

尚未指定。若希望他人自由复用，请补充一个 LICENSE 文件。
