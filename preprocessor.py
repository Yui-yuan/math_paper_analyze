"""预处理压缩：删除冗余内容 + 便宜模型摘要非核心引理"""

import re
from reader import PaperDocument, Section
from config import AppConfig
from token_utils import estimate_tokens
from llm import call_llm


def preprocess(paper: PaperDocument, config: AppConfig) -> PaperDocument:
    """
    预处理论文，减少 token 消耗：
    1. 删除参考文献、致谢等冗余段落
    2. 对非核心辅助 section 用便宜模型生成摘要
    """
    # Step 1: 删除明显的冗余 section
    paper = _remove_boilerplate(paper)

    # Step 2: 如果启用了压缩，对大段的 section 生成摘要
    if config.optimization.preprocess_compression:
        paper = _compress_sections(paper, config)

    return paper


def _remove_boilerplate(paper: PaperDocument) -> PaperDocument:
    """删除参考文献、致谢、附录等不需要精读的段落"""

    # 需要删除的 section 标题关键词
    remove_keywords = [
        'references', 'bibliography', 'acknowledgement', 'acknowledgment',
        'acknowledgements', 'acknowledgments', '参考文献', '致谢',
    ]

    # 标记为低优先级（保留摘要但不精读）的关键词
    low_priority_keywords = [
        'appendix', 'index of notation', 'notation', '附录', '记号表',
    ]

    filtered_sections = []
    for sec in paper.sections:
        title_lower = sec.title.lower().strip()

        # 完全删除
        if any(kw in title_lower for kw in remove_keywords):
            continue

        # 标记为非核心
        if any(kw in title_lower for kw in low_priority_keywords):
            sec.is_core = False
        else:
            sec.is_core = True  # 暂时全部标记为核心，后续会精选

        filtered_sections.append(sec)

    paper.sections = filtered_sections

    # 同时从全文中删除参考文献部分（用于 theorem 提取等）
    paper.full_text = _strip_references(paper.full_text)

    return paper


def _strip_references(text: str) -> str:
    """从全文中删除 References 部分之后的内容"""
    patterns = [
        r'\n(?:References|REFERENCES|Bibliography|参考文献)\s*\n',
        r'\\begin\{thebibliography\}',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return text[:match.start()]
    return text


def _compress_sections(paper: PaperDocument, config: AppConfig) -> PaperDocument:
    """对大段的非 Introduction section 生成摘要"""
    # 阈值：超过 500 token 的非核心 section 才需要压缩
    compress_threshold = 500

    sections_to_compress = []
    for sec in paper.sections:
        if sec.token_count > compress_threshold and not _is_essential_section(sec):
            sections_to_compress.append(sec)

    if not sections_to_compress:
        return paper

    # 用便宜模型批量生成摘要
    for sec in sections_to_compress:
        summary = _summarize_section(sec, config)
        sec.summary = summary
        sec.is_core = False  # 有摘要的就不算核心了

    return paper


def _is_essential_section(sec: Section) -> bool:
    """判断是否是必须精读的 section"""
    essential_keywords = [
        'introduction', 'main result', 'main theorem', 'statement',
        'proof of main', 'proof of the main',
        '引言', '主要结果', '主定理',
    ]
    title_lower = sec.title.lower()
    return any(kw in title_lower for kw in essential_keywords)


def _summarize_section(sec: Section, config: AppConfig) -> str:
    """用便宜模型生成 section 摘要"""
    system_prompt = (
        "你是一个数学文本处理助手。请用1-2句话精确概括以下数学论文片段的核心内容。"
        "保留关键的数学对象和结论，不要加任何修饰性描述。"
    )
    user_prompt = f"Section: {sec.title}\n\n{sec.content[:3000]}"

    try:
        summary = call_llm(
            model=config.models.preprocess,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            config=config,
            max_tokens=200,
            temperature=0.1,
        )
        return summary.strip()
    except Exception as e:
        return f"[摘要生成失败: {e}]"
