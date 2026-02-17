"""Unit tests for claudevn_submit_challenge MCP tool.

Tests cover:
- Successful challenge creation and feedback signal routing
- Challenge type validation (ChallengeType enum)
- Task not found error handling
- Service unavailable error handling
- Challenge severity mapping
- Feedback aggregation integration
- Decision trace recording
- Challenge with all optional fields
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.tools.challenge import report_challenge, SEVERITY_MAP, VALID_CHALLENGE_TYPES
from mcp.models import ReportChallengeInput, ChallengeResponse, MCPError
from models.feedback import ChallengeType, FeedbackSeverity


class TestSubmitChallengeTool:
    """Test cases for the submit_challenge tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_work = AsyncMock()
        return service

    @pytest.fixture
    def mock_work(self):
        """Create a mock work item."""
        work = MagicMock()
        work.work_id = "work-200"
        work.project_id = "project-001"
        work.issue_id = "issue-200"
        work.assigned_to = "compute-002"
        return work

    @pytest.fixture
    def mock_feedback_service(self):
        """Create a mock feedback aggregation service."""
        service = MagicMock()
        service.process_signal = AsyncMock(return_value=(MagicMock(), None))
        return service

    @pytest.fixture
    def basic_input(self):
        """Create basic challenge input."""
        return ReportChallengeInput(
            task_id="work-200",
            worker_id="compute-002",
            challenge_type="task_infeasibility",
            description="Task is not achievable with current API limitations",
        )

    @pytest.fixture
    def full_input(self):
        """Create challenge input with all optional fields."""
        return ReportChallengeInput(
            task_id="work-200",
            worker_id="compute-002",
            challenge_type="scope_discovery",
            description="Area needs significantly more work than anticipated",
            severity="critical",
            impact_assessment="Blocks 3 downstream tasks",
            suggested_approach="Split into multiple smaller tasks",
            affected_tasks=["work-201", "work-202"],
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_successful_challenge(
        self, mock_get_wms, mock_get_feedback, mock_trace,
        mock_work_map_service, mock_work, mock_feedback_service, basic_input
    ):
        """Test successful challenge creation."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_get_feedback.return_value = mock_feedback_service

        result, error = await report_challenge(basic_input)

        assert error is None
        assert result is not None
        assert isinstance(result, ChallengeResponse)
        assert result.acknowledged is True
        assert result.status == "challenge_recorded"
        assert result.signal_id.startswith("sig_")

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_profile_updated_flag(
        self, mock_get_wms, mock_get_feedback, mock_trace,
        mock_work_map_service, mock_work, basic_input
    ):
        """Test profile_updated flag reflects feedback service result."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work

        mock_feedback = MagicMock()
        mock_trace_entry = MagicMock()  # Non-None trace means profile was updated
        mock_feedback.process_signal = AsyncMock(return_value=(mock_trace_entry, None))
        mock_get_feedback.return_value = mock_feedback

        result, error = await report_challenge(basic_input)

        assert result.profile_updated is True
        assert result.pattern_detected is False

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_pattern_detected_flag(
        self, mock_get_wms, mock_get_feedback, mock_trace,
        mock_work_map_service, mock_work, basic_input
    ):
        """Test pattern_detected flag when pattern is returned."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work

        mock_feedback = MagicMock()
        mock_pattern = MagicMock()
        mock_feedback.process_signal = AsyncMock(return_value=(MagicMock(), mock_pattern))
        mock_get_feedback.return_value = mock_feedback

        result, error = await report_challenge(basic_input)

        assert result.pattern_detected is True

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_task_not_found(self, mock_get_wms, mock_work_map_service, basic_input):
        """Test error when task doesn't exist."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = None

        result, error = await report_challenge(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "TASK_NOT_FOUND"
        assert "work-200" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_service_unavailable(self, mock_get_wms, basic_input):
        """Test error when work map service is unavailable."""
        mock_get_wms.side_effect = RuntimeError("Service not initialized")

        result, error = await report_challenge(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_feedback_service_unavailable_still_succeeds(
        self, mock_get_wms, mock_get_feedback, mock_trace,
        mock_work_map_service, mock_work, basic_input
    ):
        """Challenge succeeds even if feedback service is not available."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_get_feedback.side_effect = RuntimeError("Not initialized")

        result, error = await report_challenge(basic_input)

        assert error is None
        assert result is not None
        assert result.acknowledged is True
        assert result.profile_updated is False

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_full_input_all_fields(
        self, mock_get_wms, mock_get_feedback, mock_trace,
        mock_work_map_service, mock_work, mock_feedback_service, full_input
    ):
        """Test challenge with all optional fields populated."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_get_feedback.return_value = mock_feedback_service

        result, error = await report_challenge(full_input)

        assert error is None
        assert result is not None
        assert result.acknowledged is True

        # Verify signal was passed to feedback service
        mock_feedback_service.process_signal.assert_called_once()
        signal = mock_feedback_service.process_signal.call_args[0][0]
        assert signal.data["challenge_type"] == "scope_discovery"
        assert signal.data["impact_assessment"] == "Blocks 3 downstream tasks"
        assert signal.data["suggested_approach"] == "Split into multiple smaller tasks"
        assert signal.data["affected_tasks"] == ["work-201", "work-202"]

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_critical_severity_mapping(
        self, mock_get_wms, mock_get_feedback, mock_trace,
        mock_work_map_service, mock_work, mock_feedback_service
    ):
        """Test that critical severity is correctly mapped."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_get_feedback.return_value = mock_feedback_service

        input_data = ReportChallengeInput(
            task_id="work-200",
            worker_id="compute-002",
            challenge_type="task_infeasibility",
            description="Impossible task",
            severity="critical",
        )

        await report_challenge(input_data)

        signal = mock_feedback_service.process_signal.call_args[0][0]
        assert signal.severity == FeedbackSeverity.CRITICAL

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_internal_error(
        self, mock_get_wms, mock_get_feedback,
        mock_work_map_service, mock_work, basic_input
    ):
        """Test error handling for unexpected exceptions."""
        mock_get_wms.return_value = mock_work_map_service
        mock_work_map_service.get_work.side_effect = Exception("Database error")

        result, error = await report_challenge(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Database error" in error.message


class TestChallengeTypeValidation:
    """Test challenge type validation against ChallengeType enum."""

    @pytest.mark.asyncio
    async def test_invalid_challenge_type_rejected(self):
        """Invalid challenge type returns error without hitting services."""
        input_data = ReportChallengeInput(
            task_id="work-200",
            worker_id="compute-002",
            challenge_type="invalid_type",
            description="test",
        )

        result, error = await report_challenge(input_data)

        assert result is None
        assert error is not None
        assert error.code == "INVALID_CHALLENGE_TYPE"
        assert "invalid_type" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_task_infeasibility_accepted(
        self, mock_get_wms, mock_get_feedback, mock_trace
    ):
        """task_infeasibility is a valid challenge type."""
        mock_service = MagicMock()
        mock_service.get_work = AsyncMock(return_value=MagicMock(project_id="p1", issue_id="i1"))
        mock_get_wms.return_value = mock_service
        mock_fb = MagicMock()
        mock_fb.process_signal = AsyncMock(return_value=(None, None))
        mock_get_feedback.return_value = mock_fb

        input_data = ReportChallengeInput(
            task_id="work-200", worker_id="w1",
            challenge_type="task_infeasibility", description="test",
        )
        result, error = await report_challenge(input_data)
        assert error is None
        assert result.acknowledged is True

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_scope_discovery_accepted(
        self, mock_get_wms, mock_get_feedback, mock_trace
    ):
        """scope_discovery is a valid challenge type."""
        mock_service = MagicMock()
        mock_service.get_work = AsyncMock(return_value=MagicMock(project_id="p1", issue_id="i1"))
        mock_get_wms.return_value = mock_service
        mock_fb = MagicMock()
        mock_fb.process_signal = AsyncMock(return_value=(None, None))
        mock_get_feedback.return_value = mock_fb

        input_data = ReportChallengeInput(
            task_id="work-200", worker_id="w1",
            challenge_type="scope_discovery", description="test",
        )
        result, error = await report_challenge(input_data)
        assert error is None
        assert result.acknowledged is True

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_dependency_correction_accepted(
        self, mock_get_wms, mock_get_feedback, mock_trace
    ):
        """dependency_correction is a valid challenge type."""
        mock_service = MagicMock()
        mock_service.get_work = AsyncMock(return_value=MagicMock(project_id="p1", issue_id="i1"))
        mock_get_wms.return_value = mock_service
        mock_fb = MagicMock()
        mock_fb.process_signal = AsyncMock(return_value=(None, None))
        mock_get_feedback.return_value = mock_fb

        input_data = ReportChallengeInput(
            task_id="work-200", worker_id="w1",
            challenge_type="dependency_correction", description="test",
        )
        result, error = await report_challenge(input_data)
        assert error is None
        assert result.acknowledged is True

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_quality_concern_accepted(
        self, mock_get_wms, mock_get_feedback, mock_trace
    ):
        """quality_concern is a valid challenge type."""
        mock_service = MagicMock()
        mock_service.get_work = AsyncMock(return_value=MagicMock(project_id="p1", issue_id="i1"))
        mock_get_wms.return_value = mock_service
        mock_fb = MagicMock()
        mock_fb.process_signal = AsyncMock(return_value=(None, None))
        mock_get_feedback.return_value = mock_fb

        input_data = ReportChallengeInput(
            task_id="work-200", worker_id="w1",
            challenge_type="quality_concern", description="test",
        )
        result, error = await report_challenge(input_data)
        assert error is None
        assert result.acknowledged is True

    def test_valid_challenge_types_match_enum(self):
        """VALID_CHALLENGE_TYPES set matches ChallengeType enum values."""
        enum_values = {t.value for t in ChallengeType}
        assert VALID_CHALLENGE_TYPES == enum_values


class TestDecisionTraceRecording:
    """Test decision trace recording for challenge processing."""

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_decision_trace_recorded_on_success(
        self, mock_get_wms, mock_get_feedback, mock_record_trace,
        mock_work_map_service=None, mock_work=None,
    ):
        """Decision trace is recorded after successful challenge."""
        wms = MagicMock()
        work = MagicMock(project_id="project-001", issue_id="issue-200")
        wms.get_work = AsyncMock(return_value=work)
        mock_get_wms.return_value = wms

        fb = MagicMock()
        fb.process_signal = AsyncMock(return_value=(MagicMock(), None))
        mock_get_feedback.return_value = fb

        input_data = ReportChallengeInput(
            task_id="work-200", worker_id="compute-002",
            challenge_type="task_infeasibility",
            description="Not achievable",
        )

        result, error = await report_challenge(input_data)

        assert error is None
        mock_record_trace.assert_called_once()
        call_kwargs = mock_record_trace.call_args[1]
        assert call_kwargs["project_id"] == "project-001"
        assert call_kwargs["profile_updated"] is True

    @pytest.mark.asyncio
    @patch("mcp.tools.challenge._record_challenge_trace", new_callable=AsyncMock)
    @patch("mcp.tools.challenge.get_feedback_aggregation_service")
    @patch("mcp.tools.challenge.get_work_map_service")
    async def test_decision_trace_with_affected_tasks(
        self, mock_get_wms, mock_get_feedback, mock_record_trace,
    ):
        """Decision trace includes affected_tasks in the signal."""
        wms = MagicMock()
        work = MagicMock(project_id="project-001", issue_id="issue-200")
        wms.get_work = AsyncMock(return_value=work)
        mock_get_wms.return_value = wms

        fb = MagicMock()
        fb.process_signal = AsyncMock(return_value=(None, None))
        mock_get_feedback.return_value = fb

        input_data = ReportChallengeInput(
            task_id="work-200", worker_id="compute-002",
            challenge_type="scope_discovery",
            description="More work needed",
            affected_tasks=["work-201", "work-202"],
        )

        await report_challenge(input_data)

        mock_record_trace.assert_called_once()
        call_kwargs = mock_record_trace.call_args[1]
        assert call_kwargs["input"].affected_tasks == ["work-201", "work-202"]


class TestSeverityMapping:
    """Test severity string to FeedbackSeverity mapping."""

    def test_all_severity_levels_mapped(self):
        """All expected severity levels are in the map."""
        assert "low" in SEVERITY_MAP
        assert "medium" in SEVERITY_MAP
        assert "high" in SEVERITY_MAP
        assert "critical" in SEVERITY_MAP

    def test_severity_values(self):
        assert SEVERITY_MAP["low"] == FeedbackSeverity.LOW
        assert SEVERITY_MAP["medium"] == FeedbackSeverity.MEDIUM
        assert SEVERITY_MAP["high"] == FeedbackSeverity.HIGH
        assert SEVERITY_MAP["critical"] == FeedbackSeverity.CRITICAL


class TestChallengeTypeEnum:
    """Test ChallengeType enum values."""

    def test_task_infeasibility(self):
        assert ChallengeType.TASK_INFEASIBILITY.value == "task_infeasibility"

    def test_scope_discovery(self):
        assert ChallengeType.SCOPE_DISCOVERY.value == "scope_discovery"

    def test_dependency_correction(self):
        assert ChallengeType.DEPENDENCY_CORRECTION.value == "dependency_correction"

    def test_quality_concern(self):
        assert ChallengeType.QUALITY_CONCERN.value == "quality_concern"

    def test_four_types_total(self):
        assert len(ChallengeType) == 4


class TestReportChallengeInputModel:
    """Test cases for the ReportChallengeInput model."""

    def test_required_fields(self):
        input_data = ReportChallengeInput(
            task_id="work-200",
            worker_id="compute-002",
            challenge_type="task_infeasibility",
            description="Not achievable",
        )
        assert input_data.task_id == "work-200"
        assert input_data.severity == "medium"  # default
        assert input_data.impact_assessment is None
        assert input_data.suggested_approach is None
        assert input_data.affected_tasks is None

    def test_all_fields(self):
        input_data = ReportChallengeInput(
            task_id="work-200",
            worker_id="compute-002",
            challenge_type="dependency_correction",
            description="Missing API",
            severity="high",
            impact_assessment="Critical path affected",
            suggested_approach="Implement stub first",
            affected_tasks=["work-201"],
        )
        assert input_data.severity == "high"
        assert input_data.impact_assessment == "Critical path affected"
        assert input_data.affected_tasks == ["work-201"]


class TestChallengeResponseModel:
    """Test cases for the ChallengeResponse model."""

    def test_model_creation(self):
        response = ChallengeResponse(
            acknowledged=True,
            signal_id="sig_001",
            profile_updated=True,
            pattern_detected=False,
            status="challenge_recorded",
        )
        assert response.acknowledged is True
        assert response.signal_id == "sig_001"
        assert response.profile_updated is True
        assert response.pattern_detected is False

    def test_default_flags(self):
        response = ChallengeResponse(
            acknowledged=True,
            signal_id="sig_002",
            status="challenge_recorded",
        )
        assert response.profile_updated is False
        assert response.pattern_detected is False
