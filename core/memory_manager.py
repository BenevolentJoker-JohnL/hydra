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
        """Load model configuration"""
        if not config_path.exists():
            logger.warning(f"Config not found at {config_path}, using defaults")
            return self._default_config()
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
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