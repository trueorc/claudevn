"""Unit tests for QualityGateService.

Tests the quality gate validation pipeline including syntax checking,
test execution, startup smoke tests, and config completeness validation.
All git/subprocess operations are mocked.
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from services.quality_gate_service import (
    GateResult,
    GateStatus,
    QualityGateService,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    """Provide a mock ServingConfig with quality gate settings."""
    config = MagicMock()
    config.quality_gate.enabled = True
    config.quality_gate.syntax_check = True
    config.quality_gate.test_gate = True
    config.quality_gate.startup_smoke_test = False
    config.quality_gate.config_completeness = False
    config.quality_gate.timeout_seconds = 60
    config.git.repos_path = "/repos"
    return config


@pytest.fixture
def service(mock_config):
    with patch("services.quality_gate_service.get_config", return_value=mock_config):
        svc = QualityGateService()
    return svc


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------

class TestGateResult:
    def test_to_dict(self):
        result = GateResult(
            gate="syntax_check",
            status=GateStatus.PASSED,
            message="2 file(s) checked",
            details=["a.py", "b.py"],
            duration_ms=42,
        )
        d = result.to_dict()
        assert d["gate"] == "syntax_check"
        assert d["status"] == "passed"
        assert d["message"] == "2 file(s) checked"
        assert d["details"] == ["a.py", "b.py"]
        assert d["duration_ms"] == 42

    def test_to_dict_defaults(self):
        result = GateResult(gate="x", status=GateStatus.SKIPPED)
        d = result.to_dict()
        assert d["details"] == []
        assert d["duration_ms"] == 0


class TestValidationResult:
    def test_to_dict_passed(self):
        vr = ValidationResult(
            passed=True,
            gates=[GateResult(gate="a", status=GateStatus.PASSED, message="ok")],
            started_at="t0",
            completed_at="t1",
        )
        d = vr.to_dict()
        assert d["passed"] is True
        assert len(d["gates"]) == 1
        assert d["started_at"] == "t0"

    def test_to_dict_empty_gates(self):
        vr = ValidationResult(passed=True)
        d = vr.to_dict()
        assert d["gates"] == []


# ---------------------------------------------------------------------------
# QualityGateService.validate_branch
# ---------------------------------------------------------------------------

class TestValidateBranchDisabled:
    @pytest.mark.asyncio
    async def test_returns_skipped_when_disabled(self, mock_config):
        mock_config.quality_gate.enabled = False
        with patch("services.quality_gate_service.get_config", return_value=mock_config):
            svc = QualityGateService()
        result = await svc.validate_branch("proj", "feat-1")
        assert result.passed is True
        assert result.gates[0].status == GateStatus.SKIPPED
        assert "disabled" in result.gates[0].message


class TestValidateBranchSetupFailure:
    @pytest.mark.asyncio
    async def test_setup_failure_returns_error(self, service):
        with patch("services.quality_gate_service.tempfile.mkdtemp", side_effect=OSError("disk full")):
            result = await service.validate_branch("proj", "feat-1")
        assert result.passed is False
        assert result.gates[0].status == GateStatus.ERROR
        assert "disk full" in result.gates[0].message


class TestValidateBranchMergeConflict:
    @pytest.mark.asyncio
    async def test_merge_conflict_returns_failed(self, service):
        """If the merge itself fails, return immediately with merge gate failure."""
        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            result = MagicMock()
            if "clone" in cmd:
                result.returncode = 0
            elif "checkout" in cmd:
                result.returncode = 0
            elif "diff" in cmd:
                result.returncode = 0
                result.stdout = "a.py\n"
            elif "merge" in cmd:
                result.returncode = 1
                result.stderr = "CONFLICT"
                result.stdout = ""
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with (
            patch("services.quality_gate_service.subprocess.run", side_effect=mock_run),
            patch("services.quality_gate_service.tempfile.mkdtemp", return_value="/tmp/qg"),
            patch("services.quality_gate_service.shutil.rmtree"),
            patch("git.repo_manager.RepoManager") as MockRM,
            patch("git.repo_manager.get_config") as mock_rm_config,
        ):
            mock_rm_config.return_value.git.repos_path = "/repos"
            MockRM.return_value.get_default_branch.return_value = "main"
            result = await service.validate_branch("proj", "feat-1")

        assert result.passed is False
        assert any(g.gate == "merge" for g in result.gates)


# ---------------------------------------------------------------------------
# Individual gate tests
# ---------------------------------------------------------------------------

class TestSyntaxCheck:
    @pytest.mark.asyncio
    async def test_no_python_files_skipped(self, service):
        result = await service._run_syntax_check(Path("/tmp"), ["readme.md"])
        assert result.status == GateStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_valid_files_pass(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result) as mock_thread:
            # Mock file existence
            with patch.object(Path, "exists", return_value=True):
                result = await service._run_syntax_check(Path("/tmp/work"), ["app.py"])

        assert result.status == GateStatus.PASSED
        assert "1 file(s) checked" in result.message

    @pytest.mark.asyncio
    async def test_syntax_error_detected(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "SyntaxError: invalid syntax"

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            with patch.object(Path, "exists", return_value=True):
                result = await service._run_syntax_check(Path("/tmp/work"), ["bad.py"])

        assert result.status == GateStatus.FAILED
        assert "1 file(s) have syntax errors" in result.message
        assert any("SyntaxError" in d for d in result.details)

    @pytest.mark.asyncio
    async def test_deleted_files_skipped(self, service):
        """Deleted files (exist in diff but not on disk) are skipped without errors."""
        with patch.object(Path, "exists", return_value=False):
            result = await service._run_syntax_check(Path("/tmp/work"), ["deleted.py"])

        # File is skipped (not compiled) but still counted; no errors = PASSED
        assert result.status == GateStatus.PASSED


class TestTestGate:
    @pytest.mark.asyncio
    async def test_tests_pass(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "5 passed"
        mock_result.stderr = ""

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            result = await service._run_test_gate(Path("/tmp/work"), timeout=60)

        assert result.status == GateStatus.PASSED

    @pytest.mark.asyncio
    async def test_tests_fail(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "FAILED test_foo.py::test_bar"
        mock_result.stderr = ""

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            result = await service._run_test_gate(Path("/tmp/work"), timeout=60)

        assert result.status == GateStatus.FAILED
        assert "Test suite failed" in result.message

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self, service):
        with patch(
            "services.quality_gate_service.asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=60),
        ):
            result = await service._run_test_gate(Path("/tmp/work"), timeout=60)

        assert result.status == GateStatus.ERROR
        assert "timed out" in result.message


class TestStartupSmokeTest:
    @pytest.mark.asyncio
    async def test_import_succeeds(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            result = await service._run_startup_smoke_test(Path("/tmp/work"), timeout=30)

        assert result.status == GateStatus.PASSED

    @pytest.mark.asyncio
    async def test_import_fails(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ImportError: No module named 'missing'"

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            result = await service._run_startup_smoke_test(Path("/tmp/work"), timeout=30)

        assert result.status == GateStatus.FAILED
        assert "failed to import" in result.message


class TestConfigCompletenessCheck:
    @pytest.mark.asyncio
    async def test_no_env_refs_skipped(self, service):
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text", return_value="x = 1"):
                result = await service._run_config_completeness_check(
                    Path("/tmp/work"), ["app.py"]
                )
        assert result.status == GateStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_missing_env_var_fails(self, service):
        py_content = 'db_url = os.getenv("DATABASE_URL")'
        env_content = "# empty template\n"

        def mock_exists(self_path):
            return True

        def mock_read_text(self_path, **kwargs):
            name = str(self_path)
            if name.endswith(".py"):
                return py_content
            return env_content

        with (
            patch.object(Path, "exists", mock_exists),
            patch.object(Path, "read_text", mock_read_text),
        ):
            result = await service._run_config_completeness_check(
                Path("/tmp/work"), ["app.py"]
            )

        assert result.status == GateStatus.FAILED
        assert "DATABASE_URL" in str(result.details)

    @pytest.mark.asyncio
    async def test_present_env_var_passes(self, service):
        py_content = 'db_url = os.getenv("DATABASE_URL")'
        env_content = "DATABASE_URL=postgres://localhost/db\n"

        def mock_exists(self_path):
            return True

        def mock_read_text(self_path, **kwargs):
            name = str(self_path)
            if name.endswith(".py"):
                return py_content
            return env_content

        with (
            patch.object(Path, "exists", mock_exists),
            patch.object(Path, "read_text", mock_read_text),
        ):
            result = await service._run_config_completeness_check(
                Path("/tmp/work"), ["app.py"]
            )

        assert result.status == GateStatus.PASSED

    @pytest.mark.asyncio
    async def test_no_python_files_skipped(self, service):
        result = await service._run_config_completeness_check(
            Path("/tmp/work"), ["readme.md"]
        )
        assert result.status == GateStatus.SKIPPED
