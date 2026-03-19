"""Math Paper Reader — CLI 入口"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from config import load_config, list_domains, AppConfig
from reader import read_paper
from preprocessor import preprocess
from pipeline import run_pipeline
from exporter import export_notes
from interactive import run_interactive

console = Console()


BANNER = """
╔══════════════════════════════════════════╗
║       Math Paper Reader  v0.1           ║
║   AI-powered mathematical paper reader  ║
╚══════════════════════════════════════════╝
"""


def main():
    parser = argparse.ArgumentParser(
        description="Math Paper Reader — AI 辅助数学论文阅读工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "paper",
        nargs="?",
        help="论文文件路径 (PDF, LaTeX, Markdown, 文本)",
    )

    parser.add_argument(
        "--domain", "-d",
        help="数学领域 (如 algebraic_geometry, number_theory, pde 等)",
    )

    parser.add_argument(
        "--config", "-c",
        help="配置文件路径 (默认: config.yaml)",
    )

    parser.add_argument(
        "--list-domains",
        action="store_true",
        help="列出所有可用的数学领域",
    )

    parser.add_argument(
        "--list-papers",
        action="store_true",
        help="列出 papers/ 目录下所有论文文件",
    )

    parser.add_argument(
        "--output-dir", "-o",
        help="输出目录",
    )

    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "latex", "both"],
        help="输出格式",
    )

    parser.add_argument(
        "--language", "-l",
        choices=["zh", "en"],
        help="输出语言",
    )

    parser.add_argument(
        "--max-rounds", "-r",
        type=int,
        help="最大自迭代轮数",
    )

    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="跳过研讨模式",
    )

    parser.add_argument(
        "--model-extract",
        help="Stage 1 提取使用的模型",
    )
    parser.add_argument(
        "--model-critique",
        help="Stage 2 批判使用的模型",
    )
    parser.add_argument(
        "--model-synthesize",
        help="Stage 3 修正使用的模型",
    )

    args = parser.parse_args()

    # ---- 加载配置（提前加载以获取 papers_dir）----
    config = load_config(args.config)
    base_dir = Path(__file__).parent
    papers_dir = base_dir / config.papers_dir

    # ---- 列出领域 ----
    if args.list_domains:
        domains = list_domains()
        if domains:
            console.print("[bold]可用的数学领域：[/bold]")
            for d in sorted(domains):
                console.print(f"  - {d}")
        else:
            console.print("[yellow]未找到领域配置文件[/yellow]")
        return

    # ---- 列出论文 ----
    if args.list_papers:
        papers_dir.mkdir(parents=True, exist_ok=True)
        paper_files = sorted(
            p for p in papers_dir.iterdir()
            if p.is_file() and p.suffix.lower() in ('.pdf', '.tex', '.latex', '.md', '.markdown', '.txt')
        )
        if paper_files:
            console.print(f"[bold]papers/ 目录下的论文 ({papers_dir})：[/bold]")
            for p in paper_files:
                size_kb = p.stat().st_size / 1024
                console.print(f"  - {p.name}  ({size_kb:.0f} KB)")
        else:
            console.print(f"[yellow]papers/ 目录为空，请将论文放入: {papers_dir}[/yellow]")
        return

    # ---- 检查论文路径 ----
    if not args.paper:
        console.print(BANNER)
        parser.print_help()
        return

    paper_path = Path(args.paper)

    # 如果不是完整路径或文件不存在，尝试在 papers/ 目录下查找
    if not paper_path.exists():
        papers_candidate = papers_dir / args.paper
        if papers_candidate.exists():
            paper_path = papers_candidate
        else:
            console.print(f"[red]文件不存在: {args.paper}[/red]")
            console.print(f"[dim]已在当前目录和 {papers_dir} 中查找[/dim]")
            sys.exit(1)

    # ---- 应用命令行覆盖重新加载配置 ----
    overrides = {}
    if args.domain:
        overrides['domain'] = args.domain
    if args.output_dir:
        overrides['output.output_dir'] = args.output_dir
    if args.format:
        if args.format == 'both':
            overrides['output.format'] = ['markdown', 'latex']
        else:
            overrides['output.format'] = [args.format]
    if args.language:
        overrides['output.language'] = args.language
    if args.max_rounds:
        overrides['pipeline.max_rounds'] = args.max_rounds
    if args.no_interactive:
        overrides['interactive.enabled'] = False
    if args.model_extract:
        overrides['models.extract'] = args.model_extract
    if args.model_critique:
        overrides['models.critique'] = args.model_critique
    if args.model_synthesize:
        overrides['models.synthesize'] = args.model_synthesize

    if overrides:
        config = load_config(args.config, overrides)

    # ---- 开始处理 ----
    console.print(BANNER)
    console.print(f"论文: [bold]{paper_path.name}[/bold]")
    if config.domain:
        console.print(f"领域: [bold]{config.domain}[/bold]")
    console.print(f"模型: 提取={config.models.extract}")
    console.print(f"       批判={config.models.critique}")
    console.print(f"       修正={config.models.synthesize}")
    console.print()

    # Step 1: 解析论文
    console.print("[bold]Step 1:[/bold] 解析论文...")
    paper = read_paper(str(paper_path))
    console.print(f"  标题: {paper.title}")
    console.print(f"  Section 数量: {len(paper.sections)}")
    console.print(f"  总 token 估计: ~{paper.total_tokens}")

    # Step 2: 预处理
    if config.optimization.preprocess_compression:
        console.print("\n[bold]Step 2:[/bold] 预处理压缩...")
        paper = preprocess(paper, config)
        new_total = sum(s.token_count for s in paper.sections)
        console.print(f"  处理后 Section 数量: {len(paper.sections)}")
        console.print(f"  处理后 token 估计: ~{new_total}")
    else:
        console.print("\n[bold]Step 2:[/bold] 跳过预处理")

    # Step 3: 运行 Pipeline
    console.print("\n[bold]Step 3:[/bold] 运行分析 Pipeline...")
    result = run_pipeline(paper, config)

    # Step 4: 导出笔记
    console.print("\n[bold]Step 4:[/bold] 导出笔记...")
    generated_files = export_notes(paper, result, config)

    # Step 5: 研讨模式
    if config.interactive.enabled and generated_files:
        notes_path = generated_files[0]  # 用第一个生成的文件作为 save 目标
        run_interactive(paper, result, config, notes_path)
    elif config.interactive.enabled:
        run_interactive(paper, result, config)

    console.print("\n[bold green]完成！[/bold green]")


if __name__ == "__main__":
    main()
