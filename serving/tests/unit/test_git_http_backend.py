"""Unit tests for git/http_backend.py"""

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from git.http_backend import (
    _get_repos_path,
    _is_push_request,
    _run_git_cgi,
    _validate_token,
    router,
)


class TestGitHttpBackend:
    """Test cases for Git HTTP backend."""

    @pytest.fixture
    def app(self):
        """Create test FastAPI app with git router."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_repos_path(self, tmp_path):
        """Create temporary repos directory."""
        repos_path = tmp_path / "repos"
        repos_path.mkdir()
        return repos_path

    @pytest.fixture
    def mock_repo(self, mock_repos_path):
        """Create mock Git repository."""
        repo_path = mock_repos_path / "test-project.git"
        repo_path.mkdir()
        # Create minimal repo structure
        (repo_path / "HEAD").write_text("ref: refs/heads/main\n")
        (repo_path / "config").write_text("[core]\n\tbare = true\n")
        return repo_path

    # ==========================================================================
    # Helper Function Tests
    # ==========================================================================

    def test_get_repos_path(self):
        """Test getting repos path from config."""
        with patch("git.http_backend.get_config") as mock_config:
            mock_config.return_value.git.repos_path = "/tmp/repos"
            result = _get_repos_path()
            assert result == Path("/tmp/repos")

    def test_is_push_request_receive_pack(self):
        """Test detecting push request from git-receive-pack endpoint."""
        request = MagicMock()
        request.url.path = "/git/project.git/git-receive-pack"
        request.query_params = {}

        assert _is_push_request(request) is True

    def test_is_push_request_info_refs_receive_pack(self):
        """Test detecting push request from info/refs with receive-pack service."""
        request = MagicMock()
        request.url.path = "/git/project.git/info/refs"
        request.query_params.get.return_value = "git-receive-pack"

        assert _is_push_request(request) is True

    def test_is_push_request_upload_pack(self):
        """Test that upload-pack is not detected as push."""
        request = MagicMock()
        request.url.path = "/git/project.git/git-upload-pack"
        request.query_params = {}

        assert _is_push_request(request) is False

    def test_is_push_request_info_refs_upload_pack(self):
        """Test that info/refs with upload-pack is not detected as push."""
        request = MagicMock()
        request.url.path = "/git/project.git/info/refs"
        request.query_params.get.return_value = "git-upload-pack"

        assert _is_push_request(request) is False

    # ==========================================================================
    # Token Validation Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_validate_token_no_service(self):
        """Test token validation when no token service is available."""
        request = MagicMock()
        request.headers.get.return_value = ""

        with patch("git.git_token_service.get_git_token_service", return_value=None):
            result = await _validate_token(request)
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_bearer_valid(self):
        """Test validating a valid Bearer token."""
        request = MagicMock()
        request.headers.get.return_value = "Bearer cvn-ct-validtoken123"

        mock_service = MagicMock()
        mock_service.validate_token = AsyncMock(return_value={
            "type": "compute",
            "compute_id": "compute-123",
        })

        with patch("git.git_token_service.get_git_token_service", return_value=mock_service):
            result = await _validate_token(request)
            assert result == "compute-123"
            mock_service.validate_token.assert_called_once_with("cvn-ct-validtoken123")

    @pytest.mark.asyncio
    async def test_validate_token_bearer_invalid(self):
        """Test validating an invalid Bearer token."""
        request = MagicMock()
        request.headers.get.return_value = "Bearer invalid-token"

        mock_service = MagicMock()
        mock_service.validate_token = AsyncMock(return_value=None)

        with patch("git.git_token_service.get_git_token_service", return_value=mock_service):
            result = await _validate_token(request)
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_basic_auth_valid(self):
        """Test validating a valid Basic Auth token."""
        # Git sends: username:token
        credentials = "git:cvn-ct-validtoken456"
        encoded = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        request = MagicMock()
        request.headers.get.return_value = auth_header

        mock_service = MagicMock()
        mock_service.validate_token = AsyncMock(return_value={
            "type": "compute",
            "compute_id": "compute-456",
        })

        with patch("git.git_token_service.get_git_token_service", return_value=mock_service):
            result = await _validate_token(request)
            assert result == "compute-456"
            mock_service.validate_token.assert_called_once_with("cvn-ct-validtoken456")

    @pytest.mark.asyncio
    async def test_validate_token_basic_auth_pat(self):
        """Test validating a PAT via Basic Auth (returns owner instead of compute_id)."""
        credentials = "user:cvn-pat-usertoken789"
        encoded = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        request = MagicMock()
        request.headers.get.return_value = auth_header

        mock_service = MagicMock()
        mock_service.validate_token = AsyncMock(return_value={
            "type": "pat",
            "owner": "user-789",
        })

        with patch("git.git_token_service.get_git_token_service", return_value=mock_service):
            result = await _validate_token(request)
            assert result == "user-789"

    @pytest.mark.asyncio
    async def test_validate_token_basic_auth_malformed(self):
        """Test validating malformed Basic Auth."""
        # Missing colon separator
        credentials = "malformed-no-colon"
        encoded = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {encoded}"

        request = MagicMock()
        request.headers.get.return_value = auth_header

        with patch("git.git_token_service.get_git_token_service"):
            result = await _validate_token(request)
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_basic_auth_invalid_base64(self):
        """Test validating invalid Base64 in Basic Auth."""
        auth_header = "Basic !!!invalid-base64!!!"

        request = MagicMock()
        request.headers.get.return_value = auth_header

        with patch("git.git_token_service.get_git_token_service"):
            result = await _validate_token(request)
            assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_no_auth_header(self):
        """Test validation when no auth header is present."""
        request = MagicMock()
        request.headers.get.return_value = ""

        mock_service = MagicMock()
        with patch("git.git_token_service.get_git_token_service", return_value=mock_service):
            result = await _validate_token(request)
            assert result is None

    # ==========================================================================
    # Git CGI Execution Tests
    # ==========================================================================

    @pytest.mark.asyncio
    async def test_run_git_cgi_repository_not_found(self, mock_repos_path):
        """Test CGI execution when repository doesn't exist."""
        request = MagicMock()
        request.method = "GET"
        request.query_params = {}
        request.headers.get.return_value = ""

        with pytest.raises(Exception) as exc_info:
            await _run_git_cgi(
                request,
                mock_repos_path,
                "nonexistent",
                "info/refs",
            )
        # Should raise HTTPException with 404
        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_run_git_cgi_success(self, mock_repos_path, mock_repo):
        """Test successful CGI execution."""
        request = MagicMock()
        request.method = "GET"
        request.query_params = {"service": "git-upload-pack"}
        request.headers.get.return_value = "application/x-git-upload-pack-request"
        request.body = AsyncMock(return_value=b"")

        # Mock subprocess execution
        mock_process = MagicMock()
        mock_process.returncode = 0
        # Simulate CGI response with headers and body
        cgi_response = (
            b"Content-Type: application/x-git-upload-pack-result\r\n"
            b"Status: 200 OK\r\n"
            b"\r\n"
            b"mock git response data"
        )
        mock_process.communicate = AsyncMock(return_value=(cgi_response, b""))

        with patch("git.http_backend.asyncio.create_subprocess_exec", return_value=mock_process):
            response = await _run_git_cgi(
                request,
                mock_repos_path,
                "test-project",
                "git-upload-pack",
            )

            assert response.status_code == 200
            assert response.media_type == "application/x-git-upload-pack-result"
            assert response.body == b"mock git response data"

    @pytest.mark.asyncio
    async def test_run_git_cgi_with_compute_id(self, mock_repos_path, mock_repo):
        """Test CGI execution with authenticated compute ID."""
        request = MagicMock()
        request.method = "POST"
        request.query_params = {}
        request.headers.get.return_value = "application/x-git-receive-pack-request"
        request.body = AsyncMock(return_value=b"pack data")

        mock_process = MagicMock()
        mock_process.returncode = 0
        cgi_response = b"Content-Type: application/x-git-receive-pack-result\r\n\r\nok"
        mock_process.communicate = AsyncMock(return_value=(cgi_response, b""))

        with patch("git.http_backend.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            await _run_git_cgi(
                request,
                mock_repos_path,
                "test-project",
                "git-receive-pack",
                compute_id="compute-auth-123",
            )

            # Verify environment variables were set
            call_args = mock_exec.call_args
            env = call_args[1]["env"]
            assert env["GIT_PUSH_COMPUTE_ID"] == "compute-auth-123"
            assert env["REMOTE_USER"] == "compute-auth-123"

    @pytest.mark.asyncio
    async def test_run_git_cgi_environment_setup(self, mock_repos_path, mock_repo):
        """Test that CGI environment variables are set correctly."""
        request = MagicMock()
        request.method = "GET"
        request.query_params = {"service": "git-upload-pack"}
        request.headers.get.return_value = "application/x-git-upload-pack-request"
        request.body = AsyncMock(return_value=b"")

        mock_process = MagicMock()
        mock_process.returncode = 0
        cgi_response = b"Content-Type: text/plain\r\n\r\ntest"
        mock_process.communicate = AsyncMock(return_value=(cgi_response, b""))

        with patch("git.http_backend.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            await _run_git_cgi(
                request,
                mock_repos_path,
                "test-project",
                "info/refs",
            )

            # Verify environment
            call_args = mock_exec.call_args
            env = call_args[1]["env"]
            assert env["GIT_PROJECT_ROOT"] == str(mock_repos_path)
            assert env["GIT_HTTP_EXPORT_ALL"] == "1"
            assert env["PATH_INFO"] == "/test-project.git/info/refs"
            assert env["REQUEST_METHOD"] == "GET"
            assert "QUERY_STRING" in env
            assert "PATH" in env

    @pytest.mark.asyncio
    async def test_run_git_cgi_post_with_body(self, mock_repos_path, mock_repo):
        """Test CGI execution with POST body."""
        request = MagicMock()
        request.method = "POST"
        request.query_params = {}
        request.headers.get.return_value = "application/x-git-upload-pack-request"
        post_body = b"test pack data"
        request.body = AsyncMock(return_value=post_body)

        mock_process = MagicMock()
        mock_process.returncode = 0
        cgi_response = b"Content-Type: text/plain\r\n\r\nok"
        mock_process.communicate = AsyncMock(return_value=(cgi_response, b""))

        with patch("git.http_backend.asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            await _run_git_cgi(
                request,
                mock_repos_path,
                "test-project",
                "git-upload-pack",
            )

            # Verify body was passed to subprocess
            call_args = mock_exec.call_args
            env = call_args[1]["env"]
            assert env["CONTENT_LENGTH"] == str(len(post_body))

            # Verify communicate was called with body
            mock_process.communicate.assert_called_once_with(input=post_body)

    @pytest.mark.asyncio
    async def test_run_git_cgi_process_failure(self, mock_repos_path, mock_repo):
        """Test handling of git-http-backend process failure."""
        request = MagicMock()
        request.method = "GET"
        request.query_params = {}
        request.headers.get.return_value = ""
        request.body = AsyncMock(return_value=b"")

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"fatal: error"))

        with patch("git.http_backend.asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(Exception) as exc_info:
                await _run_git_cgi(
                    request,
                    mock_repos_path,
                    "test-project",
                    "info/refs",
                )
            assert "failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_run_git_cgi_parse_status_header(self, mock_repos_path, mock_repo):
        """Test parsing CGI Status header."""
        request = MagicMock()
        request.method = "GET"
        request.query_params = {}
        request.headers.get.return_value = ""
        request.body = AsyncMock(return_value=b"")

        mock_process = MagicMock()
        mock_process.returncode = 0
        # CGI with Status header
        cgi_response = (
            b"Status: 404 Not Found\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Not found"
        )
        mock_process.communicate = AsyncMock(return_value=(cgi_response, b""))

        with patch("git.http_backend.asyncio.create_subprocess_exec", return_value=mock_process):
            response = await _run_git_cgi(
                request,
                mock_repos_path,
                "test-project",
                "info/refs",
            )

            assert response.status_code == 404
            assert response.body == b"Not found"

    # ==========================================================================
    # Endpoint Integration Tests
    # ==========================================================================

    def test_info_refs_read_no_auth(self, client, mock_repos_path, mock_repo):
        """Test info/refs endpoint for read (clone/fetch) without auth."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value=None):
                with patch("git.http_backend._run_git_cgi", new_callable=AsyncMock) as mock_cgi:
                    from fastapi.responses import Response
                    mock_cgi.return_value = Response(content=b"test", media_type="text/plain")

                    response = client.get("/git/test-project.git/info/refs?service=git-upload-pack")

                    # Should succeed without auth for read operations
                    assert response.status_code == 200

    def test_info_refs_push_requires_auth(self, client, mock_repos_path, mock_repo):
        """Test info/refs endpoint for push requires authentication."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value=None):
                response = client.get("/git/test-project.git/info/refs?service=git-receive-pack")

                # Should return 401 for push without auth
                assert response.status_code == 401
                assert "WWW-Authenticate" in response.headers

    def test_info_refs_push_with_auth(self, client, mock_repos_path, mock_repo):
        """Test info/refs endpoint for push with authentication."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value="compute-123"):
                with patch("git.http_backend._run_git_cgi", new_callable=AsyncMock) as mock_cgi:
                    from fastapi.responses import Response
                    mock_cgi.return_value = Response(content=b"test", media_type="text/plain")

                    headers = {"Authorization": "Bearer cvn-ct-validtoken"}
                    response = client.get(
                        "/git/test-project.git/info/refs?service=git-receive-pack",
                        headers=headers
                    )

                    # Should succeed with auth
                    assert response.status_code == 200

    def test_upload_pack_no_auth_required(self, client, mock_repos_path, mock_repo):
        """Test git-upload-pack endpoint (read operation, no auth required)."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value=None):
                with patch("git.http_backend._run_git_cgi", new_callable=AsyncMock) as mock_cgi:
                    from fastapi.responses import Response
                    mock_cgi.return_value = Response(content=b"pack data", media_type="application/x-git-upload-pack-result")

                    response = client.post("/git/test-project.git/git-upload-pack")

                    # Upload-pack is read-only, should work without auth
                    assert response.status_code == 200

    def test_receive_pack_requires_auth(self, client, mock_repos_path, mock_repo):
        """Test git-receive-pack endpoint requires authentication."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value=None):
                response = client.post("/git/test-project.git/git-receive-pack")

                # Receive-pack is write operation, requires auth
                assert response.status_code == 401
                assert "WWW-Authenticate" in response.headers
                assert b"Authentication required" in response.content

    def test_receive_pack_with_auth(self, client, mock_repos_path, mock_repo):
        """Test git-receive-pack endpoint with authentication."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value="compute-456"):
                with patch("git.http_backend._run_git_cgi", new_callable=AsyncMock) as mock_cgi:
                    from fastapi.responses import Response
                    mock_cgi.return_value = Response(content=b"ok", media_type="application/x-git-receive-pack-result")

                    headers = {"Authorization": "Bearer cvn-ct-validtoken"}
                    response = client.post(
                        "/git/test-project.git/git-receive-pack",
                        headers=headers
                    )

                    # Should succeed with auth
                    assert response.status_code == 200
                    # Verify compute_id was passed to CGI
                    mock_cgi.assert_called_once()
                    call_kwargs = mock_cgi.call_args[1]
                    assert call_kwargs["compute_id"] == "compute-456"

    def test_receive_pack_www_authenticate_header(self, client, mock_repos_path):
        """Test that 401 responses include WWW-Authenticate header."""
        with patch("git.http_backend._get_repos_path", return_value=mock_repos_path):
            with patch("git.http_backend._validate_token", new_callable=AsyncMock, return_value=None):
                response = client.post("/git/test-project.git/git-receive-pack")

                assert response.status_code == 401
                assert response.headers["WWW-Authenticate"] == 'Basic realm="ClaudeVN Git"'
