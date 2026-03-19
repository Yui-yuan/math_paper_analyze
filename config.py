"""配置加载与校验"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


BASE_DIR = Path(__file__).parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"


@dataclass
class ProviderConfig:
    """单个 API 服务商的配置"""
    base_url: str = ""
    api_key_env: str = ""
    compatible_mode: bool = True  # True=走 OpenAI 兼容接口, False=走原生 SDK


@dataclass
class ModelConfig:
    preprocess: str = "deepseek/deepseek-chat"
    extract: str = "deepseek/deepseek-chat"
    critique: str = "deepseek/deepseek-reasoner"
    synthesize: str = "deepseek/deepseek-chat"
    interactive: str = "deepseek/deepseek-chat"


@dataclass
class PipelineConfig:
    max_rounds: int = 3
    convergence_threshold: int = 2


@dataclass
class OptimizationConfig:
    two_pass_reading: bool = True
    preprocess_compression: bool = True
    cache_intermediates: bool = True


@dataclass
class TokenBudgetStage:
    input_max: int = 4000
    output_max: int = 2000


@dataclass
class TokenBudgetConfig:
    preprocess: TokenBudgetStage = field(default_factory=lambda: TokenBudgetStage(input_max=8000, output_max=8000))
    extract: TokenBudgetStage = field(default_factory=lambda: TokenBudgetStage(input_max=6000, output_max=2000))
    critique: TokenBudgetStage = field(default_factory=lambda: TokenBudgetStage(input_max=3000, output_max=1000))
    synthesize: TokenBudgetStage = field(default_factory=lambda: TokenBudgetStage(input_max=4000, output_max=2500))
    interactive: TokenBudgetStage = field(default_factory=lambda: TokenBudgetStage(input_max=3000, output_max=500))


@dataclass
class OutputConfig:
    format: list = field(default_factory=lambda: ["markdown"])
    language: str = "zh"
    layers: list = field(default_factory=lambda: [1, 2])
    layer3_targets: str = "auto"
    max_layer3_proofs: int = 2
    auto_compile_pdf: bool = False
    output_dir: str = "./output"


@dataclass
class InteractiveConfig:
    enabled: bool = True
    context_window: int = 5
    history_compression: bool = True
    auto_save: bool = True


@dataclass
class AppConfig:
    models: ModelConfig = field(default_factory=ModelConfig)
    providers: dict = field(default_factory=dict)  # name -> ProviderConfig
    domain: Optional[str] = None
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    token_budget: TokenBudgetConfig = field(default_factory=TokenBudgetConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    interactive: InteractiveConfig = field(default_factory=InteractiveConfig)
    papers_dir: str = "./papers"
    cache_dir: str = "./cache"


def _dict_to_dataclass(cls, data: dict):
    """递归地将 dict 转为 dataclass"""
    if data is None:
        return cls()
    fieldtypes = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for k, v in data.items():
        if k in fieldtypes and isinstance(v, dict):
            # 找到对应的 dataclass 类型
            ft = cls.__dataclass_fields__[k].type
            # 处理 Optional 类型
            if hasattr(ft, '__origin__'):
                continue
            # 尝试获取实际类
            actual_type = globals().get(ft) if isinstance(ft, str) else ft
            if actual_type and hasattr(actual_type, '__dataclass_fields__'):
                kwargs[k] = _dict_to_dataclass(actual_type, v)
            else:
                kwargs[k] = v
        else:
            kwargs[k] = v
    return cls(**kwargs)


def load_config(config_path: Optional[str] = None, overrides: Optional[dict] = None) -> AppConfig:
    """加载配置文件，支持覆盖"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    # 应用命令行覆盖
    if overrides:
        for key, value in overrides.items():
            if '.' in key:
                parts = key.split('.')
                d = raw
                for p in parts[:-1]:
                    d = d.setdefault(p, {})
                d[parts[-1]] = value
            else:
                raw[key] = value

    # 构建配置对象
    config = AppConfig()

    if 'models' in raw and raw['models']:
        config.models = ModelConfig(**{k: v for k, v in raw['models'].items() if k in ModelConfig.__dataclass_fields__})

    if 'providers' in raw and raw['providers']:
        for name, prov_data in raw['providers'].items():
            if isinstance(prov_data, dict):
                config.providers[name] = ProviderConfig(
                    base_url=prov_data.get('base_url', ''),
                    api_key_env=prov_data.get('api_key_env', ''),
                    compatible_mode=prov_data.get('compatible_mode', True),
                )

    if 'domain' in raw:
        config.domain = raw['domain']

    if 'pipeline' in raw and raw['pipeline']:
        config.pipeline = PipelineConfig(**{k: v for k, v in raw['pipeline'].items() if k in PipelineConfig.__dataclass_fields__})

    if 'optimization' in raw and raw['optimization']:
        config.optimization = OptimizationConfig(**{k: v for k, v in raw['optimization'].items() if k in OptimizationConfig.__dataclass_fields__})

    if 'token_budget' in raw and raw['token_budget']:
        tb = raw['token_budget']
        config.token_budget = TokenBudgetConfig(
            preprocess=TokenBudgetStage(**tb.get('preprocess', {})) if 'preprocess' in tb else TokenBudgetStage(input_max=8000, output_max=8000),
            extract=TokenBudgetStage(**tb.get('extract', {})) if 'extract' in tb else TokenBudgetStage(input_max=6000, output_max=2000),
            critique=TokenBudgetStage(**tb.get('critique', {})) if 'critique' in tb else TokenBudgetStage(input_max=3000, output_max=1000),
            synthesize=TokenBudgetStage(**tb.get('synthesize', {})) if 'synthesize' in tb else TokenBudgetStage(input_max=4000, output_max=2500),
            interactive=TokenBudgetStage(**tb.get('interactive', {})) if 'interactive' in tb else TokenBudgetStage(input_max=3000, output_max=500),
        )

    if 'output' in raw and raw['output']:
        config.output = OutputConfig(**{k: v for k, v in raw['output'].items() if k in OutputConfig.__dataclass_fields__})

    if 'interactive' in raw and raw['interactive']:
        config.interactive = InteractiveConfig(**{k: v for k, v in raw['interactive'].items() if k in InteractiveConfig.__dataclass_fields__})

    if 'papers_dir' in raw:
        config.papers_dir = raw['papers_dir']
    if 'cache_dir' in raw:
        config.cache_dir = raw['cache_dir']

    return config


def resolve_provider(model_name: str, config: AppConfig) -> tuple:
    """
    从 "provider/model" 格式解析出 provider 配置和模型名。

    Returns:
        (ProviderConfig, model_name_only)
    """
    if '/' in model_name:
        provider_name, model_only = model_name.split('/', 1)
    else:
        # 没有 provider 前缀，默认 openai
        provider_name = "openai"
        model_only = model_name

    provider = config.providers.get(provider_name)
    if not provider:
        # 未配置的 provider，构造一个默认的
        provider = ProviderConfig(
            base_url="",
            api_key_env=f"{provider_name.upper()}_API_KEY",
            compatible_mode=True,
        )

    return provider, model_only


def get_domain_path(domain_name: str) -> Path:
    """获取领域配置文件路径"""
    return BASE_DIR / "domains" / f"{domain_name}.yaml"


def load_domain(domain_name: str) -> Optional[dict]:
    """加载领域增强配置"""
    path = get_domain_path(domain_name)
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def list_domains() -> list:
    """列出所有可用的领域"""
    domains_dir = BASE_DIR / "domains"
    if not domains_dir.exists():
        return []
    return [p.stem for p in domains_dir.glob("*.yaml")]
