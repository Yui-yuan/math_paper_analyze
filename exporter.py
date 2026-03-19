"""输出 Markdown / LaTeX 文件"""

import re
from pathlib import Path
from typing import Optional
from datetime import datetime

from config import AppConfig
from reader import PaperDocument
from pipeline import PipelineResult

from rich.console import Console

console = Console()


def export_notes(
    paper: PaperDocument,
    result: PipelineResult,
    config: AppConfig,
) -> list:
    """
    导出笔记文件。

    Returns:
        生成的文件路径列表
    """
    output_dir = Path(config.output.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名（基于论文标题）
    safe_title = _sanitize_filename(paper.title)
    generated_files = []

    if "markdown" in config.output.format:
        md_path = output_dir / f"{safe_title}_notes.md"
        md_content = _build_markdown(paper, result, config)
        md_path.write_text(md_content, encoding='utf-8')
        generated_files.append(str(md_path))
        console.print(f"  Markdown: [green]{md_path}[/green]")

    if "latex" in config.output.format:
        tex_path = output_dir / f"{safe_title}_notes.tex"
        tex_content = _build_latex(paper, result, config)
        tex_path.write_text(tex_content, encoding='utf-8')
        generated_files.append(str(tex_path))
        console.print(f"  LaTeX:    [green]{tex_path}[/green]")

        if config.output.auto_compile_pdf:
            _compile_latex(tex_path)

    return generated_files


def append_qa_to_notes(
    notes_path: str,
    question: str,
    answer: str,
):
    """将研讨模式的 QA 追加到笔记文件"""
    path = Path(notes_path)
    if not path.exists():
        return

    content = path.read_text(encoding='utf-8')

    # 检查是否已经有研讨记录 section
    if "## 研讨记录" not in content:
        content += "\n\n---\n\n## 研讨记录\n"

    # 追加 QA
    qa_entry = f"\n### Q: {question}\n{answer}\n"
    content += qa_entry

    path.write_text(content, encoding='utf-8')


# ---- Markdown 构建 ----

def _build_markdown(
    paper: PaperDocument,
    result: PipelineResult,
    config: AppConfig,
) -> str:
    """构建 Markdown 格式的笔记"""
    parts = []

    # YAML frontmatter (Obsidian 友好)
    parts.append("---")
    parts.append(f"title: \"{paper.title}\"")
    if paper.authors:
        parts.append(f"authors: \"{paper.authors}\"")
    if config.domain:
        parts.append(f"domain: {config.domain}")
    parts.append(f"generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    parts.append(f"rounds: {result.rounds_completed}")
    parts.append("tags: [math-paper-notes, ai-generated]")
    parts.append("---\n")

    # 标题
    parts.append(f"# {paper.title}")
    meta_parts = []
    if paper.authors:
        meta_parts.append(f"作者: {paper.authors}")
    if config.domain:
        meta_parts.append(f"领域: {config.domain}")
    if meta_parts:
        parts.append("> " + " | ".join(meta_parts))
    parts.append("")

    # 主体内容
    # 如果 pipeline 结果已经按 layer 拆分好了，分别输出
    if result.layer1 and result.layer2:
        layers_to_output = config.output.layers

        if 1 in layers_to_output:
            parts.append(result.layer1)
            parts.append("")

        if 2 in layers_to_output:
            parts.append(result.layer2)
            parts.append("")

        if 3 in layers_to_output and result.layer3:
            parts.append(result.layer3)
            parts.append("")

        if result.appendix:
            parts.append(result.appendix)
            parts.append("")
    else:
        # 没有成功拆分，输出完整笔记
        parts.append(result.full_notes)

    return "\n".join(parts)


# ---- LaTeX 构建 ----

def _build_latex(
    paper: PaperDocument,
    result: PipelineResult,
    config: AppConfig,
) -> str:
    """构建 LaTeX 格式的笔记"""
    # 将 Markdown 转换为基础 LaTeX
    content = result.full_notes

    # 转换标题
    content = re.sub(r'^# (.+)$', r'\\section{\1}', content, flags=re.MULTILINE)
    content = re.sub(r'^## (.+)$', r'\\subsection{\1}', content, flags=re.MULTILINE)
    content = re.sub(r'^### (.+)$', r'\\subsubsection{\1}', content, flags=re.MULTILINE)

    # 转换粗体和斜体
    content = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', content)
    content = re.sub(r'\*(.+?)\*', r'\\textit{\1}', content)

    # 转换列表
    content = re.sub(r'^- (.+)$', r'\\item \1', content, flags=re.MULTILINE)

    # 转换 Obsidian callout 为 LaTeX 环境
    content = re.sub(
        r'> \[!(\w+)\] (.+)\n((?:> .+\n)*)',
        lambda m: _callout_to_latex(m.group(1), m.group(2), m.group(3)),
        content,
    )

    # 包装成完整的 LaTeX 文档
    lang_pkg = "\\usepackage{ctex}" if config.output.language == "zh" else ""

    latex = f"""\\documentclass[11pt]{{article}}
\\usepackage{{amsmath,amssymb,amsthm}}
\\usepackage{{geometry}}
\\usepackage{{hyperref}}
\\usepackage{{xcolor}}
\\usepackage{{tcolorbox}}
{lang_pkg}
\\geometry{{margin=2.5cm}}

\\newtcolorbox{{addedbox}}{{colback=green!5,colframe=green!50!black,title=补充的细节}}
\\newtcolorbox{{gapbox}}{{colback=red!5,colframe=red!50!black,title=细节缺失}}
\\newtcolorbox{{techbox}}{{colback=blue!5,colframe=blue!50!black,title=关键技巧}}

\\title{{{_escape_latex(paper.title)}}}
\\author{{AI 生成笔记}}
\\date{{\\today}}

\\begin{{document}}
\\maketitle

{content}

\\end{{document}}
"""
    return latex


def _callout_to_latex(callout_type: str, title: str, body: str) -> str:
    """将 Obsidian callout 转换为 LaTeX tcolorbox"""
    body_clean = re.sub(r'^>\s*', '', body, flags=re.MULTILINE).strip()
    box_map = {
        'added': 'addedbox',
        'gap': 'gapbox',
        'technique': 'techbox',
    }
    box_name = box_map.get(callout_type, 'addedbox')
    return f"\\begin{{{box_name}}}\n{body_clean}\n\\end{{{box_name}}}\n"


def _escape_latex(text: str) -> str:
    """转义 LaTeX 特殊字符"""
    chars = {'&': r'\&', '%': r'\%', '#': r'\#', '_': r'\_'}
    for char, escaped in chars.items():
        text = text.replace(char, escaped)
    return text


def _compile_latex(tex_path: Path):
    """尝试编译 LaTeX 到 PDF"""
    import subprocess
    try:
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", str(tex_path)],
            cwd=str(tex_path.parent),
            capture_output=True,
            timeout=60,
        )
        console.print(f"  PDF:      [green]{tex_path.with_suffix('.pdf')}[/green]")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        console.print("  [yellow]PDF 编译失败（需要安装 pdflatex）[/yellow]")


def _sanitize_filename(title: str) -> str:
    """将标题转换为安全的文件名"""
    # 只保留字母、数字、中文、连字符和下划线
    safe = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', title)
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe[:80] if safe else "untitled"
