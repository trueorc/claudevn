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
    _collect_known_config_vars,
    _detect_startup_command,
    _detect_test_command,
    _extract_top_level_modules,
    _parse_compile_error,
    _parse_import_error,
    _parse_test_summary,
    _poll_health,
    _scan_env_references,
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

class TestParseHelpers:
    """Tests for error parsing helper functions."""

    def test_parse_compile_error_with_line(self):
        stderr = (
            '  File "/tmp/work/serving/foo.py", line 10\n'
            "    x = (\n"
            "        ^\n"
            "SyntaxError: unexpected EOF while parsing"
        )
        result = _parse_compile_error(stderr, "serving/foo.py", "/tmp/work")
        assert "serving/foo.py:10" in result
        assert "SyntaxError" in result

    def test_parse_compile_error_fallback(self):
        result = _parse_compile_error("something weird", "app.py", "/tmp/work")
        assert result == "app.py: something weird"

    def test_parse_import_error(self):
        stderr = (
            "Traceback (most recent call last):\n"
            '  File "<string>", line 1, in <module>\n'
            "ModuleNotFoundError: No module named 'missing'"
        )
        result = _parse_import_error(stderr, "serving")
        assert result == "import serving: ModuleNotFoundError: No module named 'missing'"

    def test_extract_top_level_modules(self):
        files = [
            "serving/api/compute.py",
            "serving/services/quality_gate_service.py",
            "marketplace/api.py",
            "app.py",  # standalone script - skipped
            "tests/test_foo.py",  # test dir - skipped
        ]
        modules = _extract_top_level_modules(files)
        assert modules == ["marketplace", "serving"]

    def test_extract_top_level_modules_empty(self):
        assert _extract_top_level_modules([]) == []

    def test_extract_top_level_modules_only_scripts(self):
        assert _extract_top_level_modules(["app.py", "setup.py"]) == []


class TestSyntaxCheck:
    @pytest.mark.asyncio
    async def test_no_python_files_skipped(self, service):
        result = await service._run_syntax_check(Path("/tmp"), ["readme.md"])
        assert result.status == GateStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_valid_files_and_imports_pass(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            with patch.object(Path, "exists", return_value=True):
                result = await service._run_syntax_check(
                    Path("/tmp/work"), ["serving/api/compute.py"]
                )

        assert result.status == GateStatus.PASSED
        assert "compiled" in result.message
        assert "imported" in result.message

    @pytest.mark.asyncio
    async def test_syntax_error_detected_with_line_info(self, service):
        compile_result = MagicMock()
        compile_result.returncode = 1
        compile_result.stderr = (
            '  File "/tmp/work/serving/foo.py", line 5\n'
            "SyntaxError: invalid syntax"
        )
        import_result = MagicMock()
        import_result.returncode = 0

        call_count = [0]

        async def mock_to_thread(fn, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return compile_result
            return import_result

        with patch("services.quality_gate_service.asyncio.to_thread", side_effect=mock_to_thread):
            with patch.object(Path, "exists", return_value=True):
                result = await service._run_syntax_check(
                    Path("/tmp/work"), ["serving/foo.py"]
                )

        assert result.status == GateStatus.FAILED
        assert any("serving/foo.py:5" in d for d in result.details)
        assert any("SyntaxError" in d for d in result.details)

    @pytest.mark.asyncio
    async def test_import_error_detected(self, service):
        compile_result = MagicMock()
        compile_result.returncode = 0
        import_result = MagicMock()
        import_result.returncode = 1
        import_result.stderr = "ModuleNotFoundError: No module named 'missing'"

        call_count = [0]

        async def mock_to_thread(fn, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return compile_result
            return import_result

        with patch("services.quality_gate_service.asyncio.to_thread", side_effect=mock_to_thread):
            with patch.object(Path, "exists", return_value=True):
                result = await service._run_syntax_check(
                    Path("/tmp/work"), ["serving/api/compute.py"]
                )

        assert result.status == GateStatus.FAILED
        assert any("import serving" in d for d in result.details)
        assert any("ModuleNotFoundError" in d for d in result.details)

    @pytest.mark.asyncio
    async def test_deleted_files_skipped(self, service):
        """Deleted files (exist in diff but not on disk) are skipped without errors."""
        with patch.object(Path, "exists", return_value=False):
            result = await service._run_syntax_check(Path("/tmp/work"), ["deleted.py"])

        # Standalone script - no package to import, file deleted - no compile
        assert result.status == GateStatus.PASSED

    @pytest.mark.asyncio
    async def test_import_timeout_reported(self, service):
        compile_result = MagicMock()
        compile_result.returncode = 0

        call_count = [0]

        async def mock_to_thread(fn, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return compile_result
            raise subprocess.TimeoutExpired(cmd="python", timeout=30)

        with patch("services.quality_gate_service.asyncio.to_thread", side_effect=mock_to_thread):
            with patch.object(Path, "exists", return_value=True):
                result = await service._run_syntax_check(
                    Path("/tmp/work"), ["serving/app.py"]
                )

        assert result.status == GateStatus.FAILED
        assert any("timed out" in d for d in result.details)


class TestDetectTestCommand:
    def test_project_script(self):
        with patch.object(Path, "exists", return_value=True):
            cmd = _detect_test_command(Path("/tmp/work"))
        assert cmd[0] == "bash"
        assert "run_unit_tests.sh" in cmd[1]

    def test_npm_test(self):
        def mock_exists(self_path):
            return "package.json" in str(self_path)

        with patch.object(Path, "exists", mock_exists):
            with patch.object(Path, "read_text", return_value='{"scripts":{"test":"jest"}}'):
                cmd = _detect_test_command(Path("/tmp/work"))
        assert cmd[0] == "npm"

    def test_fallback_pytest(self):
        with patch.object(Path, "exists", return_value=False):
            cmd = _detect_test_command(Path("/tmp/work"))
        assert cmd == ["python", "-m", "pytest", "--tb=short", "-q"]


class TestParseTestSummary:
    def test_pytest_passed(self):
        output = "====== 10 passed in 1.23s ======"
        assert "10 passed" in _parse_test_summary(output)

    def test_pytest_mixed(self):
        output = "====== 2 failed, 8 passed in 2.50s ======"
        result = _parse_test_summary(output)
        assert "failed" in result

    def test_jest_output(self):
        output = "Tests: 1 failed, 5 passed, 6 total"
        result = _parse_test_summary(output)
        assert "total" in result

    def test_unparseable(self):
        assert _parse_test_summary("some random output") == ""


class TestTestGate:
    @pytest.mark.asyncio
    async def test_tests_pass_with_summary(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "collecting ...\n====== 5 passed in 1.23s ======"
        mock_result.stderr = ""

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            result = await service._run_test_gate(Path("/tmp/work"), timeout=60)

        assert result.status == GateStatus.PASSED
        assert "5 passed" in result.message

    @pytest.mark.asyncio
    async def test_tests_fail_with_summary(self, service):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "FAILED test_foo.py\n====== 2 failed, 3 passed in 1.00s ======"
        mock_result.stderr = ""

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            result = await service._run_test_gate(Path("/tmp/work"), timeout=60)

        assert result.status == GateStatus.FAILED
        assert "failed" in result.message

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self, service):
        with patch(
            "services.quality_gate_service.asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=60),
        ):
            result = await service._run_test_gate(Path("/tmp/work"), timeout=60)

        assert result.status == GateStatus.ERROR
        assert "timed out" in result.message


class TestDetectStartupCommand:
    def test_custom_command(self):
        cmd = _detect_startup_command(Path("/tmp"), custom_command="uvicorn app:app --port 9000")
        assert cmd == ["uvicorn", "app:app", "--port", "9000"]

    def test_app_py_detected(self):
        with patch.object(Path, "exists", return_value=True):
            cmd = _detect_startup_command(Path("/tmp"))
        assert cmd == ["python", "app.py"]

    def test_npm_start(self):
        def mock_exists(self_path):
            return "package.json" in str(self_path)

        with patch.object(Path, "exists", mock_exists):
            with patch.object(Path, "read_text", return_value='{"scripts":{"start":"node server.js"}}'):
                cmd = _detect_startup_command(Path("/tmp"))
        assert cmd == ["npm", "start"]

    def test_fallback(self):
        with patch.object(Path, "exists", return_value=False):
            cmd = _detect_startup_command(Path("/tmp"))
        assert "import app" in " ".join(cmd)


class TestStartupSmokeTest:
    @pytest.fixture
    def gate_config(self):
        config = MagicMock()
        config.startup_command = None
        config.startup_health_url = None
        config.startup_timeout_seconds = 5
        return config

    @pytest.mark.asyncio
    async def test_app_starts_cleanly(self, service, gate_config):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            with patch("services.quality_gate_service._detect_startup_command", return_value=["python", "app.py"]):
                result = await service._run_startup_smoke_test(Path("/tmp/work"), gate_config)

        assert result.status == GateStatus.PASSED

    @pytest.mark.asyncio
    async def test_app_crashes_on_start(self, service, gate_config):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ImportError: No module named 'missing'"

        with patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_result):
            with patch("services.quality_gate_service._detect_startup_command", return_value=["python", "app.py"]):
                result = await service._run_startup_smoke_test(Path("/tmp/work"), gate_config)

        assert result.status == GateStatus.FAILED
        assert "exited with code 1" in result.message

    @pytest.mark.asyncio
    async def test_app_timeout_means_stable(self, service, gate_config):
        """If the app runs for the full timeout without crashing, that's a pass."""
        with patch(
            "services.quality_gate_service.asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired(cmd="python", timeout=5),
        ):
            with patch("services.quality_gate_service._detect_startup_command", return_value=["python", "app.py"]):
                result = await service._run_startup_smoke_test(Path("/tmp/work"), gate_config)

        assert result.status == GateStatus.PASSED
        assert "stayed alive" in result.message

    @pytest.mark.asyncio
    async def test_health_check_passes(self, service, gate_config):
        gate_config.startup_health_url = "http://localhost:8002/health"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_proc),
            patch("services.quality_gate_service._poll_health", return_value=True),
            patch("services.quality_gate_service._detect_startup_command", return_value=["python", "app.py"]),
        ):
            result = await service._run_startup_smoke_test(Path("/tmp/work"), gate_config)

        assert result.status == GateStatus.PASSED
        assert "health check passed" in result.message

    @pytest.mark.asyncio
    async def test_health_check_fails(self, service, gate_config):
        gate_config.startup_health_url = "http://localhost:8002/health"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stderr.read.return_value = b"Connection refused\n"

        with (
            patch("services.quality_gate_service.asyncio.to_thread", return_value=mock_proc),
            patch("services.quality_gate_service._poll_health", return_value=False),
            patch("services.quality_gate_service._detect_startup_command", return_value=["python", "app.py"]),
        ):
            result = await service._run_startup_smoke_test(Path("/tmp/work"), gate_config)

        assert result.status == GateStatus.FAILED
        assert "failed health check" in result.message


class TestScanEnvReferences:
    def test_python_getenv(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value='x = os.getenv("DB_URL")'),
        ):
            refs = _scan_env_references(Path("/tmp"), ["app.py"])
        assert ("DB_URL", "app.py") in refs

    def test_python_environ_bracket(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value='x = os.environ["API_KEY"]'),
        ):
            refs = _scan_env_references(Path("/tmp"), ["app.py"])
        assert ("API_KEY", "app.py") in refs

    def test_js_process_env(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="const url = process.env.API_URL;"),
        ):
            refs = _scan_env_references(Path("/tmp"), ["app.js"])
        assert ("API_URL", "app.js") in refs

    def test_js_builtin_skipped(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="const env = process.env.NODE_ENV;"),
        ):
            refs = _scan_env_references(Path("/tmp"), ["app.js"])
        assert len(refs) == 0

    def test_no_refs(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="x = 1"),
        ):
            refs = _scan_env_references(Path("/tmp"), ["app.py"])
        assert refs == []


class TestCollectKnownConfigVars:
    def test_env_template(self):
        def mock_exists(self_path):
            return ".env.example" in str(self_path)

        with (
            patch.object(Path, "exists", mock_exists),
            patch.object(Path, "read_text", return_value="DB_URL=postgres://\nAPI_KEY=secret\n"),
        ):
            known = _collect_known_config_vars(Path("/tmp"))
        assert "DB_URL" in known
        assert "API_KEY" in known

    def test_config_py_fields(self):
        config_content = '''
class MyConfig(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8002)
'''

        def mock_exists(self_path):
            return "config.py" in str(self_path)

        with (
            patch.object(Path, "exists", mock_exists),
            patch.object(Path, "read_text", return_value=config_content),
        ):
            known = _collect_known_config_vars(Path("/tmp"))
        assert "HOST" in known
        assert "PORT" in known


class TestConfigCompletenessCheck:
    @pytest.mark.asyncio
    async def test_no_env_refs_skipped(self, service):
        with patch("services.quality_gate_service._scan_env_references", return_value=[]):
            result = await service._run_config_completeness_check(
                Path("/tmp/work"), ["app.py"]
            )
        assert result.status == GateStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_missing_env_var_fails(self, service):
        with (
            patch("services.quality_gate_service._scan_env_references",
                  return_value=[("DATABASE_URL", "app.py")]),
            patch("services.quality_gate_service._collect_known_config_vars",
                  return_value=set()),
        ):
            result = await service._run_config_completeness_check(
                Path("/tmp/work"), ["app.py"]
            )
        assert result.status == GateStatus.FAILED
        assert "DATABASE_URL" in str(result.details)
        assert "add to .env.example" in str(result.details)

    @pytest.mark.asyncio
    async def test_present_env_var_passes(self, service):
        with (
            patch("services.quality_gate_service._scan_env_references",
                  return_value=[("DATABASE_URL", "app.py")]),
            patch("services.quality_gate_service._collect_known_config_vars",
                  return_value={"DATABASE_URL"}),
        ):
            result = await service._run_config_completeness_check(
                Path("/tmp/work"), ["app.py"]
            )
        assert result.status == GateStatus.PASSED

    @pytest.mark.asyncio
    async def test_js_env_var_missing(self, service):
        with (
            patch("services.quality_gate_service._scan_env_references",
                  return_value=[("REACT_APP_API", "src/config.js")]),
            patch("services.quality_gate_service._collect_known_config_vars",
                  return_value=set()),
        ):
            result = await service._run_config_completeness_check(
                Path("/tmp/work"), ["src/config.js"]
            )
        assert result.status == GateStatus.FAILED
        assert "REACT_APP_API" in str(result.details)
