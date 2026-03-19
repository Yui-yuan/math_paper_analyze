# Math Paper Reader

AI 辅助数学论文阅读工具。通过三阶段 Pipeline（提取 → 批判 → 修正）自动生成高质量的论文研读笔记，并支持交互式追问。

---

## 目录

- [安装](#安装)
- [论文管理](#论文管理)
- [快速开始](#快速开始)
- [完整用法](#完整用法)
- [配置文件](#配置文件)
- [数学领域支持](#数学领域支持)
- [输出格式说明](#输出格式说明)
- [研讨模式](#研讨模式)
- [Token 优化机制](#token-优化机制)
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
| `--no-interactive` | | 跳过研讨模式，直接输出笔记后退出 | |
| `--model-extract` | | Stage 1（提取）使用的模型 | `--model-extract openai/gpt-4o` |
| `--model-critique` | | Stage 2（批判）使用的模型 | `--model-critique anthropic/claude-opus-4-20250115` |
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
python main.py paper.pdf --model-extract openai/gpt-4o --model-critique anthropic/claude-opus-4-20250115

# 增加迭代轮数（更精细，但更费 token）
python main.py paper.pdf -r 5

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
| Moonshot 128k | `moonshot/moonshot-v1-128k` | 超长上下文 | ¥60/M tokens |
| MiniMax Text | `minimax/MiniMax-Text-01` | 便宜 | ¥1/M tokens |
| Claude Opus 4 | `anthropic/claude-opus-4-20250115` | 最强 | $15/M tokens |
| Claude Sonnet 4 | `anthropic/claude-sonnet-4-20250514` | 平衡 | $3/M tokens |
| Claude Haiku 4.5 | `anthropic/claude-haiku-4-5-20251001` | 快速 | $0.8/M tokens |
| GPT-4o | `openai/gpt-4o` | OpenAI 主力 | $2.5/M tokens |
| GPT-4o mini | `openai/gpt-4o-mini` | 便宜 | $0.15/M tokens |
| Gemini 2.5 Pro | `gemini/gemini-2.5-pro` | Google 最强，100万上下文 | $1.25/M tokens |
| Gemini 2.5 Flash | `gemini/gemini-2.5-flash` | 快速便宜 | $0.15/M tokens |
| Gemini 2.0 Flash | `gemini/gemini-2.0-flash` | 最便宜 | $0.10/M tokens |

**省钱建议**：默认配置使用 DeepSeek，全流程跑完一篇论文大约 ¥0.1-0.5。如果追求最高质量，批判阶段换成 `anthropic/claude-opus-4-20250115` 或 `openai/o3`。

#### Pipeline 配置

```yaml
pipeline:
  max_rounds: 3              # 最大迭代轮数（越多越精细，但越费 token）
  convergence_threshold: 2   # 当批判意见 ≤ 2 条时停止迭代
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

生成的笔记按三层组织：

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
| `gap <位置>` | 要求补全某处逻辑跳跃 | `gap Theorem 4.1 step 3` |
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
- 使用更强的模型做提取：`--model-extract anthropic/claude-opus-4-20250115`

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
