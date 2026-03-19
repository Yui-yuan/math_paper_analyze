"""Token 计数、预算控制、超限压缩"""

import re
from typing import Optional
from config import AppConfig, TokenBudgetStage


def estimate_tokens(text: str) -> int:
    """
    粗略估算文本的 token 数。
    经验法则：英文约 1 token/4 字符，中文约 1 token/1.5 字符。
    混合文本取加权平均。
    """
    if not text:
        return 0

    # 统计中文字符数
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(text) - chinese_chars

    tokens = chinese_chars / 1.5 + other_chars / 4
    return int(tokens)


def check_budget(text: str, budget: TokenBudgetStage, role: str = "input") -> dict:
    """
    检查文本是否超出预算。

    Returns:
        {
            "tokens": int,
            "max": int,
            "over_budget": bool,
            "excess": int,  # 超出多少
        }
    """
    tokens = estimate_tokens(text)
    max_tokens = budget.input_max if role == "input" else budget.output_max
    return {
        "tokens": tokens,
        "max": max_tokens,
        "over_budget": tokens > max_tokens,
        "excess": max(0, tokens - max_tokens),
    }


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """
    将文本截断到预算内。按段落截断，尽量不切断句子。
    """
    current = estimate_tokens(text)
    if current <= max_tokens:
        return text

    # 按段落切分
    paragraphs = text.split('\n\n')
    result = []
    running_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if running_tokens + para_tokens > max_tokens:
            # 看看剩余预算能不能放下部分内容
            remaining = max_tokens - running_tokens
            if remaining > 50:  # 至少留 50 token 才截
                sentences = re.split(r'(?<=[.!?。！？])\s+', para)
                for sent in sentences:
                    sent_tokens = estimate_tokens(sent)
                    if running_tokens + sent_tokens > max_tokens:
                        break
                    result.append(sent)
                    running_tokens += sent_tokens
            break
        result.append(para)
        running_tokens += para_tokens

    return '\n\n'.join(result)


def format_token_report(stages: dict) -> str:
    """
    格式化 token 消耗预估报告。

    Args:
        stages: {"stage_name": {"input": int, "output": int, "model": str, "rounds": int}}
    Returns:
        格式化的表格字符串
    """
    from llm import estimate_cost

    lines = ["预估 token 消耗："]
    total_cost = 0.0
    total_tokens = 0

    for name, info in stages.items():
        inp = info["input"]
        out = info["output"]
        model = info["model"]
        rounds = info.get("rounds", 1)
        cost = estimate_cost(model, inp * rounds, out * rounds)
        total_cost += cost
        total_tokens += (inp + out) * rounds
        lines.append(f"  {name:12s}: ~{(inp + out) * rounds:>6d} tokens  (${cost:.4f})")

    lines.append(f"  {'总计':12s}: ~{total_tokens:>6d} tokens  (${total_cost:.4f})")
    return "\n".join(lines)
