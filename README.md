# Math Paper Reader

> ⚠️ **开发中** — 本项目仍在完善阶段，许多功能有待进一步改进和优化。欢迎反馈 Bug 和建议！

AI 辅助数学论文阅读工具。通过三阶段 Pipeline（提取 → 批判 → 修正）自动生成高质量的论文研读笔记，支持可选的第四阶段（研究突破问题生成），并支持交互式追问。

---

## 目录

- [安装](#安装)
- [论文管理](#论文管理)
- [快速开始](#快速开始)
- [完整用法](#完整用法)
- [Section 与页码过滤](#section-与页码过滤)
- [配置文件](#配置文件)
- [自定义 Prompt](#自定义-prompt)
- [数学领域支持](#数学领域支持)
- [输出格式说明](#输出格式说明)
- [研讨模式](#研讨模式)
- [Token 优化机制](#token-优化机制)
- [断点续跑](#断点续跑)
- [常见问题](#常见问题)

---

## 安装

### 1. 环境要求

- Python 3.9+
- 至少一个 LLM API key（Anthropic / OpenAI / 其他 litellm 支持的服务）

### 2. 安装依赖

```bash
cd C:\Users\Lenovo\iCloudDrive\ai\math-paper-reader
pip install -r requirements.txt
```

依赖列表：

| 包 | 用途 |
|---|---|
| openai | OpenAI 兼容接口调用（同时支持 DeepSeek/Moonshot/MiniMax 等） |
| anthropic | Anthropic 原生 SDK |
| PyMuPDF | PDF 文本提取 |
| rich | 终端美化输出 |
| pyyaml | YAML 配置文件解析 |
| tiktoken | Token 计数 |
| Jinja2 | 模板引擎 |

### 3. 设置 API Key

根据你使用的模型服务商，设置对应的环境变量。默认使用 DeepSeek（最便宜）：

**Windows (CMD):**
```cmd
set DEEPSEEK_API_KEY=sk-xxxxx
```

**Windows (PowerShell):**
```powershell
$env:DEEPSEEK_API_KEY = "sk-xxxxx"
```

**Linux / macOS / Git Bash:**
```bash
export DEEPSEEK_API_KEY="sk-xxxxx"
```

其他服务商：
```bash
export MOONSHOT_API_KEY="sk-xxxxx"     # Moonshot (Kimi)
export MINIMAX_API_KEY="xxxxx"         # MiniMax
export ANTHROPIC_API_KEY="sk-ant-xxx"  # Anthropic (Claude)
export OPENAI_API_KEY="sk-xxxxx"       # OpenAI
export GEMINI_API_KEY="xxxxx"          # Google Gemini
```

你也可以在系统环境变量中永久设置，避免每次都输入。只需要设置你实际使用的服务商的 key。

---

## 论文管理

将你要阅读的论文文件放入项目根目录的 `papers/` 文件夹中：

```
math-paper-reader/
  papers/
    hodge_conjecture.pdf
    riemann_hypothesis.tex
    navier_stokes.md
    ...
```

运行时只需要指定文件名（不需要写完整路径），程序会自动在 `papers/` 目录下查找：

```bash
python main.py hodge_conjecture.pdf
```

你也可以查看 `papers/` 中所有可用的论文：

```bash
python main.py --list-papers
```

---

## 快速开始

最简单的用法——把 PDF 放进 `papers/` 文件夹，然后：

```bash
python main.py your_paper.pdf
```

程序会：
1. 从 `papers/` 目录读取论文，提取文本和 Section 结构
2. 预处理压缩，删除参考文献等冗余内容
3. 运行三阶段 Pipeline（提取 → 批判 → 修正），自动迭代直到收敛
4. 在 `output/` 目录生成 Markdown 笔记
5. 进入研讨模式，你可以对笔记内容追问

**指定数学领域（推荐）：**

```bash
python main.py your_paper.pdf --domain algebraic_geometry
```

指定领域后，模型会获得该领域的专业提示（常见技巧、易遗漏假设、标准记号），生成质量更高。

**可选高级功能：**
- **按 Section 过滤**：`--sections "keyword"`，只读论文的某些章节
- **按页码过滤**：`--pages 5-12`，只读 PDF 的指定页面
- **研究问题生成**：`--research-questions`，在笔记末尾自动生成 5 个研究突破问题

更多细节见 [Section 与页码过滤](#section-与页码过滤) 和 [输出格式说明 → Layer 4](#layer-4研究突破问题可选需启用-research-questions)。

---

## 完整用法

```
python main.py [论文路径] [选项]
```

### 所有命令行参数

| 参数 | 缩写 | 说明 | 示例 |
|------|------|------|------|
| `paper` | | 论文文件名（自动在 `papers/` 目录下查找）或完整路径 | `paper.pdf` |
| `--domain` | `-d` | 数学领域 | `-d number_theory` |
| `--config` | `-c` | 自定义配置文件路径 | `-c my_config.yaml` |
| `--output-dir` | `-o` | 输出目录 | `-o ./notes` |
| `--format` | `-f` | 输出格式：markdown / latex / both | `-f both` |
| `--language` | `-l` | 输出语言：zh（中文）/ en（英文） | `-l en` |
| `--max-rounds` | `-r` | 最大自迭代轮数 | `-r 5` |
| `--sections` | `-s` | 只分析指定 Section（逗号分隔的标题关键词） | `-s "Proof,Main Theorem"` |
| `--pages` | `-p` | 只分析指定页码范围（仅对 PDF 有效） | `-p 5-12` 或 `-p 7` |
| `--research-questions` | | 生成研究突破问题（Stage 4），在笔记末尾附加 5 个问题 | |
| `--no-interactive` | | 跳过研讨模式，直接输出笔记后退出 | |
| `--model-extract` | | Stage 1（提取）使用的模型 | `--model-extract openai/gpt-4o` |
| `--model-critique` | | Stage 2（批判）使用的模型 | `--model-critique anthropic/claude-opus-4-6` |
| `--model-synthesize` | | Stage 3（修正）使用的模型 | `--model-synthesize openai/gpt-4o` |
| `--list-domains` | | 列出所有可用的数学领域 | |
| `--list-papers` | | 列出 `papers/` 目录下所有论文文件 | |

### 用法示例

```bash
# 查看 papers/ 目录下有哪些论文
python main.py --list-papers

# 基本：读 papers/ 里的一篇 PDF（只写文件名）
python main.py hodge_conjecture.pdf

# 也可以用完整路径读其他位置的论文
python main.py "C:/Documents/other_paper.pdf"

# 指定领域 + 中文输出
python main.py paper.pdf -d pde -l zh

# 同时输出 Markdown 和 LaTeX
python main.py paper.pdf -f both

# 用 OpenAI 模型做提取，Anthropic 做批判
python main.py paper.pdf --model-extract openai/gpt-5.4 --model-critique anthropic/claude-opus-4-6

# 增加迭代轮数（更精细，但更费 token）
python main.py paper.pdf -r 5

# 只分析某些 Section（按标题关键词）
python main.py paper.pdf --sections "Main Theorem,Proof"

# 只分析某个页码范围（仅对 PDF）
python main.py paper.pdf --pages 5-12

# 同时用 Section 和页码过滤（会请你确认）
python main.py paper.pdf --sections "Proof" --pages 1-20

# 启用研究突破问题生成（Stage 4，会在笔记末尾添加 5 个研究问题）
python main.py paper.pdf --research-questions

# 只要笔记，不进入研讨模式
python main.py paper.pdf --no-interactive

# 读 LaTeX 源文件
python main.py paper.tex -d algebraic_geometry

# 查看支持哪些领域
python main.py --list-domains
```

### 支持的输入格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| PDF | `.pdf` | 自动提取文本（需要 PyMuPDF） |
| LaTeX | `.tex`, `.latex` | 解析 `\section`, `\begin{theorem}` 等结构 |
| Markdown | `.md`, `.markdown` | 按标题层级解析 |
| 纯文本 | `.txt` 或其他 | 尝试按 Section 编号解析 |

---

## Section 与页码过滤

### 按 Section 标题过滤

如果论文很长，只想分析某些特定的章节或部分，可以用 `--sections` 参数指定：

```bash
python main.py paper.pdf --sections "Proof,Main Theorem"
```

匹配规则：
- 多个关键词用逗号分隔
- **不区分大小写**（`proof` 和 `Proof` 效果相同）
- **模糊匹配**（只要 Section 标题中**包含**关键词即可匹配，不需完全相同）
- 所有匹配的 Section 都会被选中

### 按页码范围过滤

仅对 PDF 有效。用 `--pages` 参数指定页码范围：

```bash
# 只分析第 5-12 页
python main.py paper.pdf --pages 5-12

# 或指定单页
python main.py paper.pdf --pages 7
```

### 同时用两种过滤条件

当同时指定 `--sections` 和 `--pages` 时，两个条件都会应用（**取交集**）：

```bash
# 只分析"第 5-12 页"且"标题包含 Proof 的" Section
python main.py paper.pdf --sections "Proof" --pages 5-12
```

### 确认对话

无论用哪种过滤方式，程序都会展示一个表格，列出：
- 匹配到的所有 Section ID、标题、页码、Token 估计
- 合计 Token 数

你可以：
- **Y** (或 **enter**）：确认，开始分析
- **N**（或 **no** / **否**）：取消，不进行分析

这样可以避免误操作，特别是在大论文上。

---

## 配置文件

默认配置文件为项目根目录的 `config.yaml`。你可以直接编辑它，或者用 `--config` 指定自己的配置文件。

### 关键配置项说明

#### Provider（服务商）配置

程序支持多个 API 服务商，在 `config.yaml` 的 `providers:` 区块中配置：

```yaml
providers:
  deepseek:
    base_url: "https://api.deepseek.com/v1"
    api_key_env: DEEPSEEK_API_KEY

  moonshot:
    base_url: "https://api.moonshot.cn/v1"
    api_key_env: MOONSHOT_API_KEY

  minimax:
    base_url: "https://api.minimax.chat/v1"
    api_key_env: MINIMAX_API_KEY

  anthropic:
    base_url: "https://api.anthropic.com/v1"
    api_key_env: ANTHROPIC_API_KEY
    compatible_mode: false  # Anthropic 用原生 SDK

  openai:
    base_url: "https://api.openai.com/v1"
    api_key_env: OPENAI_API_KEY

  # 自定义服务商（任何兼容 OpenAI 接口的服务）
  my_provider:
    base_url: "https://your-api.com/v1"
    api_key_env: MY_API_KEY
```

#### 模型配置

每个阶段独立选择 `provider/model`：

```yaml
models:
  preprocess: "deepseek/deepseek-chat"          # 便宜，适合预处理
  extract: "deepseek/deepseek-chat"             # 提取
  critique: "deepseek/deepseek-reasoner"        # 推理强，适合批判
  synthesize: "deepseek/deepseek-chat"          # 修正
  interactive: "deepseek/deepseek-chat"         # 研讨模式
```

可用模型：

| 模型 | 名称 | 特点 | 大致价格 |
|------|------|------|---------|
| DeepSeek Chat | `deepseek/deepseek-chat` | 便宜好用 | ¥1/M tokens |
| DeepSeek Reasoner | `deepseek/deepseek-reasoner` | 推理强 | ¥4/M tokens |
| Kimi K2.5 | `moonshot/kimi-k2.5` | 原生多模态，1T MoE，256K 上下文 | ¥60/M tokens |
| MiniMax M2.7 | `minimax/MiniMax-M2.7` | 便宜 | $0.3/$1.2 per MTok |
| Claude Opus 4.6 | `anthropic/claude-opus-4-6` | 最强，1M上下文 | $5/$25 per MTok |
| Claude Sonnet 4.6 | `anthropic/claude-sonnet-4-6` | 平衡，1M上下文 | $3/$15 per MTok |
| Claude Haiku 4.5 | `anthropic/claude-haiku-4-5-20251001` | 快速 | $1/$5 per MTok |
| GPT-5.4 | `openai/gpt-5.4` | OpenAI 主力 | $2.5/$15 per MTok |
| GPT-5.4 mini | `openai/gpt-5.4-mini` | 便宜 | $0.75/$4.5 per MTok |
| Gemini 3.1 Pro | `gemini/gemini-3.1-pro-preview` | Google 最新最强（preview） | $2/$4 per MTok |
| Gemini 3.1 Flash-Lite | `gemini/gemini-3.1-flash-lite-preview` | 最新轻量（preview） | $0.25/$0.50 per MTok |
| Gemini 2.5 Pro | `gemini/gemini-2.5-pro` | 稳定版旗舰，1M上下文 | $1.25/$10 per MTok |
| Gemini 2.5 Flash | `gemini/gemini-2.5-flash` | 快速便宜 | $0.30/$1.00 per MTok |
| Gemini 2.5 Flash-Lite | `gemini/gemini-2.5-flash-lite` | 最便宜 | $0.10/$0.40 per MTok |

**省钱建议**：默认配置使用 DeepSeek，全流程跑完一篇论文大约 ¥0.1-0.5。如果追求最高质量，批判阶段换成 `anthropic/claude-opus-4-6` 或 `openai/gpt-5.4`。

#### Pipeline 配置

```yaml
pipeline:
  max_rounds: 3              # 最大迭代轮数（越多越精细，但越费 token）
  convergence_threshold: 2   # 当批判意见 ≤ 2 条时停止迭代

# Stage 4（可选）：研究突破问题生成
research_questions:
  enabled: false             # 默认关闭，用 --research-questions 或这里设为 true 启用
  model: "deepseek/deepseek-reasoner"  # 推荐用推理强的模型
  num_questions: 5           # 生成问题数量
```

#### Token 预算

```yaml
token_budget:
  preprocess:  { input_max: 8000 }
  extract:     { input_max: 6000, output_max: 2000 }
  critique:    { input_max: 3000, output_max: 1000 }
  synthesize:  { input_max: 4000, output_max: 2500 }
  interactive: { input_max: 3000, output_max: 500 }
```

如果你的论文特别长或特别复杂，可以适当调大这些值。

#### 输出配置

```yaml
output:
  format: [markdown]          # 可选：markdown, latex
  language: zh                # zh 中文 / en 英文
  layers: [1, 2]              # 输出哪些层（1=总览, 2=技术骨架, 3=证明细节）
  layer3_targets: auto        # auto=自动选最核心的 / manual / all
  max_layer3_proofs: 2        # Layer 3 最多展开几个证明
  output_dir: "./output"      # 输出目录
```

---

## 自定义 Prompt

所有 LLM 的指令模板都集中在 `prompts.py` 文件中，你可以直接修改来调整输出风格和内容侧重。

### Prompt 结构

| 变量名 | 阶段 | 作用 |
|--------|------|------|
| `EXTRACT_SYSTEM` | Stage 1 系统提示 | 控制提取风格：详细程度、是否要求公式、Layer 1/2/3 的内容要求 |
| `EXTRACT_USER_FIRST_PASS` | Stage 1 粗读 | 第一遍只看骨架时的提问方式 |
| `EXTRACT_USER_SECOND_PASS` | Stage 1 精读 | 精读核心 Section 时的输出要求 |
| `CRITIQUE_SYSTEM` | Stage 2 系统提示 | 批判审查清单：改这里可以增减审查维度 |
| `CRITIQUE_USER_FULL` | Stage 2 首轮批判 | 第一轮全面批判的提问 |
| `CRITIQUE_USER_INCREMENTAL` | Stage 2 增量批判 | 后续轮次只审查修改部分 |
| `SYNTHESIZE_SYSTEM` | Stage 3 系统提示 | 修正时的写作原则 |
| `SYNTHESIZE_USER` | Stage 3 修正 | 修正时的具体要求 |
| `QUESTIONS_SYSTEM` | Stage 4 系统提示 | 研究问题的生成原则 |
| `INTERACTIVE_SYSTEM` | 研讨模式 | 追问时的回答风格 |

### 常见调整场景

**想要更详细的证明（推荐）：**

修改 `EXTRACT_SYSTEM` 中 Layer 3 部分，例如增加对特定类型构造的要求：

```python
# 在 EXTRACT_SYSTEM 的 "核心证明复现" 部分末尾加入：
"对于每个函子构造，必须明确写出：定义域、陪域、映射规则（用公式）、以及它是如何与其他构造交互的。"
```

**想要更精简的输出：**

在 `EXTRACT_SYSTEM` 末尾把 Layer 1/2 字数限制改小，例如：
```python
"- Layer 1 控制在 200-300 词，Layer 2 控制在 500-800 词"
```

**想要更严格的批判：**

在 `CRITIQUE_SYSTEM` 的审查清单中新增条目，例如：
```python
"7. **符号一致性**：笔记中使用的记号是否与原文完全一致？同一对象在不同地方是否用了不同符号？"
```

**想要针对特定领域调整：**

`domains/` 目录下的 YAML 文件可以添加更多 `context_hints` 和 `critical_assumptions`，这些会自动注入到 Stage 1 和 Stage 2 的 prompt 中，不需要修改 `prompts.py`。

---

## 数学领域支持

目前内置 8 个数学领域：

| 领域 ID | 名称 |
|---------|------|
| `algebraic_geometry` | 代数几何 |
| `number_theory` | 数论 |
| `pde` | 偏微分方程 |
| `topology` | 拓扑学 |
| `probability` | 概率论与随机分析 |
| `representation_theory` | 表示论 |
| `combinatorics` | 组合数学 |
| `differential_geometry` | 微分几何 |

查看完整列表：

```bash
python main.py --list-domains
```

### 领域增强的作用

指定领域后，模型在各阶段会获得额外的专业提示：

- **Stage 1（提取）**：领域特有的注意事项（如代数几何中 scheme vs variety 的区分）、常见技巧列表、标准记号表
- **Stage 2（批判）**：领域易遗漏的假设条件（如 "proper 和 projective 不等价"）

不指定领域也能用，只是少了这层专业提示。

### 自定义领域

在 `domains/` 目录下新建 YAML 文件即可。格式参考已有文件：

```yaml
name: my_domain
display_name: 我的领域

context_hints:
  - 注意事项 1
  - 注意事项 2

common_techniques:
  - name: 技巧名称
    description: 简短描述

critical_assumptions:
  - "容易遗漏的假设 1"

standard_notation:
  "\\symbol": 含义
```

---

## 输出格式说明

生成的笔记按四层组织（后两层可选）：

### Layer 1：一页纸总览（300-500 词）

- **核心问题**：这篇文章要解决什么？（1-2 句话）
- **主定理**：完整 LaTeX 陈述，含所有假设
- **逻辑依赖图**：树形结构展示引理→定理的推导链
- **一句话创新点**：核心新技巧

### Layer 2：技术骨架（800-1500 词）

- **关键定义与记号**：仅非标准的定义
- **各引理精确陈述**：每条附 1-2 句说明在主线中的角色
- **证明策略地图**：每个关键证明的 输入→核心操作→输出
- **关键技巧标注**：具体操作 + 适用场景

### Layer 3：证明细节（可选，每个 500-2000 词）

- 对最核心证明的详细复现
- 补充的细节用 `> [!added]` 标出
- 无法复现的步骤用 `> [!gap]` 标出

### Layer 4：研究突破问题（可选，需启用 `--research-questions`）

用一个强大的模型（如 Claude Opus 或 GPT-4o）基于完整笔记提出 5 个研究突破问题。每个问题包括：
- 问题描述：清楚地阐述这是什么问题及其重要性
- 与论文的联系：指出如何从本文的技术或结果推广/变化这个问题
- 潜在价值：为什么这个问题值得研究

启用方式：
```bash
python main.py paper.pdf --research-questions
```

或在 `config.yaml` 中设置：
```yaml
research_questions:
  enabled: true
  num_questions: 5           # 可自定义问题数量
  model: "anthropic/claude-opus-4-6"  # 推荐用强模型
```

### 附录

- 术语记号对照表
- 延伸阅读指引

### Obsidian 用户

输出的 Markdown 完全兼容 Obsidian：
- 使用 Obsidian callout 语法（`> [!note]`、`> [!added]`、`> [!technique]`）
- 包含 YAML frontmatter（标题、作者、领域、标签）
- 数学公式使用标准 LaTeX

直接将 `output/` 目录放到你的 Obsidian vault 中即可。

---

## 研讨模式

Pipeline 完成后，程序自动进入研讨模式。你可以对笔记内容追问，模型会**指路式回答**（告诉你去原文哪里找，而不是替你复述）。

### 指令列表

| 指令 | 说明 | 示例 |
|------|------|------|
| `expand <编号>` | 展开某定理/引理的证明细节 | `expand Lemma 3.2` |
| `why <编号>` | 解释为什么需要这个结果 | `why Proposition 2.1` |
| `gap <位置>` | 要求补全某处逻辑跳跃 | `gap Theorem 4.1 step 3` |-v

| `compare <A> and <B>` | 对比两个结果的异同 | `compare Prop 2.1 and Prop 2.3` |
| `what-if <条件变化>` | 假设性提问 | `what-if 去掉条件 p>2` |
| `example <编号>` | 给出具体例子帮助理解 | `example Theorem 1.1` |
| `ask <问题>` | 自由提问（不限格式） | `ask 这篇文章和 XXX 的工作有什么关系？` |
| `save` | 将上一轮 QA 保存到笔记文件 | |
| `save all` | 将所有 QA 保存到笔记文件 | |
| `help` | 显示帮助 | |
| `quit` / `exit` | 退出 | |

也可以直接输入自然语言问题，不需要加 `ask` 前缀。

### QA 保存

- 如果配置了 `auto_save: true`（默认），每轮 QA 自动追加到笔记文件末尾的"研讨记录"区域
- 也可以手动用 `save` / `save all` 指令保存

---

## Token 优化机制

本工具通过四种策略控制 token 消耗：

### 1. 两遍读法

不把整篇论文一次性喂给模型：
- **第一遍（粗读）**：只喂 Abstract + 定理陈述 + Section 标题（约全文 10-15%）
- **第二遍（精读）**：根据第一遍的判断，只加载关键 Section

### 2. 预处理压缩

在喂给主模型之前：
- 删除参考文献、致谢等
- 对非核心 Section 用便宜模型生成一句话摘要替代原文

### 3. 模型分层

不同阶段用不同价位的模型，预处理用最便宜的，只有批判阶段用最贵的。

### 4. 增量批判

自迭代时，第 2 轮起只检查上一轮修改的部分，不全文重审。

### Token 消耗预估

程序在 Pipeline 开始前会显示预估的 token 消耗和费用：

```
预估 token 消耗：
  Stage 1 (粗读):  ~3200 tokens  ($0.0120)
  Stage 1 (精读):  ~4200 tokens  ($0.0180)
  Stage 2 (批判):  ~12000 tokens ($0.1500)
  Stage 3 (修正):  ~13000 tokens ($0.0600)
  总计:            ~32400 tokens ($0.2400)
```

---

## 断点续跑

处理长论文时，LLM 调用可能因超时、网络中断或 API 错误而失败。程序在每一步完成后都会自动保存断点，下次运行时可以从中断处继续，无需从头重跑。

### 断点保存位置

每次 LLM 调用成功后，程序会将状态写入 `cache/` 目录下的 `{paper_hash}_checkpoint.json`。保存时机包括：

| 阶段 | 保存时机 |
|------|---------|
| Stage 1 粗读完成 | 生成 Layer 1 并标记精读 Section 后 |
| Stage 1 精读完成 | 生成 Layer 2/3 后 |
| 每轮**批判**完成 | Stage 2 输出保存后（修正还未开始） |
| 每轮**修正**完成 | Stage 3 输出保存后（下一轮批判还未开始） |
| 迭代全部完成 | 收敛或达到 max_rounds 后 |

这意味着：如果在"第 3 轮修正"阶段超时，下次运行会跳过粗读、精读、第 1/2 轮的全部以及第 3 轮批判，直接从第 3 轮修正继续。

### 使用方法

**默认行为（自动检测，交互式询问）：**
```bash
python main.py paper.pdf
# 如果存在断点，会显示断点信息并询问：
# 是否从断点续跑？[Y/n]
```

**直接续跑（跳过询问）：**
```bash
python main.py paper.pdf --resume
```

**强制从头重跑（忽略断点）：**
```bash
python main.py paper.pdf --fresh
```

### 注意事项

- 断点文件以论文文件路径的 MD5 为标识，**同一论文**才会匹配到对应断点
- Pipeline 成功完成后，断点文件会自动删除
- 如果修改了 `config.yaml` 中的模型或参数后想重跑，使用 `--fresh` 确保从头开始

---

## 常见问题

### Q: API 调用报错 `AuthenticationError`

检查环境变量是否正确设置：
```bash
echo $ANTHROPIC_API_KEY   # Linux/Mac
echo %ANTHROPIC_API_KEY%  # Windows CMD
```

### Q: PDF 解析结果质量差

PyMuPDF 对扫描版 PDF 效果有限。建议：
- 优先使用 LaTeX 源文件（`.tex`），解析效果最好
- 如果只有 PDF，尝试从 arXiv 下载 LaTeX 源码

### Q: 输出笔记太短 / 内容不够

尝试：
- 增加迭代轮数：`--max-rounds 5`
- 调大 token 预算（编辑 `config.yaml` 中的 `token_budget`）
- 使用更强的模型做提取：`--model-extract anthropic/claude-opus-4-6`

### Q: Token 消耗太高

尝试：
- 减少迭代轮数：`--max-rounds 1`
- 全部使用便宜模型（编辑 `config.yaml`，所有阶段都用 Haiku）
- 确保 `two_pass_reading` 和 `preprocess_compression` 为 `true`

### Q: 如何使用第三方 / 自部署模型？

在 `config.yaml` 的 `providers:` 区块中添加你的服务商，然后在 `models:` 中引用：

```yaml
providers:
  my_service:
    base_url: "https://your-service.com/v1"
    api_key_env: MY_SERVICE_API_KEY

models:
  extract: "my_service/your-model-name"
  critique: "my_service/your-model-name"
  synthesize: "my_service/your-model-name"
```

只要你的服务兼容 OpenAI 接口（大多数都兼容），就可以直接用。

### Q: 如何添加新的数学领域？

在 `domains/` 目录下新建 `your_domain.yaml`，参考已有文件的格式填写 `context_hints`、`common_techniques`、`critical_assumptions`、`standard_notation` 四个字段。然后用 `--domain your_domain` 即可。

### Q: 研讨模式下回答质量不好

研讨模式的设计是"指路"而非"复述"。如果你需要更详细的解答：
- 用 `expand` 指令展开特定证明
- 调大 `token_budget.interactive.output_max`（默认 500，可以改到 1000-2000）
- 用更强的模型：在 `config.yaml` 中设置 `models.interactive`

### Q: 如何用 `--sections` 或 `--pages` 过滤？

过滤参数会在启动分析前展示一个确认表格，列出所有匹配的 Section：

```bash
# 按 Section 标题关键词过滤（模糊匹配，不区分大小写）
python main.py paper.pdf --sections "Proof,Theorem"

# 按 PDF 页码过滤
python main.py paper.pdf --pages 5-12

# 同时用两种条件（取交集）
python main.py paper.pdf --sections "Main" --pages 1-20
```

确认对话出现后，按 **Y** 继续或 **N** 取消。

### Q: 研究问题质量不好

研究问题生成使用的是 `models.questions` 中配置的模型。默认是 `deepseek/deepseek-reasoner`，但如果你需要更高质量的问题，建议改用：

```yaml
research_questions:
  model: "anthropic/claude-opus-4-6"  # 或 openai/gpt-5.4
```

也可以用命令行覆盖（虽然目前没有专门的 CLI 参数，可以直接编辑 `config.yaml` 的 `research_questions.model`）。

### Q: `--sections` 没有匹配到任何 Section

检查：
1. 关键词是否正确（用 `python main.py --list-papers` 再看一遍原文标题）
2. 是否用了完全相反的大小写（虽然程序是大小写不敏感的，但值得确认）
3. 如果原文 Section 标题很特殊，试试换个更简短的关键词

可以用 `python main.py paper.pdf -s ""` （空值）来看所有 Section 及其页码，帮助调试。
