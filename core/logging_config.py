"""
Configure loguru for better console output
"""
import sys
from loguru import logger

def configure_logging(verbose: bool = False):
    """Configure loguru with proper formatting"""
    
    # Remove default handler
    logger.remove()
    
    # Add console handler with custom format
    if verbose:
        # Detailed format for debugging
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="DEBUG"
        )
    else:
        # Clean format for production
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="INFO"
        )
    
    # Add file handler for full logs
    logger.add(
        "logs/hydra_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    
    return logger

# Color-coded log levels for better visibility
logger.level("TRACE", color="<white>")
logger.level("DEBUG", color="<blue>")
logger.level("INFO", color="<cyan>")
logger.level("SUCCESS", color="<green>")
logger.level("WARNING", color="<yellow>")
logger.level("ERROR", color="<red>")
logger.level("CRITICAL", color="<red><bold>")