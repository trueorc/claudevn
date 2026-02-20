"""Git Smart HTTP backend for ClaudeVN.

Replaces SSH-based Git transport with HTTP, eliminating the need for
a separate git user, sshd, SSH key management, and chown operations.

Wraps the git-http-backend CGI program via FastAPI's StreamingResponse.
Mounted at /git/ for clean clone URLs:
    http://serving:8002/git/project.git/info/refs
    http://serving:8002/git/project.git/git-upload-pack
    http://serving:8002/git/project.git/git-receive-pack
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["git-http"])


def _get_repos_path() -> Path:
    """Get the path to bare Git repositories."""
    return Path(get_config().git.repos_path)


async def _validate_token(request: Request) -> Optional[str]:
    """Extract and validate token from Basic Auth or Bearer header.

    Returns the compute_id associated with the token, or None for
    unauthenticated read-only operations (git clone/fetch).

    For push operations, authentication is required.
    """
    from .git_token_service import get_git_token_service

    token_service = get_git_token_service()
    if not token_service:
        # No token service available - allow unauthenticated access
        return None

    # Try Bearer token first
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif auth_header.startswith("Basic "):
        # Git clients send Basic Auth: username is ignored, password is token
        import base64
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            # Format: username:password — password is the token
            _, token = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return None
    else:
        return None

    result = await token_service.validate_token(token)
    if result:
        return result.get("compute_id") or result.get("owner")
    return None


def _is_push_request(request: Request) -> bool:
    """Determine if this is a push (write) request."""
    path = request.url.path
    # git-receive-pack is used for push operations
    if path.endswith("/git-receive-pack"):
        return True
    # info/refs?service=git-receive-pack is the push discovery
    if "info/refs" in path and request.query_params.get("service") == "git-receive-pack":
        return True
    return False


async def _run_git_cgi(
    request: Request,
    repos_path: Path,
    project: str,
    path_info: str,
    compute_id: Optional[str] = None,
) -> StreamingResponse:
    """Execute git-http-backend as a CGI subprocess.

    Args:
        request: The incoming HTTP request
        repos_path: Path to bare Git repositories
        project: Project name (without .git suffix)
        path_info: The path after /git/project.git/
        compute_id: Authenticated compute ID (for push authorization)

    Returns:
        StreamingResponse with git-http-backend output
    """
    repo_path = repos_path / f"{project}.git"

    if not repo_path.exists() or not (repo_path / "HEAD").exists():
        raise HTTPException(status_code=404, detail=f"Repository not found: {project}")

    # Build CGI environment
    env = {
        "GIT_PROJECT_ROOT": str(repos_path),
        "GIT_HTTP_EXPORT_ALL": "1",
        "PATH_INFO": f"/{project}.git/{path_info}",
        "REQUEST_METHOD": request.method,
        "QUERY_STRING": str(request.query_params),
        "CONTENT_TYPE": request.headers.get("content-type", ""),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        # No safe.directory bypass needed — serving owns the repos now
    }

    # Pass compute_id for hook authorization
    if compute_id:
        env["GIT_PUSH_COMPUTE_ID"] = compute_id
        env["REMOTE_USER"] = compute_id

    # Read request body for POST requests
    body = b""
    if request.method == "POST":
        body = await request.body()
        env["CONTENT_LENGTH"] = str(len(body))

    # Execute git-http-backend
    process = await asyncio.create_subprocess_exec(
        "git", "http-backend",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    stdout, stderr = await process.communicate(input=body)

    if stderr:
        logger.debug(f"git-http-backend stderr: {stderr.decode(errors='replace')}")

    if process.returncode != 0:
        logger.error(
            f"git-http-backend failed (exit {process.returncode}): "
            f"{stderr.decode(errors='replace')}"
        )
        raise HTTPException(
            status_code=500,
            detail="Git operation failed"
        )

    # Parse CGI response headers
    # CGI output format: headers\r\n\r\nbody
    header_end = stdout.find(b"\r\n\r\n")
    if header_end == -1:
        header_end = stdout.find(b"\n\n")
        header_sep_len = 2
    else:
        header_sep_len = 4

    if header_end == -1:
        raise HTTPException(status_code=500, detail="Invalid CGI response")

    raw_headers = stdout[:header_end].decode("utf-8", errors="replace")
    response_body = stdout[header_end + header_sep_len:]

    # Parse headers
    response_headers = {}
    status_code = 200
    for line in raw_headers.split("\n"):
        line = line.strip()
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "status":
                # CGI status header: "200 OK" or "404 Not Found"
                try:
                    status_code = int(value.split()[0])
                except (ValueError, IndexError):
                    pass
            else:
                response_headers[key] = value

    content_type = response_headers.get("content-type", "application/octet-stream")

    return Response(
        content=response_body,
        status_code=status_code,
        media_type=content_type,
        headers={k: v for k, v in response_headers.items() if k != "content-type"},
    )


# ==========================================================================
# Routes
# ==========================================================================

@router.get("/git/{project}.git/info/refs")
async def git_info_refs(project: str, request: Request, service: str = ""):
    """Handle Git info/refs discovery request."""
    # For push discovery, require authentication
    if service == "git-receive-pack":
        compute_id = await _validate_token(request)
        if not compute_id:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="ClaudeVN Git"'},
                content="Authentication required for push operations",
            )
    else:
        compute_id = await _validate_token(request)

    repos_path = _get_repos_path()
    return await _run_git_cgi(
        request, repos_path, project, f"info/refs",
        compute_id=compute_id,
    )


@router.post("/git/{project}.git/git-upload-pack")
async def git_upload_pack(project: str, request: Request):
    """Handle Git fetch/clone (upload-pack is read-only)."""
    compute_id = await _validate_token(request)
    repos_path = _get_repos_path()
    return await _run_git_cgi(
        request, repos_path, project, "git-upload-pack",
        compute_id=compute_id,
    )


@router.post("/git/{project}.git/git-receive-pack")
async def git_receive_pack(project: str, request: Request):
    """Handle Git push (receive-pack requires authentication)."""
    compute_id = await _validate_token(request)
    if not compute_id:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="ClaudeVN Git"'},
            content="Authentication required for push operations",
        )

    repos_path = _get_repos_path()
    return await _run_git_cgi(
        request, repos_path, project, "git-receive-pack",
        compute_id=compute_id,
    )
