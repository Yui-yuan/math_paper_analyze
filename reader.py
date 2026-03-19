"""论文输入处理：PDF/LaTeX/文本解析，Section 索引表构建"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Section:
    """论文中的一个段落/Section"""
    id: str                    # 如 "sec1", "sec2.1"
    title: str                 # Section 标题
    level: int                 # 层级: 1=大节, 2=小节, 3=子小节
    content: str               # 原文内容
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    token_count: int = 0       # token 估计数
    summary: str = ""          # 便宜模型生成的摘要（预处理后填入）
    is_core: bool = False      # 是否被标记为核心 section


@dataclass
class PaperDocument:
    """解析后的论文文档"""
    title: str = ""
    authors: str = ""
    abstract: str = ""
    sections: list = field(default_factory=list)  # List[Section]
    full_text: str = ""
    source_path: str = ""
    total_tokens: int = 0

    def get_skeleton(self) -> str:
        """获取论文骨架：Abstract + 所有 Section 标题 + 定理/引理陈述"""
        parts = []
        if self.title:
            parts.append(f"# {self.title}")
        if self.authors:
            parts.append(f"Authors: {self.authors}")
        if self.abstract:
            parts.append(f"\n## Abstract\n{self.abstract}")

        parts.append("\n## Structure")
        for sec in self.sections:
            indent = "  " * (sec.level - 1)
            parts.append(f"{indent}- [{sec.id}] {sec.title} (~{sec.token_count} tokens)")

        # 提取定理、引理、命题等陈述
        theorems = self._extract_theorem_statements()
        if theorems:
            parts.append("\n## Theorem/Lemma Statements")
            parts.append(theorems)

        return "\n".join(parts)

    def _extract_theorem_statements(self) -> str:
        """从全文中提取定理、引理、命题的陈述"""
        patterns = [
            r'(\\begin\{theorem\}.*?\\end\{theorem\})',
            r'(\\begin\{lemma\}.*?\\end\{lemma\})',
            r'(\\begin\{proposition\}.*?\\end\{proposition\})',
            r'(\\begin\{corollary\}.*?\\end\{corollary\})',
            r'(\\begin\{definition\}.*?\\end\{definition\})',
            # 纯文本格式的定理
            r'((?:Theorem|Lemma|Proposition|Corollary|Definition)\s+[\d.]+[.\s].*?)(?=\n\n|\n(?:Proof|Theorem|Lemma|Proposition|Corollary|Definition|\\begin))',
        ]
        statements = []
        text = self.full_text
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            statements.extend(matches)

        return "\n\n".join(s.strip() for s in statements[:20])  # 最多取 20 个

    def get_section_by_id(self, section_id: str) -> Optional['Section']:
        for sec in self.sections:
            if sec.id == section_id:
                return sec
        return None

    def get_core_sections_text(self) -> str:
        """获取所有标记为核心的 section 的原文"""
        parts = []
        for sec in self.sections:
            if sec.is_core:
                parts.append(f"### [{sec.id}] {sec.title}\n{sec.content}")
        return "\n\n".join(parts)

    def get_section_index(self) -> str:
        """获取 Section 索引表（不含原文，仅标题和摘要）"""
        lines = []
        for sec in self.sections:
            summary_part = f" — {sec.summary}" if sec.summary else ""
            core_mark = " [核心]" if sec.is_core else ""
            lines.append(f"[{sec.id}] {sec.title}{core_mark} (~{sec.token_count} tokens){summary_part}")
        return "\n".join(lines)


def read_pdf(file_path: str) -> PaperDocument:
    """解析 PDF 文件"""
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    full_text = "\n".join(pages_text)
    doc.close()

    paper = PaperDocument(
        full_text=full_text,
        source_path=file_path,
    )

    # 尝试提取标题（通常是第一页的第一行大字）
    paper.title = _extract_title(pages_text[0] if pages_text else "")

    # 尝试提取摘要
    paper.abstract = _extract_abstract(full_text)

    # 解析 Section 结构
    paper.sections = _parse_sections(full_text, pages_text)

    return paper


def read_latex(file_path: str) -> PaperDocument:
    """解析 LaTeX 源文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    paper = PaperDocument(
        full_text=content,
        source_path=file_path,
    )

    # 提取 \title{...}
    title_match = re.search(r'\\title\{(.+?)\}', content, re.DOTALL)
    if title_match:
        paper.title = _clean_latex(title_match.group(1))

    # 提取 \author{...}
    author_match = re.search(r'\\author\{(.+?)\}', content, re.DOTALL)
    if author_match:
        paper.authors = _clean_latex(author_match.group(1))

    # 提取 abstract
    abs_match = re.search(r'\\begin\{abstract\}(.+?)\\end\{abstract\}', content, re.DOTALL)
    if abs_match:
        paper.abstract = abs_match.group(1).strip()

    # 解析 section 结构（LaTeX 格式）
    paper.sections = _parse_latex_sections(content)

    return paper


def read_text(file_path: str) -> PaperDocument:
    """读取纯文本/Markdown 文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    paper = PaperDocument(
        full_text=content,
        source_path=file_path,
    )
    paper.title = _extract_title(content[:500])
    paper.abstract = _extract_abstract(content)
    paper.sections = _parse_sections(content, [content])

    return paper


def read_paper(file_path: str) -> PaperDocument:
    """根据文件类型自动选择解析器"""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == '.pdf':
        paper = read_pdf(file_path)
    elif suffix in ('.tex', '.latex'):
        paper = read_latex(file_path)
    elif suffix in ('.txt', '.md', '.markdown'):
        paper = read_text(file_path)
    else:
        # 尝试当作文本读取
        paper = read_text(file_path)

    # 估算 token 数
    from token_utils import estimate_tokens
    paper.total_tokens = estimate_tokens(paper.full_text)
    for sec in paper.sections:
        sec.token_count = estimate_tokens(sec.content)

    return paper


# ---- 内部辅助函数 ----

def _extract_title(first_page: str) -> str:
    """从第一页文本尝试提取标题"""
    lines = [l.strip() for l in first_page.split('\n') if l.strip()]
    if lines:
        # 通常标题是前几行中最长的非空行
        candidates = lines[:5]
        if candidates:
            return max(candidates, key=len)
    return "Untitled"


def _extract_abstract(text: str) -> str:
    """提取摘要"""
    # 尝试多种格式
    patterns = [
        r'(?:Abstract|ABSTRACT)[.\s:—\-]*\n?(.*?)(?:\n\n|\n(?:1[\s.]|Introduction|Keywords|§))',
        r'\\begin\{abstract\}(.*?)\\end\{abstract\}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _parse_sections(full_text: str, pages_text: list) -> list:
    """从纯文本中解析 Section 结构"""
    sections = []
    # 匹配常见的 section 格式: "1. Introduction", "2.1 Preliminaries", "§3" 等
    pattern = r'\n((?:§?\d+(?:\.\d+)*\.?\s+[A-Z][^\n]{3,})|(?:#{1,3}\s+[^\n]+))\n'
    matches = list(re.finditer(pattern, full_text))

    if not matches:
        # 如果找不到 section 结构，整篇作为一个 section
        sections.append(Section(
            id="sec0",
            title="Full Text",
            level=1,
            content=full_text,
        ))
        return sections

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        content = full_text[start:end].strip()

        # 判断层级
        level = 1
        num_match = re.match(r'§?(\d+(?:\.\d+)*)', title)
        if num_match:
            level = num_match.group(1).count('.') + 1
        elif title.startswith('###'):
            level = 3
        elif title.startswith('##'):
            level = 2

        sec_id = f"sec{i + 1}"
        if num_match:
            sec_id = f"sec{num_match.group(1)}"

        sections.append(Section(
            id=sec_id,
            title=re.sub(r'^[§#\d.]+\s*', '', title).strip(),
            level=level,
            content=content,
        ))

    return sections


def _parse_latex_sections(content: str) -> list:
    """从 LaTeX 源文件中解析 Section 结构"""
    sections = []
    pattern = r'\\(section|subsection|subsubsection)\{(.+?)\}'
    matches = list(re.finditer(pattern, content))

    level_map = {'section': 1, 'subsection': 2, 'subsubsection': 3}

    for i, match in enumerate(matches):
        level = level_map[match.group(1)]
        title = _clean_latex(match.group(2))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sec_content = content[start:end].strip()

        sections.append(Section(
            id=f"sec{i + 1}",
            title=title,
            level=level,
            content=sec_content,
        ))

    return sections


def _clean_latex(text: str) -> str:
    """简单清理 LaTeX 命令"""
    text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'[{}\\]', '', text)
    return text.strip()
