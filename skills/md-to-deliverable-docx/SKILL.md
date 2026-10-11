---
name: md-to-deliverable-docx
description: Converts Markdown content written in the conversation into a deliverable Word (.docx) file with pandoc and a user-supplied reference template. This skill should be used when the user asks for a report, paper, lab write-up, coursework answer, or any assignment to be produced as a Word document, or says 转Word / 导出Word / 交付Word / 输出成文档. It owns the pandoc prerequisite check, the reference-template handshake, the conversion route, CJK path handling, and the known LaTeX-math and raw-HTML failure modes.
agent_created: true
---

# Markdown 转可交付 Word

## 用途

把会话里写好的 Markdown 正文转成可交付的 .docx。本 skill 只负责转换机制，不负责内容质量与文风；文风约束属于偏好层。

## 前置条件

转换前先跑 `pandoc --version`。本 skill 实测于 pandoc 3.10，低于 2.19 的版本未验证。

pandoc 缺失时停下来，告知使用者要先安装（官方安装页 pandoc.org/installing，Windows 上也可用 `winget install --id JohnMacFarlane.Pandoc`），不要改用其他工具顶替。

只依赖 pandoc，不需要 LibreOffice，也不要承诺提供 PDF 预览或成品截图。

## 先取参考模板

参考模板是一个 .docx 文件。pandoc 只从它读取样式定义，包括字体、字号、行距、各级标题样式和表格样式，不读它的正文内容。成品长什么样由它决定。

1. 每次转换前，向使用者要参考模板的绝对路径。
2. 使用者未提供时停下来等。不要用 pandoc 内置默认样式硬出，也不要猜路径或回退到历史目录。
3. 使用者说没有模板时，说明最小模板怎么造：用 Word 新建一个空文档，把标题 1/2/3、正文、表格样式按需要设好，另存为 .docx，这个文件就是模板。学校或单位下发的课程模板、公文模板同样可以直接拿来用。
4. 拿到路径后确认文件存在，不存在就把路径报给使用者。
5. 如果使用者另外维护了偏好层（例如单独一个 `docx-preferences` 技能，存放命名规则、版式默认值、文风禁用清单），先读它，用它回答本文档需要向使用者确认的默认值。没有偏好层时按通用默认走：产物写到工作区根目录，与源 md 同名，不加封面页与目录。

## 路线选择

默认走直连。两条路线的能力差异如下，据此判断，不要靠感觉。

| 源文件内容 | 结论 |
| --- | --- |
| LaTeX 公式（`$...$`、`$$...$$`） | 必须直连 md→docx |
| 原始 HTML `<sub>` `<sup>` `<u>` | 先把标签改写为原生语法 `~x~` / `^x^`，再走直连 |
| 其他情况 | 直连 md→docx |

不要使用两段式 md→html→docx。它保留 HTML 特性，代价是公式全废：行内公式被拍成纯文本（`$E=mc^2$` 变成 `E = mc2`），行间公式与分数以原始 TeX 字符串留在正文里，Word 原生公式块数为零。

物理、数学、统计、运筹、经济这类含公式的内容，一律直连。

## 命令

直连导出：

```
pandoc "<in.md>" -o "<out.docx>" --reference-doc "<reference.docx>"
```

论文与实验报告通常还要目录，加 `--toc`。使用者已经在正文里手写了「一、二、三」或「3.1」这类编号时，不要加 `--number-sections`，会被 Word 再自动编一遍。

源文件用到 `==高亮==`、HTML 颜色 span 或 HTML `<img>` 时，追加聚合过滤器：

```
--lua-filter "<路径>/markdown-to-docx.lua"
```

该过滤器不随本 skill 分发，来源是 Achuan-2 的 pandoc_docx_template 仓库。本机没有它时，上述三类特性会被静默忽略，改用原生 Markdown 语法表达。

## 中文路径与图片

pandoc 处理中文路径有编码风险。操作顺序固定为：把源 md 复制成 ASCII 文件名到临时目录（如 `D:\Temp`），在临时目录转换，再把产物复制回工作区的目标文件名。

源 md 用相对路径引用图片时，必须把它引用的目录一并复制过去。只复制 md 会断掉图片链接。更省事的做法是先把图片路径改写成绝对路径，转换完再改回来。

不要用 PowerShell 的 here-string 传内联 Python 或脚本，引号会被剥掉导致语法错误。需要脚本时先写成 .py 文件再执行。

## 走通一遍

输入 `D:\Temp\r.md`：

```markdown
# 标题

行内公式 $E = mc^2$，以及一个表格：

| 项 | 值 |
| --- | --- |
| a | 1 |
```

命令：

```
pandoc "D:\Temp\r.md" -o "D:\Temp\r.docx" --reference-doc "D:\templates\report.docx"
```

预期：`r.docx` 生成且大小非零；打开后标题套上模板里的标题样式，公式是 Word 原生公式（可以点进去编辑），表格是三线表，前提是模板里的 `Table` 样式被设成了三线表。

## 交付

1. 转换后确认输出文件存在且大小非零。
2. 不跑自动体检，不做结构断言。把文件路径交给使用者，由使用者自己打开核对。只有 pandoc 报错或输出文件缺失时，才报告异常。
3. 保留 md 源文件并一并交付，便于使用者自行修改后重新转换。
4. 不在交付消息里罗列本轮做过哪些处理。

## 已知失败模式

- 公式变成乱码或留成原始 TeX：说明走了两段式管线，改直连。
- 上下标丢失，或 HTML 标签本身留在正文里：直连会吞掉原始 HTML 的 `<sub>` `<sup>`，改写为 `~x~` / `^x^` 后重新导出。
- 需要 PDF 预览或成品截图：本机没有对应工具，不要承诺。

深度排查、docx 结构核对、LaTeX 宏的覆盖边界，见 [references/troubleshooting.md](references/troubleshooting.md)。遇到异常，或使用者要求核对 docx 内部结构时再读它。
