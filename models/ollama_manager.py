"""
⚠️ DEPRECATION NOTICE ⚠️

This module (models/ollama_manager.py) is DEPRECATED and replaced by SOLLOL integration.

SOLLOL provides superior load balancing:
- Resource-aware routing (VRAM/RAM monitoring)
- Auto-discovery of Ollama nodes
- 10x faster routing (50ms → 5ms)
- 12x faster failover (2+ min → 10-30s)
- 2x higher throughput (2k → 4k req/min)
- Intelligent model-to-node placement

Please use: core/sollol_integration.py

This file is kept for backward compatibility only.
Migration: main.py now uses SOLLOLIntegration instead of OllamaLoadBalancer.
"""

import asyncio
import random
import httpx
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime, timedelta
import ollama
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

logger.warning("⚠️  models/ollama_manager.py is DEPRECATED. Use core/sollol_integration.py instead")

class OllamaLoadBalancer:
    def __init__(self, hosts: List[str]):
        self.hosts = hosts
        self.client_pool = {host: ollama.AsyncClient(host=host) for host in hosts}
        # Initialize all hosts as healthy by default
        self.health_status = {host: True for host in hosts}
        self.request_counts = defaultdict(int)
        self.response_times = defaultdict(list)
        self.last_health_check = defaultdict(lambda: datetime.now())
        # Track initialization
        self.initialized = False
        
    async def check_health(self, host: str) -> bool:
        try:
            client = self.client_pool[host]
            await client.list()
            return True
        except Exception as e:
            # Only log if this is a new failure
            if self.health_status.get(host, True):  # Was healthy before
                logger.warning(f"Host {host} health check failed: {e}")
            return False
            
    async def initialize(self):
        """Initialize and check all hosts"""
        if not self.initialized:
            logger.info("Initializing Ollama hosts...")
            for host in self.hosts:
                is_healthy = await self.check_health(host)
                self.health_status[host] = is_healthy
                if is_healthy:
                    logger.success(f"✅ Host {host} is available")
                else:
                    logger.warning(f"⚠️ Host {host} is not available")
            self.initialized = True
            
            # Start with at least localhost if nothing else works
            if not any(self.health_status.values()):
                logger.warning("No hosts available, forcing localhost")
                if 'http://localhost:11434' in self.hosts:
                    self.health_status['http://localhost:11434'] = True
    
    async def periodic_health_check(self):
        """Periodic health check with better error tracking and recovery"""
        failure_counts = defaultdict(int)
        
        # Initialize on first run
        if not self.initialized:
            await self.initialize()
        
        while True:
            for host in self.hosts:
                # Check health less frequently - every 2 minutes instead of 30 seconds
                if datetime.now() - self.last_health_check[host] > timedelta(minutes=2):
                    is_healthy = await self.check_health(host)
                    
                    if is_healthy:
                        # Mark healthy if it wasn't before
                        if not self.health_status.get(host, False):
                            logger.info(f"✅ Host {host} recovered")
                        self.health_status[host] = True
                        failure_counts[host] = 0  # Reset on success
                    else:
                        failure_counts[host] += 1
                        if failure_counts[host] >= 3:
                            self.health_status[host] = False
                            logger.warning(f"⚠️ Host {host} marked unhealthy after {failure_counts[host]} failures")
                        else:
                            logger.debug(f"Host {host} health check failed ({failure_counts[host]}/3)")
                    
                    self.last_health_check[host] = datetime.now()
            
            # Ensure at least one host is available
            if not any(self.health_status.values()):
                logger.error("All hosts are unhealthy! Attempting recovery...")
                # Try to recover localhost
                if 'http://localhost:11434' in self.hosts:
                    is_healthy = await self.check_health('http://localhost:11434')
                    if is_healthy:
                        self.health_status['http://localhost:11434'] = True
                        logger.success("Recovered localhost")
            
            # Wait 60 seconds between health check cycles (was 10)
            await asyncio.sleep(60)
            
    def get_best_host(self) -> Optional[str]:
        available_hosts = [h for h in self.hosts if self.health_status[h]]
        if not available_hosts:
            return None
            
        host_scores = {}
        for host in available_hosts:
            load = self.request_counts[host]
            avg_response_time = (
                sum(self.response_times[host][-10:]) / len(self.response_times[host][-10:])
                if self.response_times[host] else 0
            )
            host_scores[host] = load * 0.3 + avg_response_time * 0.7
            
        return min(host_scores, key=host_scores.get)
        
    async def generate_stream(self, model: str, prompt: str, **kwargs):
        """Stream generation from model without time-based timeouts"""
        max_retries = 2
        retry_count = 0
        # NO TIME-BASED TIMEOUTS for resource-constrained environments
        # Models can take as long as needed to generate responses
        
        # Initialize if needed
        if not self.initialized:
            await self.initialize()
        
        while retry_count <= max_retries:
            host = self.get_best_host()
            if not host:
                logger.warning("No available Ollama hosts, attempting recovery...")
                # Try to recover localhost
                if 'http://localhost:11434' in self.hosts:
                    is_healthy = await self.check_health('http://localhost:11434')
                    if is_healthy:
                        self.health_status['http://localhost:11434'] = True
                        host = 'http://localhost:11434'
                        logger.success("Recovered localhost for streaming")
                    else:
                        await asyncio.sleep(2)
                        retry_count += 1
                        continue
                else:
                    await asyncio.sleep(2)
                    retry_count += 1
                    continue
                
            client = self.client_pool[host]
            start_time = datetime.now()
            self.request_counts[host] += 1
            
            # Log to console
            logger.info(f"🤖 Streaming from {model} on {host} (attempt {retry_count + 1})")
            
            try:
                # Ollama 0.5.3 uses 'options' for parameters
                options = {}
                if 'temperature' in kwargs:
                    options['temperature'] = kwargs.pop('temperature')
                if 'top_p' in kwargs:
                    options['top_p'] = kwargs.pop('top_p')
                if 'repeat_penalty' in kwargs:
                    options['repeat_penalty'] = kwargs.pop('repeat_penalty')
                
                # Set stream=True for streaming
                kwargs['stream'] = True
                
                # Stream WITHOUT timeouts - let models take as long as needed
                chunk_count = 0
                
                generator = await client.generate(
                    model=model,
                    prompt=prompt,
                    options=options,
                    **kwargs
                )
                
                async for part in generator:
                    chunk_count += 1
                    # Simply yield chunks as they arrive
                    # No timeout checks - model can take as long as needed
                    yield part
                
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.success(f"✅ Stream from {model} completed in {elapsed:.2f}s")
                return  # Success, exit the retry loop
                    
            except Exception as e:
                self.health_status[host] = False
                logger.error(f"❌ Stream from {model} failed: {e}")
                retry_count += 1
                
                # If it's a connection error, try another host
                if "disconnected" in str(e).lower() or "connection" in str(e).lower():
                    if retry_count <= max_retries:
                        logger.info(f"Connection issue, trying another host...")
                        await asyncio.sleep(1)
                        continue
                        
                raise
            finally:
                self.request_counts[host] -= 1
        
        raise Exception(f"Failed to stream from {model} after {max_retries + 1} attempts")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), reraise=True)
    async def generate(self, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
        host = self.get_best_host()
        if not host:
            raise Exception("No available Ollama hosts")
            
        client = self.client_pool[host]
        start_time = datetime.now()
        self.request_counts[host] += 1
        
        # Log to console
        logger.info(f"🤖 Model call: {model} on {host}")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_model_call(model, f"on {host}")
        except:
            pass
        
        try:
            # Ollama 0.5.3 uses 'options' for parameters
            options = {}
            if 'temperature' in kwargs:
                options['temperature'] = kwargs.pop('temperature')
            if 'top_p' in kwargs:
                options['top_p'] = kwargs.pop('top_p')
            if 'repeat_penalty' in kwargs:
                options['repeat_penalty'] = kwargs.pop('repeat_penalty')
                
            response = await client.generate(
                model=model, 
                prompt=prompt,
                options=options,
                **kwargs
            )
            elapsed = (datetime.now() - start_time).total_seconds()
            self.response_times[host].append(elapsed)
            if len(self.response_times[host]) > 100:
                self.response_times[host] = self.response_times[host][-100:]
                
            # Log success to console
            logger.success(f"✅ Model {model} completed in {elapsed:.2f}s")
            
            # Also log to terminal if available
            try:
                if hasattr(st.session_state, 'terminal'):
                    term_logger.log_model_call(model, f"completed in {elapsed:.2f}s")
            except:
                pass
                
            return response
        except Exception as e:
            self.health_status[host] = False
            
            # Log error to console
            logger.error(f"❌ Model {model} failed: {e}")
            
            # Also log to terminal if available
            try:
                if hasattr(st.session_state, 'terminal'):
                    term_logger.log_error(f"Model {model} failed: {e}", "ModelAPI")
            except:
                pass
                
            raise
        finally:
            self.request_counts[host] -= 1
            
    async def embed(self, model: str, input: str) -> List[float]:
        host = self.get_best_host()
        if not host:
            raise Exception("No available Ollama hosts")
            
        client = self.client_pool[host]
        response = await client.embed(model=model, input=input)
        return response['embeddings'][0]

class ModelPool:
    def __init__(self, load_balancer: OllamaLoadBalancer, config: Dict):
        self.lb = load_balancer
        self.config = config
        self.model_usage = defaultdict(int)
        
    async def stream_from_model(self, model: str, prompt: str, **kwargs):
        """Stream response from a single model with fallback"""
        self.model_usage[model] += 1
        
        full_response = ""
        try:
            async for chunk in self.lb.generate_stream(
                model=model,
                prompt=prompt,
                temperature=kwargs.get('temperature', self.config.get('temperature', 0.7)),
                top_p=kwargs.get('top_p', self.config.get('top_p', 0.95)),
                timeout=kwargs.get('timeout', 120)
            ):
                if 'response' in chunk:
                    full_response += chunk['response']
                    yield {
                        'model': model,
                        'chunk': chunk['response'],
                        'full_response': full_response,
                        'done': chunk.get('done', False)
                    }
        except Exception as e:
            logger.warning(f"Model {model} failed during streaming: {e}")
            # Return partial response if we got something
            if full_response:
                yield {
                    'model': model,
                    'chunk': '',
                    'full_response': full_response,
                    'done': True,
                    'error': str(e)
                }
            else:
                raise
        
    async def get_diverse_responses(self, prompt: str, models: List[str], max_concurrent: int = 5) -> List[Dict]:
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def generate_with_model(model: str):
            async with semaphore:
                try:
                    # Pass parameters as kwargs for the generate method to handle
                    response = await self.lb.generate(
                        model=model,
                        prompt=prompt,
                        temperature=self.config.get('temperature', 0.7),
                        top_p=self.config.get('top_p', 0.95)
                    )
                    self.model_usage[model] += 1
                    return {
                        'model': model,
                        'response': response['response'],
                        'tokens': response.get('total_duration', 0)
                    }
                except Exception as e:
                    logger.error(f"Model {model} failed: {e}")
                    return None
                    
        tasks = [generate_with_model(model) for model in models]
        responses = await asyncio.gather(*tasks)
        return [r for r in responses if r is not None]
        
    def select_models_for_task(self, task_type: str, count: int = 5) -> List[str]:
        if task_type == 'code':
            models = self.config['code_synthesis']['primary']
        elif task_type == 'math':
            models = [self.config['code_synthesis']['specialized']['math']]
        elif task_type == 'reasoning':
            models = [self.config['code_synthesis']['specialized']['reasoning']]
        else:
            models = self.config['general']
            
        sorted_models = sorted(models, key=lambda m: self.model_usage[m])
        return sorted_models[:count]