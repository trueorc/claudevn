"""
Main entry point for ClaudeVN Compute Engine.

Runs the compute infrastructure as a standalone asyncio process.
No HTTP server — connects outbound to Serving via SSE.
"""

import sys
import asyncio
import logging

from config import load_config


def main():
    """Main entry point."""
    # Load configuration for startup banner
    config = load_config()

    # Setup logging
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("ClaudeVN Compute Engine")
    logger.info("=" * 60)
    logger.info(f"Instance ID: {config.instance_id}")
    logger.info(f"Instance Name: {config.instance_name}")
    logger.info(f"Serving URL: {config.serving_url}")
    logger.info(f"Storage: {config.storage_path if hasattr(config, 'storage_path') else 'N/A'}")
    logger.info("=" * 60)

    try:
        from app import main as async_main
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Shutting down due to keyboard interrupt...")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
