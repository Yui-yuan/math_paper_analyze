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
    """
    从纯文本中解析 Section 结构。

    策略：
    1. 优先解析目录（Contents）获取完整的 section 列表和页码
    2. 根据目录信息在正文中定位各 section
    3. 如果没有目录，退回正则扫描模式
    """
    page_offsets = _build_page_offsets(pages_text)
    lines = full_text.split('\n')
    line_offsets = []
    pos = 0
    for line in lines:
        line_offsets.append(pos)
        pos += len(line) + 1

    # 策略 1：尝试解析目录
    toc_entries = _parse_toc(lines, line_offsets, page_offsets, pages_text)
    if toc_entries:
        sections = _locate_sections_from_toc(
            toc_entries, lines, line_offsets, page_offsets, pages_text, full_text
        )
        if sections:
            return sections

    # 策略 2：退回正则扫描
    return _scan_sections_regex(lines, line_offsets, page_offsets, pages_text, full_text)


def _parse_toc(lines: list, line_offsets=None, page_offsets=None, pages_text=None) -> list:
    """
    解析目录（Contents），返回 [(sec_num, title, page_ref), ...] 列表。
    目录格式（PDF 提取后）：
        1              ← section 编号独占一行
        Introduction   ← 标题（可能带点线 ......）
        3              ← 目录中标注的页码
    """
    # 查找 "Contents" 行
    toc_start = None
    for i, line in enumerate(lines):
        if line.strip().lower() in ('contents', 'table of contents', '目录'):
            toc_start = i + 1
            break
    if toc_start is None:
        return []

    # 支持多种编号格式：
    # 阿拉伯数字: 1, 2.1, 4.6.1
    # 附录字母: A, A.1, B.2
    # 罗马数字章: Chapter I., Chapter IV.
    # 罗马数字节: I.1., IV.4., VI.12.
    roman = r'[IVXLCDM]+'
    sec_num_pat = re.compile(
        r'^\s*(?:§\s*)?('
        r'\d+(?:\.\d+)*'                     # 1, 2.1, 4.6.1
        r'|[A-Z](?:\.\d+)+'                  # A.1, B.2
        r'|[A-Z]'                             # A, B (单字母附录)
        r'|Chapter\s+' + roman + r'\.?'       # Chapter I., Chapter IV.
        r'|' + roman + r'\.\d+\.?'            # I.1., IV.4., VI.12.
        r')\s*$'
    )
    page_ref_pat = re.compile(r'^\s*(\d+)\s*$')

    entries = []
    i = toc_start
    max_scan = min(toc_start + 500, len(lines))  # 目录最多扫 500 行

    while i < max_scan:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue

        # 排除页眉/页脚页码（仅跳过纯数字的页首/页尾行）
        if line_offsets and page_offsets and pages_text:
            char_off = line_offsets[i]
            is_pure_number = re.match(r'^\d+$', stripped)
            if is_pure_number and _is_near_page_end(char_off, page_offsets, pages_text):
                i += 1
                continue
            if is_pure_number and _is_near_page_start(char_off, page_offsets):
                i += 1
                continue

        # 尝试匹配 section 编号
        m = sec_num_pat.match(stripped)
        if m:
            sec_num = m.group(1)
            # 下一个非空行 = 标题
            j = i + 1
            while j < max_scan and not lines[j].strip():
                j += 1
            if j >= max_scan:
                break

            title = lines[j].strip()
            # 清理标题上的点线尾缀
            title = re.sub(r'\s*[.·]{3,}[\s\d]*$', '', title).strip()
            title = re.sub(r'\s+\. \. \.[\s.\d]*$', '', title).strip()

            # 跳过后续的纯点线行（目录标题可能跨行，点线单独一行）
            k = j + 1
            while k < max_scan:
                next_stripped = lines[k].strip() if k < len(lines) else ''
                if not next_stripped:
                    k += 1
                    continue
                # 这行是纯点线（". . . . . ." 或 "....."）→ 跳过
                if re.match(r'^[.\s·]+\d*\s*$', next_stripped):
                    k += 1
                    continue
                break

            # 现在 k 应该指向页码引用行
            page_ref = None
            if k < max_scan and page_ref_pat.match(lines[k].strip()):
                page_ref = int(lines[k].strip())
                i = k + 1
            else:
                i = j + 1

            if title and not page_ref_pat.match(title):
                entries.append((sec_num, title, page_ref))
            continue

        # 非目录格式的行：可能是脚注、页码等，跳过但计数
        # 连续太多非目录行才认为目录结束
        non_toc_count = 0
        while i < max_scan:
            s = lines[i].strip() if i < len(lines) else ''
            if not s:
                i += 1
                continue
            if sec_num_pat.match(s) or page_ref_pat.match(s):
                break  # 又遇到目录内容了
            non_toc_count += 1
            if non_toc_count > 10:
                break  # 连续 10+ 行非目录内容，目录结束
            i += 1
            continue

        if non_toc_count > 10:
            break

        # i 已经被 while 推进了，继续外层循环

    return entries


def _locate_sections_from_toc(
    toc_entries, lines, line_offsets, page_offsets, pages_text, full_text
):
    """根据目录条目在正文中定位各 section 的起始位置"""
    # 匹配所有支持的编号格式（与 TOC 解析器保持一致）
    roman = r'[IVXLCDM]+'
    sec_num_pat = re.compile(
        r'^\s*(?:§\s*)?('
        r'\d+(?:\.\d+)*'
        r'|[A-Z](?:\.\d+)+'
        r'|[A-Z]'
        r'|Chapter\s+' + roman + r'\.?'
        r'|' + roman + r'\.\d+\.?'
        r')\s*$'
    )

    headers = []  # (line_idx, sec_num, title, char_offset)

    for sec_num, title, page_ref in toc_entries:
        if page_ref is None:
            continue

        # 在 page_ref 指定的页（±1 页容差）中找 section 编号
        target_page = page_ref - 1  # 转 0-based
        search_start_page = max(0, target_page - 1)
        search_end_page = min(len(page_offsets), target_page + 2)

        start_off = page_offsets[search_start_page]
        end_off = page_offsets[search_end_page] if search_end_page < len(page_offsets) else len(full_text)

        found = False
        # 构建搜索用的模式
        # 1. 独立行: "I.1." 单独一行
        # 2. Inline: "I.1. Title text" 同一行
        # 3. 章标题变体: "CHAPTER I" (全大写) 对应 TOC 的 "Chapter I."
        escaped_num = re.escape(sec_num.rstrip('.'))
        inline_pat = re.compile(r'^\s*' + escaped_num + r'\.?\s+\S')
        chapter_pat = None
        if sec_num.startswith('Chapter'):
            # "Chapter I." → 也匹配 "CHAPTER I"
            ch_roman = sec_num.replace('Chapter ', '').rstrip('.')
            chapter_pat = re.compile(
                r'^\s*(?:CHAPTER|Chapter)\s+' + re.escape(ch_roman) + r'\b',
                re.IGNORECASE
            )

        for i, line in enumerate(lines):
            if line_offsets[i] < start_off or line_offsets[i] > end_off:
                continue
            # 排除页脚页码
            if _is_near_page_end(line_offsets[i], page_offsets, pages_text):
                continue

            stripped = line.strip()
            # 排除页眉：仅跳过页面开头的纯数字行（如 "8"），不跳过实际内容
            if _is_near_page_start(line_offsets[i], page_offsets) and re.match(r'^\d+$', stripped):
                continue

            # 匹配独立行编号
            m = sec_num_pat.match(stripped)
            if m and m.group(1) == sec_num:
                headers.append((i, sec_num, title, line_offsets[i]))
                found = True
                break

            # 匹配 inline 编号 (如 "I.1. Title")
            if inline_pat.match(stripped):
                headers.append((i, sec_num, title, line_offsets[i]))
                found = True
                break

            # 匹配章标题变体 (如 "CHAPTER I")
            if chapter_pat and chapter_pat.match(stripped):
                headers.append((i, sec_num, title, line_offsets[i]))
                found = True
                break

        if not found:
            # 退回：直接用目录给的页码估算位置
            if target_page < len(page_offsets):
                headers.append((-1, sec_num, title, page_offsets[target_page]))

    if not headers:
        return []

    headers.sort(key=lambda h: h[3])

    # 构建 Section 对象
    sections = []
    for idx, (line_i, sec_num, title, char_offset) in enumerate(headers):
        # 找内容起始行：编号行 + 标题行之后
        if line_i >= 0:
            content_start = line_i + 1
            # 跳过标题行
            if content_start < len(lines) and lines[content_start].strip() == title:
                content_start += 1
            elif content_start < len(lines):
                # 标题可能被清理过，模糊匹配
                next_line = lines[content_start].strip()
                cleaned = re.sub(r'\s*[.·]{3,}[\s\d]*$', '', next_line).strip()
                if cleaned and title.startswith(cleaned[:20]):
                    content_start += 1
        else:
            # 用偏移估算
            content_start = 0
            for ci, lo in enumerate(line_offsets):
                if lo >= char_offset:
                    content_start = ci
                    break

        if idx + 1 < len(headers):
            content_end_offset = headers[idx + 1][3]
            content_end_line = 0
            for ci, lo in enumerate(line_offsets):
                if lo >= content_end_offset:
                    content_end_line = ci
                    break
        else:
            content_end_line = len(lines)
            content_end_offset = len(full_text)

        content = '\n'.join(lines[content_start:content_end_line]).strip()

        # 层级
        if sec_num.startswith('Chapter'):
            level = 1
        elif re.match(r'^[IVXLCDM]+\.\d+', sec_num):
            # 罗马数字节如 IV.4. → level 2
            level = 2
        elif sec_num.count('.') > 0 and sec_num.split('.')[0].isalpha():
            parts = sec_num.split('.')
            level = len(parts)  # A.1=2, A.1.1=3
        else:
            level = sec_num.count('.') + 1

        sec_id = f"sec{sec_num}"
        page_start = _offset_to_page(char_offset, page_offsets)
        page_end = _offset_to_page(content_end_offset, page_offsets)

        sections.append(Section(
            id=sec_id,
            title=title,
            level=level,
            content=content,
            page_start=page_start,
            page_end=page_end,
        ))

    return sections


def _scan_sections_regex(lines, line_offsets, page_offsets, pages_text, full_text):
    """退回方案：正则扫描（用于无目录的论文）"""
    sec_num_pat = re.compile(r'^\s*(?:§\s*)?(\d+(?:\.\d+)*|[A-Z]\.\d+(?:\.\d+)*)\s*$')
    markdown_pat = re.compile(r'^\s*(#{1,3})\s+(\S.*)$')

    headers = []
    skip_lines = set()

    for i, line in enumerate(lines):
        if i in skip_lines:
            continue
        stripped = line.strip()
        if not stripped:
            continue

        # 两行式
        m = sec_num_pat.match(stripped)
        if m:
            sec_num = m.group(1)
            char_off = line_offsets[i]
            if _is_near_page_end(char_off, page_offsets, pages_text):
                continue
            if '.' not in sec_num and sec_num.isdigit() and int(sec_num) > 20:
                continue
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                title_text = lines[j].strip()
                if _is_likely_section_title(title_text):
                    headers.append((i, sec_num, title_text, char_off))
                    skip_lines.add(j)
                    continue

        # Markdown
        m3 = markdown_pat.match(stripped)
        if m3:
            hashes = m3.group(1)
            title_text = m3.group(2).strip()
            headers.append((i, f"md{len(hashes)}_{i}", title_text, line_offsets[i]))

    if not headers:
        return [Section(id="sec0", title="Full Text", level=1, content=full_text)]

    # 去重：保留首次出现
    seen = set()
    deduped = []
    for h in headers:
        if h[1] not in seen:
            seen.add(h[1])
            deduped.append(h)
    deduped.sort(key=lambda h: h[3])

    sections = []
    for idx, (line_i, sec_num, title, char_offset) in enumerate(deduped):
        title_line = line_i
        if line_i + 1 in skip_lines:
            title_line = line_i + 1
        content_start = title_line + 1

        if idx + 1 < len(deduped):
            content_end_line = deduped[idx + 1][0]
            content_end_offset = deduped[idx + 1][3]
        else:
            content_end_line = len(lines)
            content_end_offset = len(full_text)

        content = '\n'.join(lines[content_start:content_end_line]).strip()

        if sec_num.startswith('md'):
            level = int(sec_num[2])
        else:
            level = sec_num.count('.') + 1

        sec_id = f"sec{sec_num}" if not sec_num.startswith('md') else f"sec{idx + 1}"
        page_start = _offset_to_page(char_offset, page_offsets)
        page_end = _offset_to_page(content_end_offset, page_offsets)

        sections.append(Section(
            id=sec_id, title=title, level=level, content=content,
            page_start=page_start, page_end=page_end,
        ))

    return sections


def _is_near_page_start(char_offset: int, page_offsets: list) -> bool:
    """判断字符偏移是否接近某页开头（用于排除页眉页码）"""
    for po in page_offsets:
        if 0 <= char_offset - po < 20:
            return True
    return False


def _is_near_page_end(char_offset: int, page_offsets: list, pages_text: list) -> bool:
    """判断字符偏移是否接近某页末尾（用于排除页脚页码）"""
    if not page_offsets:
        return False
    page_idx = 0
    for i, po in enumerate(page_offsets):
        if po <= char_offset:
            page_idx = i
        else:
            break
    if page_idx < len(pages_text):
        page_end = page_offsets[page_idx] + len(pages_text[page_idx])
        if page_end - char_offset < 100:
            return True
    return False


def _is_likely_section_title(text: str) -> bool:
    """判断一行文本是否可能是 section 标题（用于无目录的退回模式）"""
    if not text or len(text) > 100:
        return False
    if '...' in text or '. . .' in text:
        return False
    if re.match(r'^\s*(?:§\s*)?\d+(?:\.\d+)*\.?\s*$', text):
        return False
    if re.match(r'^\([\d.]+\)\s*$', text):
        return False
    if text.startswith('['):
        return False
    alpha_count = sum(1 for c in text if c.isalpha())
    if alpha_count < 5:
        return False
    if len(text) > 60 and text.count(',') >= 2:
        return False
    return True


def _build_page_offsets(pages_text: list) -> list:
    """返回每页在 full_text 中的起始字符偏移（full_text = '\\n'.join(pages_text)）"""
    offsets = []
    pos = 0
    for i, page in enumerate(pages_text):
        offsets.append(pos)
        pos += len(page) + 1  # +1 for the '\n' separator
    return offsets


def _offset_to_page(offset: int, page_offsets: list) -> Optional[int]:
    """将字符偏移转换为 1-based 页码"""
    if not page_offsets:
        return None
    # 二分查找
    lo, hi = 0, len(page_offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if page_offsets[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1  # 1-based


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
