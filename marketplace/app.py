"""
ClaudeVN Skill Marketplace - Standalone Service
Manages atomic skills and composes them into agent bundles.
"""

import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from skill_registry import SkillRegistry, set_skill_registry
from persona_registry import PersonaRegistry, set_persona_registry
from config import get_config
from api import router as skills_router, persona_router, tools_router, agents_router, audit_router
from services.registration_client import MarketplaceRegistrationClient
from claudevn_shared.version import get_version

# Global registration client (set during lifespan)
_registration_client: MarketplaceRegistrationClient | None = None
_registration_retry_task: "asyncio.Task | None" = None

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def _registration_retry_loop(
    client: MarketplaceRegistrationClient,
    max_retries: int = 10,
    initial_delay: float = 5.0,
    max_delay: float = 60.0
):
    """Background task to retry registration with Serving.

    This handles the case where marketplace starts before serving is available
    (due to Docker dependency order: serving depends on marketplace).

    Args:
        client: The registration client to use
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        await asyncio.sleep(delay)

        logger.info(f"Attempting registration retry {attempt}/{max_retries}...")

        try:
            if await client.register():
                await client.start_heartbeat()
                logger.info("Successfully registered with Serving on retry")
                return
            else:
                logger.warning(f"Registration retry {attempt} failed")
        except Exception as e:
            logger.warning(f"Registration retry {attempt} error: {e}")

        # Exponential backoff with max cap
        delay = min(delay * 1.5, max_delay)

    logger.error(
        f"Failed to register with Serving after {max_retries} retries. "
        "Operating in standalone mode."
    )


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication.

    Supports multiple named API keys (SERVING_API_KEY, ADMIN_API_KEY,
    MARKETPLACE_API_KEY) for different clients.
    """

    PUBLIC_PATHS = ['/', '/docs', '/openapi.json', '/redoc']
    _auth_disabled_warned = False

    async def dispatch(self, request: Request, call_next):
        config = get_config()

        if not config.require_auth:
            if not APIKeyAuthMiddleware._auth_disabled_warned:
                logger.warning(
                    "API key authentication is DISABLED "
                    "(MARKETPLACE_REQUIRE_AUTH=false). "
                    "This is insecure for production deployments."
                )
                APIKeyAuthMiddleware._auth_disabled_warned = True
            return await call_next(request)

        path = request.url.path
        if path in self.PUBLIC_PATHS or path.endswith('/health'):
            return await call_next(request)

        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing API key. Include X-API-Key header."}
            )

        valid_keys = set(config.api_keys.values())
        if config.api_key:
            valid_keys.add(config.api_key)

        if not valid_keys:
            logger.error(
                "Authentication is enabled but no API keys are configured. "
                "Set MARKETPLACE_API_KEY, SERVING_API_KEY, or ADMIN_API_KEY."
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Server authentication misconfigured"}
            )

        if api_key not in valid_keys:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"}
            )

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global _registration_client, _registration_retry_task

    logger.info("Starting ClaudeVN Skill Marketplace...")
    config = get_config()

    # Initialize skill registry
    skills_path = os.getenv('SKILLS_PATH', './skills')
    try:
        skill_registry = SkillRegistry(skills_path=skills_path)
        await skill_registry.initialize()
        set_skill_registry(skill_registry)
        stats = skill_registry.get_stats()
        logger.info(f"Skill registry initialized: {stats['total_skills']} skills, {stats['total_tools']} tools")
    except Exception as e:
        logger.error(f"Failed to initialize skill registry: {e}")
        raise

    # Initialize persona registry
    personas_path = os.getenv('PERSONAS_PATH', './personas')
    try:
        persona_registry = PersonaRegistry(personas_path=personas_path)
        await persona_registry.initialize()
        # Wire bidirectional references between registries:
        # - PersonaRegistry needs SkillRegistry for merged instruction generation
        # - SkillRegistry needs PersonaRegistry for invalidation on skill updates
        persona_registry.set_skill_registry(skill_registry)
        skill_registry.set_persona_registry(persona_registry)
        set_persona_registry(persona_registry)
        persona_stats = persona_registry.get_stats()
        logger.info(f"Persona registry initialized: {persona_stats['total_personas']} personas")
    except Exception as e:
        logger.error(f"Failed to initialize persona registry: {e}")
        raise

    # Register with Serving (if configured)
    if config.serving_url and config.register_on_startup:
        marketplace_endpoint = f"http://{config.host}:{config.port}"
        # Use external hostname if available
        if os.getenv('MARKETPLACE_ENDPOINT'):
            marketplace_endpoint = os.getenv('MARKETPLACE_ENDPOINT')

        _registration_client = MarketplaceRegistrationClient(
            serving_url=config.serving_url,
            marketplace_id=config.marketplace_id,
            marketplace_name=config.marketplace_name,
            endpoint=marketplace_endpoint,
            version="1.0.0",
            heartbeat_interval=config.heartbeat_interval
        )

        # Update capabilities from registries
        _registration_client.update_capabilities(
            skill_count=stats['total_skills'],
            persona_count=persona_stats['total_personas'],
            tool_count=stats['total_tools']
        )

        if await _registration_client.register():
            await _registration_client.start_heartbeat()
        else:
            # Start background retry task (handles case where serving isn't ready yet)
            logger.warning(
                "Initial registration failed - starting background retry. "
                "This is expected if serving hasn't started yet."
            )
            _registration_retry_task = asyncio.create_task(
                _registration_retry_loop(_registration_client)
            )
    else:
        logger.info("Registration with Serving not configured (SERVING_URL not set)")

    logger.info("Skill Marketplace started successfully")
    yield

    # Shutdown: cancel retry task, stop heartbeat and deregister
    if _registration_retry_task and not _registration_retry_task.done():
        _registration_retry_task.cancel()
        try:
            await _registration_retry_task
        except asyncio.CancelledError:
            pass

    if _registration_client:
        await _registration_client.stop_heartbeat()
        await _registration_client.deregister()

    logger.info("Skill Marketplace stopped")


app = FastAPI(
    title="ClaudeVN Skill Marketplace",
    description="Manages atomic skills and composes them into agent bundles for Claude Code",
    version=get_version(),
    lifespan=lifespan
)

# CORS
cors_origins = os.getenv('CORS_ORIGINS', '*')
origins = ["*"] if cors_origins == '*' else [o.strip() for o in cors_origins.split(',')]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Authentication (enabled by default; disable with MARKETPLACE_REQUIRE_AUTH=false)
app.add_middleware(APIKeyAuthMiddleware)

# Include routers
API_VERSION = os.getenv('API_VERSION', 'v1')
api_prefix = f"/api/{API_VERSION}"
app.include_router(skills_router, prefix=api_prefix)
app.include_router(persona_router, prefix=api_prefix)
app.include_router(tools_router, prefix=api_prefix)
app.include_router(agents_router, prefix=api_prefix)
app.include_router(audit_router, prefix=api_prefix)


@app.get(f"{api_prefix}/health")
async def health_check():
    """Health check endpoint."""
    from skill_registry import get_skill_registry
    from persona_registry import get_persona_registry

    skill_registry = get_skill_registry()
    persona_registry = get_persona_registry()

    skill_stats = skill_registry.get_stats()
    persona_stats = persona_registry.get_stats()

    return {
        "status": "healthy",
        "service": "marketplace",
        "version": get_version(),
        "skills": skill_stats["total_skills"],
        "tools": skill_stats["total_tools"],
        "personas": persona_stats["total_personas"]
    }


@app.get("/")
def root():
    return {
        "service": "ClaudeVN Skill Marketplace",
        "version": "1.0.0",
        "api_docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    host = os.getenv('MARKETPLACE_HOST', '0.0.0.0')
    port = int(os.getenv('MARKETPLACE_PORT', 8003))
    uvicorn.run("app:app", host=host, port=port, reload=True)
