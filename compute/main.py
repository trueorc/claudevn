"""
Main entry point for ClaudeVN Compute Engine.

This script starts the compute engine with proper configuration and logging.
"""

import sys
import logging
from pathlib import Path
import uvicorn

from config import load_config


def setup_logging(config):
    """Set up logging configuration."""
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    
    # Create log directory if specified
    if config.log_file:
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(config.log_file) if config.log_file else logging.NullHandler()
        ]
    )
    
    return logging.getLogger(__name__)


def main():
    """Main entry point."""
    # Load configuration
    config = load_config()
    
    # Setup logging
    logger = setup_logging(config)
    
    logger.info("="*60)
    logger.info("ClaudeVN Compute Engine")
    logger.info("="*60)
    logger.info(f"Instance ID: {config.instance_id}")
    logger.info(f"Instance Name: {config.instance_name}")
    logger.info(f"Host: {config.host}")
    logger.info(f"Port: {config.port}")
    logger.info(f"Serving URL: {config.serving_url}")
    logger.info(f"Storage: {config.storage_path}")
    logger.info(f"Register on startup: {config.register_on_startup}")
    if config.agents_dir:
        logger.info(f"Agents directory: {config.agents_dir}")
    if config.tools_dir:
        logger.info(f"Tools directory: {config.tools_dir}")
    logger.info("="*60)
    
    # Start server
    try:
        uvicorn.run(
            "app:app",
            host=config.host,
            port=config.port,
            reload=False,
            log_level=config.log_level.lower(),
            access_log=True
        )
    except KeyboardInterrupt:
        logger.info("Shutting down due to keyboard interrupt...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

