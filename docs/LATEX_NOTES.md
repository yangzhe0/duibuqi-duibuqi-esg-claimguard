# LaTeX Notes

## 编译命令

```bash
cd latex
latexmk -xelatex -interaction=nonstopmode -halt-on-error MathModel.tex
```

## 输出文件

```text
latex/MathModel.pdf
```

当前 PDF 共 9 页。

## 已修改内容

已修改 `latex/gmcmthesis.cls` 第 149 行附近字体配置：

- `setmainfont`
- `setmonofont`
- `setsansfont`

上述字体配置已改为读取本地 `fonts/times.ttf`。

## 当前警告

LiSu/CJK 字体警告已通过本地 `fonts/STLiti.ttf` 处理。当前仅剩普通字形替代警告，主要原因是部分字体文件未提供完整粗体或斜体字形，不影响 PDF 生成。
