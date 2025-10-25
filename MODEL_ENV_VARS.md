# Model Configuration with Environment Variables

## Overview

Hydra now supports **environment variable overrides** for model configuration. This allows you to change which models are used without editing the `config/models.yaml` file.

Environment variables take precedence over YAML configuration, making it easy to:
- Test different models quickly
- Configure different environments (dev, staging, production)
- Override models for specific deployments
- Customize model selection without code changes

## Quick Start

### 1. View Available Environment Variables

Check `.env` or `.env.example` for all available model configuration options:

```bash
cat .env | grep HYDRA_
```

### 2. Override Models

Simply set environment variables in your `.env` file or export them:

```bash
# In .env file
HYDRA_LIGHT_MODEL=llama3.2:3b
HYDRA_HEAVY_MODEL=llama3.1:70b
HYDRA_CODE_MODELS=qwen2.5-coder:32b,deepseek-coder:33b
HYDRA_DEFAULT_TEMPERATURE=0.9

# Or export in shell
export HYDRA_LIGHT_MODEL=llama3.2:3b
export HYDRA_HEAVY_MODEL=llama3.1:70b
```

### 3. Restart Hydra

The new configuration will be loaded automatically:

```bash
streamlit run app.py
# or
python main.py api
```

## Available Environment Variables

### Orchestrator Models

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `HYDRA_LIGHT_MODEL` | Quick analysis model | `qwen3:1.7b` | `llama3.2:3b` |
| `HYDRA_HEAVY_MODEL` | Complex task model | `qwen3:14b` | `llama3.1:70b` |

### Code Synthesis Models

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `HYDRA_CODE_MODELS` | Primary code models (comma-separated) | `qwen2.5-coder:14b,deepseek-coder:latest,...` | `qwen2.5-coder:32b,codellama:34b` |
| `HYDRA_MATH_MODEL` | Specialized math model | `wizard-math:latest` | `deepseek-math:latest` |
| `HYDRA_REASONING_MODEL` | Specialized reasoning model | `qwq:32b` | `qwen2.5:32b` |

### General Models

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `HYDRA_GENERAL_MODELS` | General-purpose models (comma-separated) | `llama3.1:latest,tulu3:latest,...` | `llama3.2:3b,gemma2:9b` |
| `HYDRA_EMBEDDING_MODEL` | Embedding model for vectorization | `mxbai-embed-large` | `nomic-embed-text` |
| `HYDRA_JSON_MODEL` | Model for JSON function calling | `llama3.2:latest` | `llama3.1:8b` |

### Model Parameters

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `HYDRA_DEFAULT_TEMPERATURE` | Generation temperature (0.0-2.0) | `0.7` | `0.9` |
| `HYDRA_DEFAULT_TOP_P` | Nucleus sampling threshold | `0.95` | `0.9` |
| `HYDRA_DEFAULT_REPEAT_PENALTY` | Repetition penalty | `1.1` | `1.2` |
| `HYDRA_DEFAULT_MAX_TOKENS` | Maximum tokens per generation | `8192` | `4096` |

## Examples

### Example 1: Use Smaller Models for Development

```bash
# .env
HYDRA_LIGHT_MODEL=qwen3:1.7b
HYDRA_HEAVY_MODEL=qwen3:14b
HYDRA_CODE_MODELS=qwen2.5-coder:7b,codellama:7b
```

This configuration uses smaller models that load faster and use less VRAM.

### Example 2: Use Larger Models for Production

```bash
# .env
HYDRA_LIGHT_MODEL=qwen3:14b
HYDRA_HEAVY_MODEL=qwq:32b
HYDRA_CODE_MODELS=qwen2.5-coder:32b,deepseek-coder:33b,codellama:34b
HYDRA_REASONING_MODEL=qwq:32b
```

This configuration prioritizes larger, more capable models for production use.

### Example 3: Specialized Configuration for Math Tasks

```bash
# .env
HYDRA_MATH_MODEL=deepseek-math:latest
HYDRA_CODE_MODELS=qwen2.5-coder:32b,wizard-coder:latest
HYDRA_DEFAULT_TEMPERATURE=0.3  # Lower temperature for precise math
```

Optimized for mathematical and analytical tasks.

### Example 4: Testing New Models

```bash
# Temporary override - don't edit .env
export HYDRA_LIGHT_MODEL=llama3.2:1b
export HYDRA_HEAVY_MODEL=mistral-nemo:latest
export HYDRA_CODE_MODELS=codestral:latest,qwen2.5-coder:latest

streamlit run app.py
```

Test new models without modifying configuration files.

## How It Works

### Loading Priority

1. **Environment Variables** (highest priority)
2. **YAML Configuration** (`config/models.yaml`)
3. **Hardcoded Defaults** (fallback if config missing)

### Example Flow

```python
# Load config with overrides
from core.config_loader import load_model_config

config = load_model_config()

# Environment variables automatically override YAML values
# HYDRA_LIGHT_MODEL=llama3.2:3b → config['orchestrators']['light']['model'] = 'llama3.2:3b'
```

### Configuration Files

1. **`/home/joker/hydra/core/config_loader.py`**
   - Loads YAML configuration
   - Applies environment variable overrides
   - Provides helper functions (`get_model_param`, `get_model_list`)

2. **`/home/joker/hydra/core/orchestrator.py`**
   - Uses `load_model_config()` to get merged configuration
   - Automatically respects environment variable overrides

3. **`/home/joker/hydra/core/memory_manager.py`**
   - Also uses `load_model_config()` for consistent configuration

## Testing Configuration

Run the test script to verify environment variable overrides:

```bash
python test_config_env_vars.py
```

Expected output:
```
======================================================================
Testing Environment Variable Configuration Overrides
======================================================================

1. Testing default YAML configuration...
   Light model: qwen3:1.7b
   Heavy model: qwen3:14b
   Code models: 11 models
   ...

✅ ALL TESTS PASSED - Environment variable overrides working!
======================================================================
```

## Programmatic Access

### Using Helper Functions

```python
from core.config_loader import get_model_param, get_model_list, load_model_config

# Get a specific parameter
temperature = get_model_param('temperature', default=0.7)

# Get a model list
code_models = get_model_list('code')

# Load full configuration
config = load_model_config()
light_model = config['orchestrators']['light']['model']
```

### In Your Code

```python
# ModelOrchestrator automatically uses environment variable overrides
from core.orchestrator import ModelOrchestrator

orchestrator = ModelOrchestrator(load_balancer)
# orchestrator.light_model and orchestrator.heavy_model
# will respect HYDRA_LIGHT_MODEL and HYDRA_HEAVY_MODEL
```

## Troubleshooting

### Override Not Working

1. **Check environment variable is set:**
   ```bash
   echo $HYDRA_LIGHT_MODEL
   ```

2. **Verify .env file is loaded:**
   - Hydra loads `.env` automatically via `python-dotenv`
   - Check that `load_dotenv()` is called in `main.py`

3. **Check for typos:**
   - Variable names must match exactly (case-sensitive)
   - Use `HYDRA_` prefix, not `OLLAMA_` or other

4. **Restart application:**
   - Environment variables are loaded at startup
   - Kill and restart Streamlit/FastAPI

### See What Overrides Are Active

Look for log messages during startup:

```
INFO - Applied 4 environment variable overrides:
INFO -   • light model → llama3.2:3b
INFO -   • heavy model → llama3.1:70b
INFO -   • code models → 2 models
INFO -   • temperature → 0.9
```

### Invalid Values

If you provide an invalid value, you'll see a warning:

```
WARNING - Invalid HYDRA_DEFAULT_TEMPERATURE: abc
```

The system will fall back to the YAML configuration or default value.

## Best Practices

1. **Use `.env` for persistent configuration**
   - Edit `.env` for changes you want to keep
   - Don't commit `.env` to version control (use `.env.example` as template)

2. **Use `export` for temporary testing**
   - Quick testing without modifying files
   - Variables only exist in current shell session

3. **Document your overrides**
   - Add comments in `.env` explaining why you changed defaults
   - Share configuration via `.env.example`

4. **Test before deploying**
   - Run `test_config_env_vars.py` to verify setup
   - Check logs for applied overrides during startup

5. **Use YAML for defaults, env vars for customization**
   - Keep sensible defaults in `config/models.yaml`
   - Override only what you need to change

## Migration Guide

### Before (YAML only)

```python
# Had to edit config/models.yaml to change models
# orchestrators:
#   light:
#     model: qwen3:1.7b  # Edit this line
```

### After (Environment Variables)

```bash
# Just set environment variable
HYDRA_LIGHT_MODEL=llama3.2:3b
```

No code or YAML file changes needed!

## Summary

✅ **Environment variables override YAML configuration**
✅ **All model settings configurable via env vars**
✅ **No code changes required to switch models**
✅ **Easy testing and deployment configuration**
✅ **Backward compatible with YAML-only config**

For more details, see:
- `/home/joker/hydra/.env` - Current configuration
- `/home/joker/hydra/.env.example` - Example with all available variables
- `/home/joker/hydra/config/models.yaml` - Base YAML configuration
- `/home/joker/hydra/core/config_loader.py` - Implementation
