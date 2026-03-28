"""三阶段 Pipeline + 自迭代循环 + 收敛判定 + 断点续跑"""

import re
import json
import hashlib
from datetime import datetime
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


def run_pipeline(paper: PaperDocument, config: AppConfig, resume_mode: str = "auto") -> PipelineResult:
    """
    运行完整的三阶段 Pipeline，支持断点续跑。

    流程：
    1. 粗读：提取骨架 → Stage 1 生成 Layer 1 + 标记精读 Section
    2. 精读：加载关键 Section → Stage 1 补充 Layer 2/3
    3. 自迭代：[Stage 2 批判 → Stage 3 修正] × N 轮（每步独立保存断点）
    4. Stage 4（可选）：研究突破问题生成

    resume_mode: "auto"（检测断点并询问）/ "resume"（直接续跑）/ "fresh"（强制重头）
    """
    result = PipelineResult()
    domain_data = load_domain(config.domain) if config.domain else None
    domain_hints = build_domain_hints(domain_data)
    domain_assumptions = build_domain_assumptions(domain_data)
    language = config.output.language

    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- 断点检测与恢复 ----
    cp = _handle_checkpoint(cache_dir, paper, resume_mode)
    resume_stage = cp["stage"] if cp else None
    saved = cp["state"] if cp else {}

    # 从 checkpoint 恢复状态
    layer1            = saved.get("layer1", "")
    sections_to_read  = saved.get("sections_to_read", [])
    current_summary   = saved.get("current_summary", "")
    last_critique     = saved.get("last_critique", "")
    previous_critique = saved.get("previous_critique", "")
    result.critique_history    = list(saved.get("critique_history", []))
    result.rounds_completed    = saved.get("rounds_completed", 0)
    result.total_input_tokens  = saved.get("total_input_tokens", 0)
    result.total_output_tokens = saved.get("total_output_tokens", 0)
    result.layer1 = layer1

    # 构建骨架和 system prompt（各阶段共用）
    system_prompt = format_prompt(EXTRACT_SYSTEM, domain_hints=domain_hints, language=language)
    skeleton = truncate_to_budget(paper.get_skeleton(), config.token_budget.extract.input_max)

    # ---- 预估 Token（仅首次运行时显示）----
    if resume_stage is None:
        _show_token_estimate(paper, config)

    # ==================================================
    # Stage 1 - 粗读（First Pass）
    # ==================================================
    if resume_stage is None:
        console.print("\n[bold cyan][Stage 1 - 粗读][/bold cyan] 提取论文骨架...")
        user_prompt = format_prompt(EXTRACT_USER_FIRST_PASS, skeleton=skeleton)
        first_pass_output = call_llm(
            model=config.models.extract, system_prompt=system_prompt,
            user_prompt=user_prompt, config=config,
            max_tokens=config.token_budget.extract.output_max,
        )
        result.total_input_tokens  += estimate_tokens(system_prompt + user_prompt)
        result.total_output_tokens += estimate_tokens(first_pass_output)
        layer1, sections_to_read = _parse_first_pass(first_pass_output, paper)
        result.layer1 = layer1
        console.print(f"  Layer 1 生成完毕，标记了 {len(sections_to_read)} 个 Section 需要精读")
        _save_checkpoint(cache_dir, paper, "first_pass", result, {
            "layer1": layer1, "sections_to_read": sections_to_read,
            "current_summary": "", "last_critique": "", "previous_critique": "",
        })
    else:
        console.print(f"\n[dim][Stage 1 - 粗读] 已跳过（断点: {resume_stage}）[/dim]")
        result.layer1 = layer1

    # ==================================================
    # Stage 1 - 精读（Second Pass）
    # ==================================================
    if resume_stage in (None, "first_pass"):
        if config.optimization.two_pass_reading and sections_to_read:
            console.print("[bold cyan][Stage 1 - 精读][/bold cyan] 加载关键 Section...")
            for sec in paper.sections:
                sec.is_core = sec.id in sections_to_read
            deep_read_text = truncate_to_budget(
                paper.get_core_sections_text(),
                config.token_budget.extract.input_max - estimate_tokens(layer1) - 200,
            )
            user_prompt_2 = format_prompt(
                EXTRACT_USER_SECOND_PASS, layer1=layer1,
                deep_read_sections=deep_read_text,
                max_proofs=str(config.output.max_layer3_proofs),
            )
            second_pass_output = call_llm(
                model=config.models.extract, system_prompt=system_prompt,
                user_prompt=user_prompt_2, config=config,
                max_tokens=config.token_budget.extract.output_max,
            )
            result.total_input_tokens  += estimate_tokens(system_prompt + user_prompt_2)
            result.total_output_tokens += estimate_tokens(second_pass_output)
            current_summary = _merge_passes(layer1, second_pass_output)
            console.print("  Layer 2/3 生成完毕")
        else:
            current_summary = layer1
        _save_checkpoint(cache_dir, paper, "second_pass", result, {
            "layer1": layer1, "sections_to_read": sections_to_read,
            "current_summary": current_summary, "last_critique": "", "previous_critique": "",
        })
    else:
        console.print(f"[dim][Stage 1 - 精读] 已跳过（断点: {resume_stage}）[/dim]")

    # ==================================================
    # 迭代：Stage 2 批判 + Stage 3 修正
    # ==================================================
    max_rounds = config.pipeline.max_rounds
    threshold  = config.pipeline.convergence_threshold
    critique_system   = format_prompt(CRITIQUE_SYSTEM, domain_assumptions=domain_assumptions, language=language)
    synthesize_system = format_prompt(SYNTHESIZE_SYSTEM, language=language)

    # 根据 resume_stage 决定从哪轮开始、是否跳过首轮批判
    start_round, skip_first_critique = _parse_resume_round(resume_stage)
    iterations_already_done = (start_round is None)

    if not iterations_already_done:
        for round_num in range(start_round, max_rounds + 1):
            console.print(f"\n[bold yellow][Round {round_num}/{max_rounds}][/bold yellow] 批判审查中...")

            # ---- Stage 2: 批判 ----
            if skip_first_critique and round_num == start_round:
                # 该轮批判已完成，直接使用断点中保存的结果
                console.print(f"  [dim]批判结果已从断点加载，跳过重新批判[/dim]")
                critique_output = last_critique
                skip_first_critique = False
            else:
                if round_num == 1:
                    core_sections_text = truncate_to_budget(
                        paper.get_core_sections_text(),
                        config.token_budget.critique.input_max - estimate_tokens(current_summary) - 500,
                    )
                    critique_user = format_prompt(
                        CRITIQUE_USER_FULL,
                        skeleton=truncate_to_budget(skeleton, 1000),
                        core_sections=core_sections_text,
                        summary=current_summary,
                    )
                else:
                    critique_user = format_prompt(
                        CRITIQUE_USER_INCREMENTAL,
                        previous_critique=previous_critique,
                        revised_parts=current_summary,
                    )
                critique_output = call_llm(
                    model=config.models.critique, system_prompt=critique_system,
                    user_prompt=critique_user, config=config,
                    max_tokens=config.token_budget.critique.output_max,
                )
                result.total_input_tokens  += estimate_tokens(critique_system + critique_user)
                result.total_output_tokens += estimate_tokens(critique_output)
                # 保存批判断点
                _save_checkpoint(cache_dir, paper, f"round_{round_num}_critique", result, {
                    "layer1": layer1, "sections_to_read": sections_to_read,
                    "current_summary": current_summary,
                    "last_critique": critique_output,
                    "previous_critique": previous_critique,
                })

            result.critique_history.append(critique_output)
            issue_count = _count_issues(critique_output)
            console.print(f"  发现 {issue_count} 个问题")

            # 收敛判定
            if issue_count <= threshold:
                console.print(f"  [green]收敛！问题数 ({issue_count}) ≤ 阈值 ({threshold})[/green]")
                result.rounds_completed = round_num
                break

            # ---- Stage 3: 修正 ----
            console.print(f"[bold green][Round {round_num}/{max_rounds}][/bold green] 修正中...")
            synthesize_user = format_prompt(
                SYNTHESIZE_USER, current_summary=current_summary, critique=critique_output,
            )
            revised_output = call_llm(
                model=config.models.synthesize, system_prompt=synthesize_system,
                user_prompt=synthesize_user, config=config,
                max_tokens=config.token_budget.synthesize.output_max,
            )
            result.total_input_tokens  += estimate_tokens(synthesize_system + synthesize_user)
            result.total_output_tokens += estimate_tokens(revised_output)
            current_summary   = revised_output
            previous_critique = critique_output
            result.rounds_completed = round_num
            # 保存修正断点
            _save_checkpoint(cache_dir, paper, f"round_{round_num}_synthesize", result, {
                "layer1": layer1, "sections_to_read": sections_to_read,
                "current_summary": current_summary,
                "last_critique": "", "previous_critique": previous_critique,
            })
            console.print("  修正完毕")
        else:
            console.print(f"  [yellow]达到最大轮数 ({max_rounds})，停止迭代[/yellow]")

    # 保存"迭代全部完成"断点
    _save_checkpoint(cache_dir, paper, "done_iterations", result, {
        "layer1": layer1, "sections_to_read": sections_to_read,
        "current_summary": current_summary,
        "last_critique": "", "previous_critique": previous_critique,
    })

    # ---- 组装最终结果 ----
    result.full_notes = current_summary
    result.layer1, result.layer2, result.layer3, result.appendix = _split_layers(current_summary)

    # ==================================================
    # Stage 4: 研究突破点提问（可选）
    # ==================================================
    if config.research_questions_enabled and resume_stage != "research_questions":
        console.print("\n[bold magenta][Stage 4][/bold magenta] 生成研究突破问题...")
        result.research_questions = _generate_research_questions(result.full_notes, config)
        result.total_input_tokens  += estimate_tokens(result.full_notes)
        result.total_output_tokens += estimate_tokens(result.research_questions)
        console.print("  研究问题生成完毕")

    # ---- Pipeline 全部完成：删除断点文件 ----
    _delete_checkpoint(cache_dir, paper)

    total_cost = estimate_cost(config.models.extract, result.total_input_tokens, result.total_output_tokens)
    console.print(f"\n[bold]Pipeline 完成[/bold]")
    console.print(f"  迭代轮数: {result.rounds_completed}")
    console.print(f"  总 token: ~{result.total_input_tokens + result.total_output_tokens}")
    console.print(f"  预估费用: ${total_cost:.4f}")

    return result


# ---- 断点辅助函数 ----

def _checkpoint_path(cache_dir: Path, paper: PaperDocument) -> Path:
    paper_hash = hashlib.md5(paper.source_path.encode()).hexdigest()[:8]
    return cache_dir / f"{paper_hash}_checkpoint.json"


def _save_checkpoint(cache_dir: Path, paper: PaperDocument, stage: str,
                     result: "PipelineResult", extra: dict):
    """将当前 pipeline 状态序列化为 checkpoint JSON 文件。"""
    state = {
        "layer1":            extra.get("layer1", ""),
        "sections_to_read":  extra.get("sections_to_read", []),
        "current_summary":   extra.get("current_summary", ""),
        "last_critique":     extra.get("last_critique", ""),
        "previous_critique": extra.get("previous_critique", ""),
        "critique_history":  list(result.critique_history),
        "rounds_completed":  result.rounds_completed,
        "total_input_tokens":  result.total_input_tokens,
        "total_output_tokens": result.total_output_tokens,
    }
    checkpoint = {
        "paper_hash": hashlib.md5(paper.source_path.encode()).hexdigest()[:8],
        "paper_name": paper.title or Path(paper.source_path).name,
        "stage":     stage,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "state":     state,
    }
    path = _checkpoint_path(cache_dir, paper)
    path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_checkpoint(cache_dir: Path, paper: PaperDocument) -> Optional[dict]:
    path = _checkpoint_path(cache_dir, paper)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _delete_checkpoint(cache_dir: Path, paper: PaperDocument):
    path = _checkpoint_path(cache_dir, paper)
    if path.exists():
        path.unlink()


def _handle_checkpoint(cache_dir: Path, paper: PaperDocument, resume_mode: str) -> Optional[dict]:
    """
    检测 checkpoint 文件，根据 resume_mode 决定续跑或重头。
    返回 checkpoint dict（续跑）或 None（重头）。
    """
    cp = _load_checkpoint(cache_dir, paper)
    if cp is None:
        return None

    stage      = cp.get("stage", "?")
    timestamp  = cp.get("timestamp", "?")
    rounds     = cp.get("state", {}).get("rounds_completed", 0)

    console.print(f"\n[bold yellow]⚡ 发现断点记录[/bold yellow]")
    console.print(f"  论文     : {cp.get('paper_name', '?')}")
    console.print(f"  已完成阶段: [cyan]{stage}[/cyan]")
    console.print(f"  已完成轮数: {rounds}")
    console.print(f"  保存时间 : {timestamp}")

    if resume_mode == "resume":
        console.print("  [green]--resume：自动续跑[/green]\n")
        return cp
    if resume_mode == "fresh":
        console.print("  [yellow]--fresh：删除断点，重新开始[/yellow]\n")
        _delete_checkpoint(cache_dir, paper)
        return None

    # auto：交互询问
    try:
        answer = input("\n是否从断点续跑？[Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if answer in ("n", "no", "否"):
        _delete_checkpoint(cache_dir, paper)
        return None
    return cp


def _parse_resume_round(resume_stage: Optional[str]) -> tuple:
    """
    根据 resume_stage 返回 (start_round, skip_first_critique)。
    start_round=None 表示迭代循环已全部完成，可直接跳到 Stage 4。
    skip_first_critique=True 表示该轮批判已完成，只需运行修正。
    """
    if resume_stage is None or resume_stage in ("first_pass", "second_pass"):
        return 1, False
    if resume_stage == "done_iterations":
        return None, False
    m = re.match(r"round_(\d+)_(critique|synthesize)", resume_stage)
    if m:
        n, step = int(m.group(1)), m.group(2)
        if step == "critique":
            return n, True   # 批判完成 → 续跑本轮修正
        else:
            return n + 1, False  # 修正完成 → 进入下一轮
    return 1, False


# ---- 其他辅助函数 ----

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


