#!/usr/bin/env python3
"""
Memory-aware model management for resource-constrained environments
Prevents OOM errors by monitoring memory and selecting appropriate models
"""

import psutil
import yaml
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import os
from loguru import logger
from .config_loader import load_model_config


@dataclass
class ModelInfo:
    """Model information including memory requirements"""
    name: str
    memory_gb: float
    priority: int
    use_for: List[str]
    

class MemoryManager:
    """Manages model selection based on available memory"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "models.yaml"
        
        self.config = self._load_config(config_path)
        self.model_registry = self._build_registry()
        self.current_models = set()  # Track loaded models
        
    def _load_config(self, config_path: Path) -> Dict:
        """Load model configuration with environment variable overrides"""
        try:
            # Use config_loader to get config with env var overrides
            config = load_model_config(str(config_path))
            return config
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}, using defaults")
            return self._default_config()
    
    def _default_config(self) -> Dict:
        """Default configuration for common models"""
        return {
            'memory_settings': {
                'system_reserved': 2.0,
                'max_memory_percent': 85,
                'unload_threshold': 3.0,
                'aggressive_gc': True,
                'cache_size': 3
            },
            'task_chains': {
                'generate': {
                    'preferred': ['qwen2.5-coder:14b', 'deepseek-coder:latest'],
                    'fallback': ['qwen2.5-coder:7b', 'qwen2.5:1.5b', 'tinyllama']
                },
                'debug': {
                    'preferred': ['qwen2.5-coder:14b', 'qwen2.5-coder:7b'],
                    'fallback': ['qwen2.5:1.5b', 'tinyllama']
                },
                'explain': {
                    'preferred': ['qwen2.5:3b'],
                    'fallback': ['qwen2.5:1.5b', 'tinyllama']
                }
            }
        }
    
    def _build_registry(self) -> Dict[str, ModelInfo]:
        """Build model registry from config"""
        registry = {}
        
        # Hardcoded estimates if not in config
        default_sizes = {
            'tinyllama': 1.5,
            'qwen2.5:0.5b': 1.0,
            'qwen2.5:1.5b': 2.5,
            'qwen2.5:3b': 5.0,
            'qwen2.5-coder:7b': 6.5,
            'qwen2.5-coder:14b': 13.0,
            'qwen2.5:14b': 12.0,
            'deepseek-coder:latest': 14.0,
            'deepseek-coder:6.7b': 7.0,
            'codellama:7b': 7.5,
            'codellama:13b': 14.5,
            'phi': 2.7,
            'gemma:2b': 3.0,
            'codegemma:2b': 3.2
        }
        
        # Add models from config if available
        if 'models' in self.config:
            for category in self.config['models'].values():
                for model_data in category:
                    info = ModelInfo(
                        name=model_data['name'],
                        memory_gb=model_data.get('memory_gb', default_sizes.get(model_data['name'], 8.0)),
                        priority=model_data.get('priority', 99),
                        use_for=model_data.get('use_for', ['general'])
                    )
                    registry[info.name] = info
        
        # Add defaults for any missing models
        for model_name, size in default_sizes.items():
            if model_name not in registry:
                registry[model_name] = ModelInfo(
                    name=model_name,
                    memory_gb=size,
                    priority=99,
                    use_for=['general']
                )
        
        return registry
    
    def get_available_memory(self) -> Tuple[float, float]:
        """Get available system memory in GB"""
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        available_gb = mem.available / (1024**3)
        
        # Account for reserved memory
        reserved = self.config.get('memory_settings', {}).get('system_reserved', 2.0)
        usable_gb = max(0, available_gb - reserved)
        
        return usable_gb, total_gb
    
    def can_load_model(self, model_name: str) -> bool:
        """Check if model can be loaded without OOM"""
        available_gb, total_gb = self.get_available_memory()
        
        # Get model size
        model_info = self.registry.get(model_name)
        if not model_info:
            # Unknown model, estimate conservatively
            logger.warning(f"Unknown model {model_name}, assuming 8GB requirement")
            required_gb = 8.0
        else:
            required_gb = model_info.memory_gb
        
        # Check if we have enough memory
        max_percent = self.config.get('memory_settings', {}).get('max_memory_percent', 85)
        max_usable = (total_gb * max_percent / 100)
        
        # Account for currently loaded models
        current_usage = sum(
            self.registry.get(m, ModelInfo(m, 8.0, 99, [])).memory_gb 
            for m in self.current_models
        )
        
        total_after_load = current_usage + required_gb
        
        can_load = (available_gb >= required_gb and total_after_load <= max_usable)
        
        if not can_load:
            logger.warning(f"Cannot load {model_name}: needs {required_gb:.1f}GB, "
                          f"available {available_gb:.1f}GB, "
                          f"current models using {current_usage:.1f}GB")
        
        return can_load
    
    def select_model_for_task(self, task: str, available_models: List[str] = None) -> Optional[str]:
        """Select best model for task given memory constraints"""
        available_gb, total_gb = self.get_available_memory()
        
        logger.info(f"Selecting model for '{task}' with {available_gb:.1f}GB available")
        
        # Get task chain if available
        task_config = self.config.get('task_chains', {}).get(task, {})
        preferred = task_config.get('preferred', [])
        fallback = task_config.get('fallback', [])
        
        # Build candidate list
        candidates = preferred + fallback
        
        # If no task chain, use available models
        if not candidates and available_models:
            candidates = available_models
        elif not candidates:
            # Use all known models sorted by priority
            candidates = sorted(
                self.registry.keys(),
                key=lambda m: (self.registry[m].priority, self.registry[m].memory_gb)
            )
        
        # Find best model that fits in memory
        for model_name in candidates:
            if available_models and model_name not in available_models:
                continue  # Model not available on system
                
            if self.can_load_model(model_name):
                logger.success(f"Selected {model_name} for {task}")
                return model_name
        
        # If nothing fits, try smallest model
        smallest = min(
            candidates,
            key=lambda m: self.registry.get(m, ModelInfo(m, 99, 99, [])).memory_gb
        )
        
        logger.warning(f"No model fits in memory, attempting {smallest} anyway")
        return smallest
    
    def get_fallback_chain(self, failed_model: str, task: str = None) -> List[str]:
        """Get fallback models after one fails"""
        # Detect if it was OOM
        available_gb, _ = self.get_available_memory()
        model_info = self.registry.get(failed_model)
        
        if model_info and model_info.memory_gb > available_gb * 1.5:
            # Likely OOM, suggest smaller models
            logger.info(f"Model {failed_model} likely failed due to OOM")
            
            # Get models that would fit
            fallbacks = []
            for model_name, info in self.registry.items():
                if info.memory_gb <= available_gb * 0.8:  # 80% of available
                    fallbacks.append((model_name, info.memory_gb, info.priority))
            
            # Sort by priority then size
            fallbacks.sort(key=lambda x: (x[2], -x[1]))
            return [f[0] for f in fallbacks[:5]]  # Top 5 options
        
        # Otherwise use task chain
        if task:
            task_config = self.config.get('task_chains', {}).get(task, {})
            return task_config.get('fallback', ['tinyllama', 'qwen2.5:1.5b'])
        
        # Generic fallback
        return ['tinyllama', 'qwen2.5:1.5b', 'qwen2.5:0.5b']
    
    def mark_model_loaded(self, model_name: str):
        """Mark model as loaded"""
        self.current_models.add(model_name)
        logger.debug(f"Model {model_name} marked as loaded")
    
    def mark_model_unloaded(self, model_name: str):
        """Mark model as unloaded"""
        self.current_models.discard(model_name)
        logger.debug(f"Model {model_name} marked as unloaded")
    
    def suggest_models_to_unload(self) -> List[str]:
        """Suggest models to unload to free memory"""
        available_gb, _ = self.get_available_memory()
        threshold = self.config.get('memory_settings', {}).get('unload_threshold', 3.0)
        
        if available_gb < threshold:
            # Need to free memory
            models_by_size = sorted(
                self.current_models,
                key=lambda m: self.registry.get(m, ModelInfo(m, 8.0, 99, [])).memory_gb,
                reverse=True
            )
            
            # Suggest unloading largest models first
            to_unload = []
            freed = 0
            for model in models_by_size:
                to_unload.append(model)
                freed += self.registry.get(model, ModelInfo(model, 8.0, 99, [])).memory_gb
                if available_gb + freed >= threshold:
                    break
            
            logger.warning(f"Suggest unloading {to_unload} to free {freed:.1f}GB")
            return to_unload
        
        return []
    
    def detect_oom_error(self, error_message: str) -> bool:
        """Detect if error is OOM related"""
        oom_indicators = [
            'killed',
            'terminated',
            'out of memory',
            'oom',
            'memory',
            'cannot allocate',
            'resource exhausted',
            'signal: killed'
        ]
        
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in oom_indicators)


# Singleton instance
_memory_manager = None

def get_memory_manager() -> MemoryManager:
    """Get or create the memory manager singleton"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


# ==============================================================================
# Ollama Model Lifecycle Manager
# ==============================================================================

import asyncio
import httpx
from typing import Dict, List, Optional
from datetime import datetime


class OllamaModelLifecycleManager:
    """
    Manages Ollama model lifecycle to prevent OOM crashes

    Uses Ollama's keep_alive parameter and /api/ps endpoint to:
    - Unload large models immediately after use
    - Free memory before loading new large models
    - Prevent OOM crashes from too many loaded models
    """

    # Model size estimates (GB)
    MODEL_SIZES = {
        "qwen2.5-coder:14b": 9.0,
        "qwen2.5-coder:7b": 5.0,
        "qwen2.5-coder:3b": 2.0,
        "qwen2.5-coder:1.5b": 1.0,
        "deepseek-coder-v2:latest": 9.0,
        "deepseek-coder-v2:16b": 9.0,
        "deepseek-coder:33b": 19.0,
        "deepseek-coder:6.7b": 4.0,
        "codestral:latest": 13.0,
        "codellama:13b": 8.0,
        "codellama:7b": 4.0,
        "stable-code:3b": 2.0,
        "codegemma:7b": 4.0,
        "llama3.1:70b": 43.0,
        "qwen3:14b": 9.0,
        "qwen3:8b": 5.0,
        "qwen3:4b": 2.5,
        "qwen3:1.7b": 1.0,
        "mistral:latest": 4.5,
        "llama3.2:3b": 2.0,
    }

    LARGE_MODEL_THRESHOLD_GB = 8.0  # Models > 8GB trigger aggressive management

    def __init__(self):
        self.loaded_cache: Dict[str, List[str]] = {}  # node_url -> [models]
        self.cache_time: Dict[str, datetime] = {}

    def estimate_size(self, model_name: str) -> float:
        """Estimate model size in GB"""
        if model_name in self.MODEL_SIZES:
            return self.MODEL_SIZES[model_name]

        # Infer from name
        name_lower = model_name.lower()
        if "70b" in name_lower:
            return 43.0
        elif "33b" in name_lower:
            return 19.0
        elif "14b" in name_lower:
            return 9.0
        elif "13b" in name_lower:
            return 8.0
        elif "7b" in name_lower or "8b" in name_lower:
            return 5.0
        elif "3b" in name_lower or "4b" in name_lower:
            return 2.0
        elif "1.5b" in name_lower or "1.7b" in name_lower:
            return 1.0
        return 5.0  # Conservative default

    async def get_loaded_models(self, node_url: str, force: bool = False) -> List[str]:
        """Get currently loaded models from Ollama /api/ps"""
        # Cache for 10 seconds
        if not force and node_url in self.cache_time:
            age = (datetime.now() - self.cache_time[node_url]).total_seconds()
            if age < 10:
                return self.loaded_cache.get(node_url, [])

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{node_url}/api/ps")
                resp.raise_for_status()
                data = resp.json()

                loaded = []
                if "models" in data:
                    for m in data["models"]:
                        if "name" in m:
                            loaded.append(m["name"])

                self.loaded_cache[node_url] = loaded
                self.cache_time[node_url] = datetime.now()
                return loaded

        except Exception as e:
            logger.debug(f"Failed to get loaded models from {node_url}: {e}")
            return self.loaded_cache.get(node_url, [])

    async def unload_model(self, node_url: str, model: str) -> bool:
        """Unload model by sending generate with keep_alive=0"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{node_url}/api/generate",
                    json={"model": model, "prompt": "", "keep_alive": 0},
                    timeout=10.0
                )
                logger.info(f"🗑️  Unloaded {model} from {node_url}")

                # Update cache
                if node_url in self.loaded_cache:
                    if model in self.loaded_cache[node_url]:
                        self.loaded_cache[node_url].remove(model)
                return True

        except Exception as e:
            logger.warning(f"Failed to unload {model}: {e}")
            return False

    async def free_memory(self, node_url: str, model_to_load: str) -> int:
        """
        Free memory before loading a large model

        Returns number of models unloaded
        """
        size = self.estimate_size(model_to_load)

        # Only manage memory for large models
        if size < self.LARGE_MODEL_THRESHOLD_GB:
            return 0

        logger.info(f"🧹 Freeing memory on {node_url} for {model_to_load} ({size:.1f}GB)")

        loaded = await self.get_loaded_models(node_url, force=True)
        if not loaded:
            return 0

        # Sort by size (unload largest first)
        by_size = sorted(loaded, key=self.estimate_size, reverse=True)

        unloaded_count = 0
        freed_gb = 0.0

        for model in by_size:
            if model == model_to_load:
                continue

            if await self.unload_model(node_url, model):
                freed_gb += self.estimate_size(model)
                unloaded_count += 1

                # Unload enough to make room
                if freed_gb >= size:
                    logger.success(f"✨ Freed {freed_gb:.1f}GB ({unloaded_count} models)")
                    break

        return unloaded_count

    def get_keep_alive(self, model_name: str) -> int:
        """
        Get recommended keep_alive for model

        Returns:
            0 = unload immediately
            300 = keep 5 minutes
            900 = keep 15 minutes
        """
        size = self.estimate_size(model_name)

        # Large models: unload immediately to free memory
        if size >= self.LARGE_MODEL_THRESHOLD_GB:
            return 0
        # Medium models: keep for 5 minutes
        elif size >= 4.0:
            return 300
        # Small models: keep for 15 minutes
        else:
            return 900


# Singleton
_ollama_lifecycle_manager = None

def get_ollama_lifecycle_manager() -> OllamaModelLifecycleManager:
    """Get or create Ollama lifecycle manager singleton"""
    global _ollama_lifecycle_manager
    if _ollama_lifecycle_manager is None:
        _ollama_lifecycle_manager = OllamaModelLifecycleManager()
    return _ollama_lifecycle_manager