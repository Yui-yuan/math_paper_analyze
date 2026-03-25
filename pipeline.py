"""三阶段 Pipeline + 自迭代循环 + 收敛判定"""

import re
import json
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from config import AppConfig, load_domain
from reader import PaperDocument
from llm import call_llm, estimate_cost
from token_utils import estimate_tokens, check_budget, truncate_to_budget, format_token_report
from prompts import (
    EXTRACT_SYSTEM, EXTRACT_USER_FIRST_PASS, EXTRACT_USER_SECOND_PASS,
    CRITIQUE_SYSTEM, CRITIQUE_USER_FULL, CRITIQUE_USER_INCREMENTAL,
    SYNTHESIZE_SYSTEM, SYNTHESIZE_USER,
    QUESTIONS_SYSTEM, QUESTIONS_USER,
    build_domain_hints, build_domain_assumptions, format_prompt,
)

from rich.console import Console

console = Console()


@dataclass
class PipelineResult:
    """Pipeline 运行结果"""
    layer1: str = ""
    layer2: str = ""
    layer3: str = ""
    appendix: str = ""
    full_notes: str = ""           # 合并后的完整笔记
    critique_history: list = field(default_factory=list)  # 每轮批判意见
    rounds_completed: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    research_questions: str = ""   # Stage 4 生成的研究突破问题


def run_pipeline(paper: PaperDocument, config: AppConfig) -> PipelineResult:
    """
    运行完整的三阶段 Pipeline。

    流程：
    1. 粗读：提取骨架 → Stage 1 生成 Layer 1 + 标记精读 Section
    2. 精读：加载关键 Section → Stage 1 补充 Layer 2/3
    3. 自迭代：[Stage 2 批判 → Stage 3 修正] × N 轮
    """
    result = PipelineResult()
    domain_data = load_domain(config.domain) if config.domain else None
    domain_hints = build_domain_hints(domain_data)
    domain_assumptions = build_domain_assumptions(domain_data)
    language = config.output.language

    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- 预估 Token 消耗 ----
    _show_token_estimate(paper, config)

    # ---- Stage 1: 第一遍粗读 ----
    console.print("\n[bold cyan][Stage 1 - 粗读][/bold cyan] 提取论文骨架...")

    skeleton = paper.get_skeleton()

    # 检查预算，如果骨架太大就截断
    skeleton = truncate_to_budget(skeleton, config.token_budget.extract.input_max)

    system_prompt = format_prompt(
        EXTRACT_SYSTEM,
        domain_hints=domain_hints,
        language=language,
    )
    user_prompt = format_prompt(
        EXTRACT_USER_FIRST_PASS,
        skeleton=skeleton,
    )

    first_pass_output = call_llm(
        model=config.models.extract,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        config=config,
        max_tokens=config.token_budget.extract.output_max,
    )

    result.total_input_tokens += estimate_tokens(system_prompt + user_prompt)
    result.total_output_tokens += estimate_tokens(first_pass_output)

    # 解析模型输出，提取 Layer 1 和需要精读的 Section 列表
    layer1, sections_to_read = _parse_first_pass(first_pass_output, paper)
    result.layer1 = layer1

    console.print(f"  Layer 1 生成完毕，标记了 {len(sections_to_read)} 个 Section 需要精读")

    # ---- Stage 1: 第二遍精读 ----
    if config.optimization.two_pass_reading and sections_to_read:
        console.print("[bold cyan][Stage 1 - 精读][/bold cyan] 加载关键 Section...")

        # 标记核心 section
        for sec in paper.sections:
            sec.is_core = sec.id in sections_to_read

        deep_read_text = paper.get_core_sections_text()
        deep_read_text = truncate_to_budget(
            deep_read_text,
            config.token_budget.extract.input_max - estimate_tokens(layer1) - 200
        )

        user_prompt_2 = format_prompt(
            EXTRACT_USER_SECOND_PASS,
            layer1=layer1,
            deep_read_sections=deep_read_text,
            max_proofs=str(config.output.max_layer3_proofs),
        )

        second_pass_output = call_llm(
            model=config.models.extract,
            system_prompt=system_prompt,
            user_prompt=user_prompt_2,
            config=config,
            max_tokens=config.token_budget.extract.output_max,
        )

        result.total_input_tokens += estimate_tokens(system_prompt + user_prompt_2)
        result.total_output_tokens += estimate_tokens(second_pass_output)

        # 合并两遍的输出
        current_summary = _merge_passes(layer1, second_pass_output)
        console.print("  Layer 2/3 生成完毕")
    else:
        # 不做两遍读，直接用第一遍输出
        current_summary = first_pass_output

    # ---- 缓存中间结果 ----
    if config.optimization.cache_intermediates:
        _save_cache(cache_dir, paper, "stage1", current_summary)

    # ---- 自迭代: Stage 2 批判 + Stage 3 修正 ----
    max_rounds = config.pipeline.max_rounds
    threshold = config.pipeline.convergence_threshold
    previous_critique = ""

    for round_num in range(1, max_rounds + 1):
        console.print(f"\n[bold yellow][Round {round_num}/{max_rounds}][/bold yellow] 批判审查中...")

        # Stage 2: 批判
        critique_system = format_prompt(
            CRITIQUE_SYSTEM,
            domain_assumptions=domain_assumptions,
            language=language,
        )

        if round_num == 1:
            # 第一轮：全面批判
            core_sections_text = paper.get_core_sections_text()
            core_sections_text = truncate_to_budget(
                core_sections_text,
                config.token_budget.critique.input_max - estimate_tokens(current_summary) - 500
            )

            critique_user = format_prompt(
                CRITIQUE_USER_FULL,
                skeleton=truncate_to_budget(skeleton, 1000),
                core_sections=core_sections_text,
                summary=current_summary,
            )
        else:
            # 后续轮次：增量批判
            critique_user = format_prompt(
                CRITIQUE_USER_INCREMENTAL,
                previous_critique=previous_critique,
                revised_parts=current_summary,
            )

        critique_output = call_llm(
            model=config.models.critique,
            system_prompt=critique_system,
            user_prompt=critique_user,
            config=config,
            max_tokens=config.token_budget.critique.output_max,
        )

        result.total_input_tokens += estimate_tokens(critique_system + critique_user)
        result.total_output_tokens += estimate_tokens(critique_output)
        result.critique_history.append(critique_output)

        # 计算问题数量
        issue_count = _count_issues(critique_output)
        console.print(f"  发现 {issue_count} 个问题")

        # 收敛判定
        if issue_count <= threshold:
            console.print(f"  [green]收敛！问题数 ({issue_count}) ≤ 阈值 ({threshold})[/green]")
            result.rounds_completed = round_num
            break

        # Stage 3: 修正
        console.print(f"[bold green][Round {round_num}/{max_rounds}][/bold green] 修正中...")

        synthesize_system = format_prompt(
            SYNTHESIZE_SYSTEM,
            language=language,
        )
        synthesize_user = format_prompt(
            SYNTHESIZE_USER,
            current_summary=current_summary,
            critique=critique_output,
        )

        revised_output = call_llm(
            model=config.models.synthesize,
            system_prompt=synthesize_system,
            user_prompt=synthesize_user,
            config=config,
            max_tokens=config.token_budget.synthesize.output_max,
        )

        result.total_input_tokens += estimate_tokens(synthesize_system + synthesize_user)
        result.total_output_tokens += estimate_tokens(revised_output)

        current_summary = revised_output
        previous_critique = critique_output
        result.rounds_completed = round_num

        # 缓存
        if config.optimization.cache_intermediates:
            _save_cache(cache_dir, paper, f"round{round_num}", current_summary)

        console.print("  修正完毕")
    else:
        console.print(f"  [yellow]达到最大轮数 ({max_rounds})，停止迭代[/yellow]")

    # ---- 组装最终结果 ----
    result.full_notes = current_summary

    # 尝试拆分 layers
    result.layer1, result.layer2, result.layer3, result.appendix = _split_layers(current_summary)

    # ---- Stage 4: 研究突破点提问（可选）----
    if config.research_questions_enabled:
        console.print("\n[bold magenta][Stage 4][/bold magenta] 生成研究突破问题...")
        result.research_questions = _generate_research_questions(result.full_notes, config)
        result.total_input_tokens += estimate_tokens(result.full_notes)
        result.total_output_tokens += estimate_tokens(result.research_questions)
        console.print("  研究问题生成完毕")

    total_cost = estimate_cost(
        config.models.extract,
        result.total_input_tokens,
        result.total_output_tokens,
    )
    console.print(f"\n[bold]Pipeline 完成[/bold]")
    console.print(f"  迭代轮数: {result.rounds_completed}")
    console.print(f"  总 token: ~{result.total_input_tokens + result.total_output_tokens}")
    console.print(f"  预估费用: ${total_cost:.4f}")

    return result


# ---- 辅助函数 ----

def _show_token_estimate(paper: PaperDocument, config: AppConfig):
    """显示 token 消耗预估"""
    skeleton_tokens = estimate_tokens(paper.get_skeleton())
    core_tokens = min(paper.total_tokens * 0.3, config.token_budget.extract.input_max)

    stages = {
        "Stage 1 (粗读)": {
            "input": skeleton_tokens,
            "output": config.token_budget.extract.output_max,
            "model": config.models.extract,
            "rounds": 1,
        },
        "Stage 1 (精读)": {
            "input": int(core_tokens) + config.token_budget.extract.output_max,
            "output": config.token_budget.extract.output_max,
            "model": config.models.extract,
            "rounds": 1,
        },
        "Stage 2 (批判)": {
            "input": config.token_budget.critique.input_max,
            "output": config.token_budget.critique.output_max,
            "model": config.models.critique,
            "rounds": config.pipeline.max_rounds,
        },
        "Stage 3 (修正)": {
            "input": config.token_budget.synthesize.input_max,
            "output": config.token_budget.synthesize.output_max,
            "model": config.models.synthesize,
            "rounds": config.pipeline.max_rounds - 1,  # 最后一轮收敛不需要修正
        },
    }

    report = format_token_report(stages)
    console.print(f"\n{report}")


def _parse_first_pass(output: str, paper: PaperDocument) -> tuple:
    """
    解析第一遍粗读的输出。
    返回 (layer1_text, list_of_section_ids_to_read)
    """
    # 尝试找到模型标记的需要精读的 Section
    sections_to_read = []

    # 匹配 sec1, sec2.1 等格式
    section_refs = re.findall(r'sec[\d.]+', output, re.IGNORECASE)
    if section_refs:
        sections_to_read = list(set(section_refs))
    else:
        # 如果模型没有明确标出，匹配 "Section X" 格式
        section_nums = re.findall(r'Section\s+([\d.]+)', output)
        sections_to_read = [f"sec{n}" for n in section_nums]

    # 如果还是没找到，默认选 token 最多的 section（通常是主要证明所在的 section）
    if not sections_to_read and paper.sections:
        sorted_secs = sorted(paper.sections, key=lambda s: s.token_count, reverse=True)
        sections_to_read = [s.id for s in sorted_secs[:3]]

    return output, sections_to_read


def _merge_passes(layer1: str, second_pass: str) -> str:
    """合并两遍读的输出"""
    # 如果第二遍输出包含修正后的 Layer 1，使用修正版
    if "Layer 1" in second_pass and "Layer 2" in second_pass:
        return second_pass
    else:
        return f"{layer1}\n\n---\n\n{second_pass}"


def _count_issues(critique: str) -> int:
    """统计批判意见中的问题数量"""
    # 统计 [致命], [重要], [轻微] 标记
    fatal = len(re.findall(r'\[致命\]', critique))
    important = len(re.findall(r'\[重要\]', critique))
    minor = len(re.findall(r'\[轻微\]', critique))

    total = fatal + important + minor

    # 如果模型没有用标准标记，尝试数编号列表
    if total == 0:
        numbered = re.findall(r'^\s*\d+[.)]\s', critique, re.MULTILINE)
        total = len(numbered)

    # 至少返回 1（如果有内容但没匹配到格式）
    if total == 0 and len(critique.strip()) > 50:
        total = 3  # 保守估计

    return total


def _split_layers(full_notes: str) -> tuple:
    """尝试将完整笔记拆分成各 layer"""
    layer1 = ""
    layer2 = ""
    layer3 = ""
    appendix = ""

    # 尝试按标记拆分
    parts = re.split(r'(?=##\s+Layer\s+\d|##\s+附录|##\s+Appendix)', full_notes, flags=re.IGNORECASE)

    for part in parts:
        part_lower = part.lower().strip()
        if 'layer 1' in part_lower or '总览' in part_lower:
            layer1 = part.strip()
        elif 'layer 2' in part_lower or '技术骨架' in part_lower:
            layer2 = part.strip()
        elif 'layer 3' in part_lower or '证明细节' in part_lower:
            layer3 = part.strip()
        elif '附录' in part_lower or 'appendix' in part_lower:
            appendix = part.strip()

    # 如果拆分失败，全部放到 layer1
    if not layer1 and not layer2:
        layer1 = full_notes

    return layer1, layer2, layer3, appendix


def _generate_research_questions(full_notes: str, config: AppConfig) -> str:
    """Stage 4：基于阅读笔记生成研究突破问题"""
    count = 5
    language = config.output.language

    notes_input = truncate_to_budget(full_notes, config.token_budget.questions.input_max)

    system_prompt = format_prompt(
        QUESTIONS_SYSTEM,
        count=str(count),
        language=language,
    )
    user_prompt = format_prompt(
        QUESTIONS_USER,
        notes=notes_input,
        count=str(count),
    )

    try:
        output = call_llm(
            model=config.models.questions,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            config=config,
            max_tokens=config.token_budget.questions.output_max,
        )
        return output.strip()
    except Exception as e:
        return f"[研究问题生成失败: {e}]"


def _save_cache(cache_dir: Path, paper: PaperDocument, stage: str, content: str):
    """缓存中间结果"""
    paper_hash = hashlib.md5(paper.source_path.encode()).hexdigest()[:8]
    cache_file = cache_dir / f"{paper_hash}_{stage}.md"
    cache_file.write_text(content, encoding='utf-8')
