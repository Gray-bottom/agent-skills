---
name: md-to-deliverable-docx
description: Converts Markdown content written in the conversation into a deliverable Word (.docx) file with pandoc and a user-supplied reference template. This skill should be used when the user asks for a report, paper, lab write-up, coursework answer, or any assignment to be produced as a Word document, or says 转Word / 导出Word / 交付Word / 输出成文档. It owns the conversion route, the reference-template handshake, CJK path handling, and the known LaTeX-math and raw-HTML failure modes.
agent_created: true
---

# Markdown 转可交付 Word

## 用途

把会话里写好的 Markdown 正文转成可交付的 .docx。本 skill 只负责转换机制，不负责内容质量与文风；文风约束属于偏好层。

## 前置：先取参考模板

参考模板决定字体、字号、行距、标题编号与表格样式，必须由使用者提供。

1. 每次转换前，向使用者要参考模板的绝对路径。
2. 使用者未提供时，停下来等，不要用 pandoc 默认样式硬出，也不要猜路径或回退到任何历史目录。
3. 拿到路径后确认文件存在；不存在就把路径报给使用者。
4. 如果使用者另外维护了偏好层（例如单独一个 `docx-preferences` 技能，存放命名规则、版式默认值、文风禁用清单），先读它，用它回答本文档需要向使用者确认的默认值。没有偏好层时按通用默认走。

## 路线选择

默认走直连。两条路线的能力差异如下，据此判断，不要靠感觉。

| 源文件内容 | 结论 |
| --- | --- |
| LaTeX 公式（`$...$`、`$$...$$`） | 必须直连 md→docx |
| 原始 HTML `<sub>` `<sup>` `<u>` | 先把标签改写为原生语法 `~x~` / `^x^`，再走直连 |
| 其他情况 | 直连 md→docx |

不要使用两段式 md→html→docx。它保留 HTML 特性，但代价是公式全废：行内公式被拍成纯文本（`$E=mc^2$` 变成 `E = mc2`），行间公式与分数以原始 TeX 字符串留在正文里，Word 原生公式块数为零。

物理、数学、统计、运筹、经济这类含公式的内容，一律直连。

## 命令

直连导出：

```
pandoc "<in.md>" -o "<out.docx>" --reference-doc "<reference.docx>"
```

源文件用到 `==高亮==`、HTML 颜色 span 或 HTML `<img>` 时，追加聚合过滤器：

```
--lua-filter "<pandoc-docx-template 目录>/markdown-to-docx.lua"
```

该过滤器不随本 skill 分发。本机没有它时，上述三类特性会被静默忽略，改用原生 Markdown 语法表达。

## 中文路径

pandoc 处理中文路径有编码风险。操作顺序固定为：把源 md 复制成 ASCII 文件名到临时目录（如 `D:\Temp`），在临时目录转换，再把产物复制回工作区的目标文件名。

不要用 PowerShell 的 here-string 传内联 Python 或脚本，引号会被剥掉导致语法错误；需要脚本时先写成 .py 文件再执行。

## 交付

1. 转换后确认输出文件存在且大小非零。
2. 不跑自动体检，不做结构断言。把文件路径交给使用者，由使用者自己打开核对。只有 pandoc 报错或输出文件缺失时，才报告异常。
3. 保留 md 源文件并一并交付，便于使用者自行修改后重新转换。
4. 不在交付消息里罗列本轮做过哪些处理。

## 已知失败模式

- **公式变成乱码或原始 TeX**：说明走了两段式管线，改直连即可。
- **上下标丢失**：直连会吞掉原始 HTML 的 `<sub>` `<sup>`，改写为 `~x~` / `^x^` 后重新导出。
- **图片、题注、代码块、脚注、表格**：两条路线表现一致，无需特殊处理。`![alt](path "title")` 的 title 会成为题注。
- **预览**：本机没有 LibreOffice 与 pdftoppm，不要承诺提供 PDF 预览或转图。
- **使用者明确要求核对 docx 结构时才采用**：模板自带的 heading 样式 id 是数字（形如 `10` / `20` / `3`），按 Heading1 之类的名字统计会误判为零；加粗标签在 XML 里写作 `<w:b />`（带一个空格），用 `<w:b/>` 匹配会误判成完全没有加粗；三线表要 `w:tblStyle` 指向 `Table`、`tblLook` 带 `firstRow="1"`、首行含 `<w:tblHeader/>` 三者齐备，缺中间那条 0.5pt 线画不出来。
