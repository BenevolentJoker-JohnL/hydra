#!/usr/bin/env python3
"""
Test script for environment variable configuration overrides.

This script tests that environment variables correctly override YAML configuration.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config_loader import load_model_config, get_model_param, get_model_list
from loguru import logger

def test_env_var_overrides():
    """Test that environment variables override YAML config"""
    print("=" * 70)
    print("Testing Environment Variable Configuration Overrides")
    print("=" * 70)

    # Test 1: Load default config without env vars
    print("\n1. Testing default YAML configuration...")
    config = load_model_config()

    print(f"   Light model: {config['orchestrators']['light']['model']}")
    print(f"   Heavy model: {config['orchestrators']['heavy']['model']}")
    print(f"   Code models: {len(config['code_synthesis']['primary'])} models")
    print(f"   General models: {len(config['general'])} models")
    print(f"   Temperature: {config['model_params']['temperature']}")

    # Test 2: Set env vars and reload
    print("\n2. Setting environment variables...")
    os.environ['HYDRA_LIGHT_MODEL'] = 'llama3.2:3b'
    os.environ['HYDRA_HEAVY_MODEL'] = 'llama3.1:70b'
    os.environ['HYDRA_CODE_MODELS'] = 'qwen2.5-coder:32b,deepseek-coder:33b'
    os.environ['HYDRA_DEFAULT_TEMPERATURE'] = '0.9'

    print("   HYDRA_LIGHT_MODEL=llama3.2:3b")
    print("   HYDRA_HEAVY_MODEL=llama3.1:70b")
    print("   HYDRA_CODE_MODELS=qwen2.5-coder:32b,deepseek-coder:33b")
    print("   HYDRA_DEFAULT_TEMPERATURE=0.9")

    # Test 3: Reload config with env vars
    print("\n3. Reloading configuration with env var overrides...")
    config_with_overrides = load_model_config()

    print(f"   Light model: {config_with_overrides['orchestrators']['light']['model']}")
    print(f"   Heavy model: {config_with_overrides['orchestrators']['heavy']['model']}")
    print(f"   Code models: {config_with_overrides['code_synthesis']['primary']}")
    print(f"   Temperature: {config_with_overrides['model_params']['temperature']}")

    # Test 4: Verify overrides worked
    print("\n4. Verifying overrides...")
    assert config_with_overrides['orchestrators']['light']['model'] == 'llama3.2:3b', "Light model override failed"
    assert config_with_overrides['orchestrators']['heavy']['model'] == 'llama3.1:70b', "Heavy model override failed"
    assert len(config_with_overrides['code_synthesis']['primary']) == 2, "Code models override failed"
    assert 'qwen2.5-coder:32b' in config_with_overrides['code_synthesis']['primary'], "Code model list wrong"
    assert config_with_overrides['model_params']['temperature'] == 0.9, "Temperature override failed"

    print("   ✅ All overrides applied correctly!")

    # Test 5: Test helper functions
    print("\n5. Testing helper functions...")
    temp = get_model_param('temperature', default=0.7)
    print(f"   get_model_param('temperature'): {temp}")
    assert temp == 0.9, "get_model_param failed"

    code_models = get_model_list('code')
    print(f"   get_model_list('code'): {code_models}")
    assert len(code_models) == 2, "get_model_list failed"

    print("   ✅ Helper functions work correctly!")

    # Clean up env vars
    del os.environ['HYDRA_LIGHT_MODEL']
    del os.environ['HYDRA_HEAVY_MODEL']
    del os.environ['HYDRA_CODE_MODELS']
    del os.environ['HYDRA_DEFAULT_TEMPERATURE']

    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED - Environment variable overrides working!")
    print("=" * 70)


if __name__ == "__main__":
    test_env_var_overrides()
