"""
Async helpers for Streamlit compatibility
Handles running async code in Streamlit's event loop
"""

import asyncio
import inspect
from typing import Any, Coroutine
from loguru import logger

def run_async(coro: Coroutine) -> Any:
    """
    Run async function in a way compatible with Streamlit
    
    This handles the case where we might already be in an event loop
    (which happens in Streamlit) or not (command line execution).
    """
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        
        if loop.is_running():
            # We're already in a running event loop (Streamlit case)
            # Create a task and run it
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
        else:
            # No event loop running, we can use asyncio.run()
            return asyncio.run(coro)
            
    except RuntimeError:
        # No event loop at all, create one
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"Error running async function: {e}")
        raise

def create_async_task(coro: Coroutine):
    """
    Create an async task that won't block Streamlit
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule the coroutine to run in the background
            return asyncio.create_task(coro)
        else:
            # Run in a new event loop
            return asyncio.run(coro)
    except RuntimeError:
        return asyncio.run(coro)

async def gather_async(*coros):
    """
    Gather multiple async operations safely
    """
    return await asyncio.gather(*coros, return_exceptions=True)

def is_async_context() -> bool:
    """
    Check if we're currently in an async context
    """
    try:
        loop = asyncio.get_running_loop()
        return loop is not None and loop.is_running()
    except RuntimeError:
        return False

class AsyncContextManager:
    """
    Context manager for handling async operations in Streamlit
    """
    def __init__(self):
        self.loop = None
        self.nest_applied = False
        
    def __enter__(self):
        try:
            self.loop = asyncio.get_event_loop()
            if self.loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                self.nest_applied = True
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.nest_applied:
            # Reset nest_asyncio if we applied it
            pass
        return False
        
    def run(self, coro):
        """Run a coroutine in the context"""
        if self.loop.is_running() and self.nest_applied:
            return self.loop.run_until_complete(coro)
        elif not self.loop.is_running():
            return self.loop.run_until_complete(coro)
        else:
            # Create a task if loop is already running
            task = asyncio.create_task(coro)
            return task