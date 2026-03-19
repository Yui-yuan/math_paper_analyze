"""研讨模式：用户提问，模型指路式回答"""

import re
from typing import Optional

from config import AppConfig, load_domain
from reader import PaperDocument
from pipeline import PipelineResult
from llm import call_llm_with_history
from token_utils import estimate_tokens, truncate_to_budget
from exporter import append_qa_to_notes
from prompts import INTERACTIVE_SYSTEM, build_domain_hints, format_prompt

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()


HELP_TEXT = """
[bold]研讨模式指令[/bold]

  [cyan]expand[/cyan] <引理/定理编号>    展开某个定理/引理的证明细节
  [cyan]why[/cyan] <引理/定理编号>       解释为什么需要这个结果
  [cyan]gap[/cyan] <位置描述>            要求补全某处的逻辑跳跃
  [cyan]compare[/cyan] <A> and <B>       对比两个结果的异同
  [cyan]what-if[/cyan] <假设条件变化>     假设性提问
  [cyan]example[/cyan] <定理编号>         给出具体例子帮助理解
  [cyan]ask[/cyan] <任意问题>             自由提问

  [cyan]save[/cyan]                       将上一轮 QA 保存到笔记
  [cyan]save all[/cyan]                   将所有 QA 保存到笔记
  [cyan]help[/cyan]                       显示此帮助
  [cyan]quit[/cyan] / [cyan]exit[/cyan]                  退出研讨模式
"""


def run_interactive(
    paper: PaperDocument,
    result: PipelineResult,
    config: AppConfig,
    notes_path: Optional[str] = None,
):
    """
    运行研讨模式交互循环。

    Args:
        paper: 解析后的论文
        result: Pipeline 运行结果
        config: 配置
        notes_path: 笔记文件路径（用于 save 功能）
    """
    if not config.interactive.enabled:
        return

    domain_data = load_domain(config.domain) if config.domain else None
    domain_hints = build_domain_hints(domain_data)

    # 构建系统 prompt
    # 只带 Layer 1 + Layer 2 + Section 索引，不带全文
    notes_summary = result.layer1
    if result.layer2:
        notes_summary += "\n\n" + result.layer2

    notes_summary = truncate_to_budget(notes_summary, 2000)
    section_index = paper.get_section_index()

    system_prompt = format_prompt(
        INTERACTIVE_SYSTEM,
        domain_hints=domain_hints,
        notes_summary=notes_summary,
        section_index=section_index,
        language=config.output.language,
    )

    # 消息历史
    messages = []
    qa_history = []  # (question, answer) 对，用于 save

    console.print("\n" + "=" * 60)
    console.print("[bold green]进入研讨模式[/bold green]")
    console.print('输入问题与论文"对谈"，输入 help 查看指令，quit 退出')
    console.print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("📖 > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n退出研讨模式")
            break

        if not user_input:
            continue

        # 处理特殊指令
        cmd = user_input.lower()

        if cmd in ('quit', 'exit', 'q'):
            console.print("退出研讨模式")
            break

        if cmd == 'help':
            console.print(HELP_TEXT)
            continue

        if cmd == 'save' and qa_history:
            q, a = qa_history[-1]
            if notes_path:
                append_qa_to_notes(notes_path, q, a)
                console.print("[green]上一轮 QA 已保存到笔记[/green]")
            else:
                console.print("[yellow]没有笔记文件路径，无法保存[/yellow]")
            continue

        if cmd == 'save all' and qa_history:
            if notes_path:
                for q, a in qa_history:
                    append_qa_to_notes(notes_path, q, a)
                console.print(f"[green]已保存 {len(qa_history)} 条 QA 到笔记[/green]")
            else:
                console.print("[yellow]没有笔记文件路径，无法保存[/yellow]")
            continue

        # 构建用户消息
        actual_question = _build_question(user_input, paper)

        # 管理上下文窗口
        messages.append({"role": "user", "content": actual_question})

        # 保留最近 N 轮，压缩更早的
        max_history = config.interactive.context_window * 2  # 每轮有 user + assistant
        if len(messages) > max_history and config.interactive.history_compression:
            messages = _compress_history(messages, max_history, config)

        # 调用 LLM
        try:
            response = call_llm_with_history(
                model=config.models.interactive,
                system_prompt=system_prompt,
                messages=messages,
                config=config,
                max_tokens=config.token_budget.interactive.output_max,
                temperature=0.3,
            )
        except Exception as e:
            console.print(f"[red]调用失败: {e}[/red]")
            messages.pop()  # 移除失败的消息
            continue

        messages.append({"role": "assistant", "content": response})
        qa_history.append((user_input, response))

        # 渲染输出
        console.print()
        console.print(Panel(Markdown(response), border_style="blue", padding=(1, 2)))
        console.print()

        # 自动保存
        if config.interactive.auto_save and notes_path:
            append_qa_to_notes(notes_path, user_input, response)


def _build_question(user_input: str, paper: PaperDocument) -> str:
    """
    根据用户输入构建实际发给模型的问题。
    如果用户引用了特定 section，把对应原文附上。
    """
    # 解析指令前缀
    prefixes = {
        'expand': '请展开以下定理/引理的证明细节，指出原文中的具体位置：',
        'why': '请解释为什么需要以下结果，它在主线证明中不可替代的原因是什么？指出原文位置：',
        'gap': '以下位置存在逻辑跳跃，请指出读者应该关注原文的哪些地方来填补这个gap：',
        'compare': '请对比以下两个结果的异同和适用范围，指出原文中的相关讨论位置：',
        'what-if': '以下是一个假设性问题。请基于原文分析如果条件改变会怎样，指出哪一步会出问题：',
        'example': '请给出以下定理的一个具体例子或特殊情形来帮助理解，如果原文有例子请指出位置：',
        'ask': '',
    }

    question = user_input
    for prefix, instruction in prefixes.items():
        if user_input.lower().startswith(prefix + ' '):
            question = instruction + user_input[len(prefix) + 1:]
            break

    # 检查是否引用了特定 section，如果有就附上原文片段
    section_refs = re.findall(r'sec[\d.]+|[Ss]ection\s+([\d.]+)', user_input)
    if section_refs:
        extra_context = []
        for ref in section_refs:
            sec_id = ref if ref.startswith('sec') else f"sec{ref}"
            sec = paper.get_section_by_id(sec_id)
            if sec:
                # 只附上前 500 词
                snippet = sec.content[:2000]
                extra_context.append(f"\n[参考原文 {sec.id} - {sec.title}]\n{snippet}")
        if extra_context:
            question += "\n\n" + "\n".join(extra_context)

    return question


def _compress_history(messages: list, keep_count: int, config: AppConfig) -> list:
    """
    压缩历史消息。保留最近 keep_count 条，
    更早的压缩成一条摘要。
    """
    if len(messages) <= keep_count:
        return messages

    old_messages = messages[:-keep_count]
    recent_messages = messages[-keep_count:]

    # 将旧消息压缩成摘要
    summary_parts = []
    for msg in old_messages:
        role = "问" if msg["role"] == "user" else "答"
        # 只保留每条消息的前 100 字符
        content_short = msg["content"][:100]
        if len(msg["content"]) > 100:
            content_short += "..."
        summary_parts.append(f"{role}: {content_short}")

    summary = "[之前的讨论摘要]\n" + "\n".join(summary_parts)

    return [{"role": "user", "content": summary}] + recent_messages
