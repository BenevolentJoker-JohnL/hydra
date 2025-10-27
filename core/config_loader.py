"""
Configuration loader with environment variable override support.

Loads base configuration from YAML and allows environment variables to override values.
Environment variables take precedence over YAML configuration.
"""

import os
import yaml
from typing import Dict, Any, List, Optional
from loguru import logger


def load_model_config(config_path: str = "config/models.yaml") -> Dict[str, Any]:
    """
    Load model configuration with environment variable overrides.

    Environment variables override YAML values:
    - HYDRA_LIGHT_MODEL: Override orchestrators.light.model
    - HYDRA_HEAVY_MODEL: Override orchestrators.heavy.model
    - HYDRA_CODE_MODELS: Override code_synthesis.primary (comma-separated)
    - HYDRA_MATH_MODEL: Override code_synthesis.specialized.math
    - HYDRA_REASONING_MODEL: Override code_synthesis.specialized.reasoning
    - HYDRA_GENERAL_MODELS: Override general models (comma-separated)
    - HYDRA_EMBEDDING_MODEL: Override embedding.model
    - HYDRA_JSON_MODEL: Override json_functions.model
    - HYDRA_DEFAULT_TEMPERATURE: Override model_params.temperature
    - HYDRA_DEFAULT_TOP_P: Override model_params.top_p
    - HYDRA_DEFAULT_REPEAT_PENALTY: Override model_params.repeat_penalty
    - HYDRA_DEFAULT_MAX_TOKENS: Override orchestrators.heavy.max_tokens

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Merged configuration dictionary with env var overrides applied
    """
    # Load base YAML configuration
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"Config file {config_path} not found, using defaults")
        config = _get_default_config()

    # Apply environment variable overrides
    overrides_applied = []

    # Orchestrator models
    if light_model := os.getenv('HYDRA_LIGHT_MODEL'):
        config.setdefault('orchestrators', {}).setdefault('light', {})['model'] = light_model
        overrides_applied.append(f"light model → {light_model}")

    if heavy_model := os.getenv('HYDRA_HEAVY_MODEL'):
        config.setdefault('orchestrators', {}).setdefault('heavy', {})['model'] = heavy_model
        overrides_applied.append(f"heavy model → {heavy_model}")

    # Max tokens
    if max_tokens := os.getenv('HYDRA_DEFAULT_MAX_TOKENS'):
        try:
            max_tokens_int = int(max_tokens)
            config.setdefault('orchestrators', {}).setdefault('light', {})['max_tokens'] = max_tokens_int
            config.setdefault('orchestrators', {}).setdefault('heavy', {})['max_tokens'] = max_tokens_int
            overrides_applied.append(f"max_tokens → {max_tokens_int}")
        except ValueError:
            logger.warning(f"Invalid HYDRA_DEFAULT_MAX_TOKENS: {max_tokens}")

    # Code synthesis models
    if code_models := os.getenv('HYDRA_CODE_MODELS'):
        models_list = [m.strip() for m in code_models.split(',') if m.strip()]
        config.setdefault('code_synthesis', {})['primary'] = models_list
        overrides_applied.append(f"code models → {len(models_list)} models")

    # Specialized models
    if math_model := os.getenv('HYDRA_MATH_MODEL'):
        config.setdefault('code_synthesis', {}).setdefault('specialized', {})['math'] = math_model
        overrides_applied.append(f"math model → {math_model}")

    if reasoning_model := os.getenv('HYDRA_REASONING_MODEL'):
        config.setdefault('code_synthesis', {}).setdefault('specialized', {})['reasoning'] = reasoning_model
        overrides_applied.append(f"reasoning model → {reasoning_model}")

    # General models
    if general_models := os.getenv('HYDRA_GENERAL_MODELS'):
        models_list = [m.strip() for m in general_models.split(',') if m.strip()]
        config['general'] = models_list
        overrides_applied.append(f"general models → {len(models_list)} models")

    # Embedding model
    if embedding_model := os.getenv('HYDRA_EMBEDDING_MODEL'):
        config.setdefault('embedding', {})['model'] = embedding_model
        overrides_applied.append(f"embedding model → {embedding_model}")

    # JSON model
    if json_model := os.getenv('HYDRA_JSON_MODEL'):
        config.setdefault('json_functions', {})['model'] = json_model
        overrides_applied.append(f"JSON model → {json_model}")

    # Model parameters
    if temperature := os.getenv('HYDRA_DEFAULT_TEMPERATURE'):
        try:
            temp_float = float(temperature)
            config.setdefault('model_params', {})['temperature'] = temp_float
            overrides_applied.append(f"temperature → {temp_float}")
        except ValueError:
            logger.warning(f"Invalid HYDRA_DEFAULT_TEMPERATURE: {temperature}")

    if top_p := os.getenv('HYDRA_DEFAULT_TOP_P'):
        try:
            top_p_float = float(top_p)
            config.setdefault('model_params', {})['top_p'] = top_p_float
            overrides_applied.append(f"top_p → {top_p_float}")
        except ValueError:
            logger.warning(f"Invalid HYDRA_DEFAULT_TOP_P: {top_p}")

    if repeat_penalty := os.getenv('HYDRA_DEFAULT_REPEAT_PENALTY'):
        try:
            repeat_float = float(repeat_penalty)
            config.setdefault('model_params', {})['repeat_penalty'] = repeat_float
            overrides_applied.append(f"repeat_penalty → {repeat_float}")
        except ValueError:
            logger.warning(f"Invalid HYDRA_DEFAULT_REPEAT_PENALTY: {repeat_penalty}")

    # Log overrides
    if overrides_applied:
        logger.info(f"Applied {len(overrides_applied)} environment variable overrides:")
        for override in overrides_applied:
            logger.info(f"  • {override}")
    else:
        logger.debug("No environment variable overrides, using YAML configuration")

    return config


def _get_default_config() -> Dict[str, Any]:
    """
    Get default configuration when YAML file is not available.

    Returns:
        Default configuration dictionary
    """
    return {
        'orchestrators': {
            'light': {
                'model': 'qwen3:1.7b',
                'max_tokens': 4096
            },
            'heavy': {
                'model': 'qwen3:14b',
                'max_tokens': 8192
            }
        },
        'code_synthesis': {
            'primary': [
                'qwen2.5-coder:14b',
                'deepseek-coder:latest',
                'codellama:13b',
                'qwen2.5-coder:7b',
                'deepseek-coder:latest',
                'codellama:latest',
                'qwen2.5:3b',
                'qwen2.5:1.5b',
                'tinyllama',
                'stable-code:3b',
                'codegemma:2b'
            ],
            'specialized': {
                'math': 'wizard-math:latest',
                'reasoning': 'qwq:32b'
            }
        },
        'general': [
            'llama3.1:latest',
            'tulu3:latest',
            'llama3:latest'
        ],
        'embedding': {
            'model': 'mxbai-embed-large'
        },
        'json_functions': {
            'model': 'llama3.2:latest'
        },
        'model_params': {
            'temperature': 0.7,
            'top_p': 0.95,
            'repeat_penalty': 1.1
        }
    }


def get_model_param(param_name: str, default: Any = None) -> Any:
    """
    Get a specific model parameter with environment variable override.

    Args:
        param_name: Parameter name (temperature, top_p, repeat_penalty, etc.)
        default: Default value if not found

    Returns:
        Parameter value from env var or config or default
    """
    env_var_map = {
        'temperature': 'HYDRA_DEFAULT_TEMPERATURE',
        'top_p': 'HYDRA_DEFAULT_TOP_P',
        'repeat_penalty': 'HYDRA_DEFAULT_REPEAT_PENALTY',
        'max_tokens': 'HYDRA_DEFAULT_MAX_TOKENS'
    }

    # Check environment variable first
    if env_var := env_var_map.get(param_name):
        if value := os.getenv(env_var):
            try:
                if param_name == 'max_tokens':
                    return int(value)
                else:
                    return float(value)
            except ValueError:
                logger.warning(f"Invalid {env_var}: {value}")

    # Fallback to default
    return default


def get_model_list(category: str) -> List[str]:
    """
    Get a list of models for a specific category with env var override.

    Args:
        category: Category name ('code', 'general', etc.)

    Returns:
        List of model names
    """
    env_var_map = {
        'code': 'HYDRA_CODE_MODELS',
        'general': 'HYDRA_GENERAL_MODELS'
    }

    if env_var := env_var_map.get(category):
        if value := os.getenv(env_var):
            return [m.strip() for m in value.split(',') if m.strip()]

    # Load from config file
    config = load_model_config()

    if category == 'code':
        return config.get('code_synthesis', {}).get('primary', [])
    elif category == 'general':
        return config.get('general', [])

    return []
