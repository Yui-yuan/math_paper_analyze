# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Math Paper Reader is an AI-powered CLI tool that generates structured research notes from mathematical papers (PDF, LaTeX, Markdown, plain text) using a three-stage LLM pipeline: Extract → Critique → Synthesize, with self-iteration until convergence.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run on a paper (auto-searches in papers/ directory)
python main.py paper.pdf --domain algebraic_geometry

# List papers in papers/ directory
python main.py --list-papers

# List supported mathematical domains
python main.py --list-domains

# Use Chinese API models (cheap)
python main.py paper.pdf --model-extract deepseek/deepseek-chat --model-critique deepseek/deepseek-reasoner

# Use Anthropic models
python main.py paper.pdf --model-critique anthropic/claude-opus-4-20250115

# Skip interactive mode
python main.py paper.pdf --no-interactive
```

API keys via environment variables: `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, `MINIMAX_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.

## Architecture

### Pipeline flow

```
Input PDF → Parse → Preprocess → [Extract → Critique → Synthesize] × N rounds → Export .md/.tex → Interactive Q&A
```

### Key modules

| Module | Role |
|--------|------|
| `main.py` | CLI entry, argument parsing, orchestration; auto-searches `papers/` dir |
| `config.py` | Loads `config.yaml`, provider routing (`ProviderConfig`), CLI overrides |
| `llm.py` | Provider-based routing: Anthropic native SDK or OpenAI-compatible SDK for DeepSeek/Moonshot/MiniMax/OpenAI. No litellm dependency |
| `reader.py` | PDF (PyMuPDF), LaTeX, Markdown, TXT → `PaperDocument` with `Section` index |
| `preprocessor.py` | Removes boilerplate, compresses non-core sections via cheap model |
| `prompts.py` | Three-stage prompt templates + domain enhancement injection from `domains/*.yaml` |
| `pipeline.py` | Two-pass reading + self-iteration (incremental critique, convergence detection) |
| `exporter.py` | Markdown (Obsidian-compatible) and LaTeX export |
| `interactive.py` | Post-pipeline Q&A loop; "guide, don't repeat" philosophy |
| `token_utils.py` | Token estimation (Chinese/English hybrid), budget enforcement, truncation |

### Provider system

`config.yaml` has a `providers:` block. Each provider has `base_url`, `api_key_env`, `compatible_mode`. Model names use `"provider/model"` format (e.g., `"deepseek/deepseek-chat"`). `llm.py` resolves provider → routes to Anthropic SDK or OpenAI-compatible SDK.

Supported: Anthropic, OpenAI, DeepSeek, Moonshot (Kimi), MiniMax, any OpenAI-compatible endpoint.

### Key design decisions

- **Two-pass reading**: First pass reads skeleton only (~10-15% tokens), second pass loads only sections marked as critical
- **Incremental critique**: Round 2+ only checks previously flagged issues, not full re-review
- **Interactive mode is "guide, don't repeat"**: Answers point to original paper locations (Section, page, equation numbers) rather than re-deriving
- **Provider-based routing replaces litellm**: Direct SDK calls for better control and fewer dependencies
- **Default models are DeepSeek**: Cheapest option; users can switch per-stage via config or CLI

### Domain system

`domains/` contains 8 YAML files with `context_hints`, `common_techniques`, `critical_assumptions`, `standard_notation`. Injected into Stage 1 (extraction) and Stage 2 (critique) prompts when `--domain` is specified.

### Output structure

- **Layer 1** (300-500 words): Overview, main theorem, dependency graph, innovation
- **Layer 2** (800-1500 words): Definitions, lemma statements, proof strategy maps, technique callouts
- **Layer 3** (optional): Detailed proof reconstruction with `[!added]` and `[!gap]` markers
- **Appendix**: Notation table, reading references
