"""Unit tests for claudevn_signal_blocker MCP tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

# Add serving to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.tools.blocker import signal_blocker, BLOCKER_TYPE_MAP
from mcp.models import SignalBlockerInput, BlockerResponse, MCPError
from mcp.models import BlockerType as MCPBlockerType
from models.work_map import BlockerType as WorkBlockerType, Blocker


class TestSignalBlockerTool:
    """Test cases for the signal_blocker tool function."""

    @pytest.fixture
    def mock_work_map_service(self):
        """Create a mock work map service."""
        service = MagicMock()
        service.get_work = AsyncMock()
        service.add_blocker = AsyncMock()
        return service

    @pytest.fixture
    def mock_work(self):
        """Create a mock work item."""
        work = MagicMock()
        work.work_id = "work-123"
        work.title = "Test Work"
        return work

    @pytest.fixture
    def mock_blocker(self):
        """Create a mock blocker."""
        return MagicMock(blocker_id="blocker-001")

    @pytest.fixture
    def basic_input(self):
        """Create basic blocker input."""
        return SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.TECHNICAL,
            description="Cannot compile TypeScript"
        )

    @pytest.fixture
    def dependency_input(self):
        """Create dependency blocker input."""
        return SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.DEPENDENCY,
            description="Waiting for API implementation",
            blocking_task_id="work-100"
        )

    @pytest.fixture
    def input_with_resolution(self):
        """Create blocker input with suggested resolution."""
        return SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.CLARIFICATION,
            description="Unclear requirements for auth flow",
            suggested_resolution="Need PM to clarify OAuth vs SAML"
        )

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_successful_blocker_creation(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker, basic_input
    ):
        """Test successful blocker creation."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        result, error = await signal_blocker(basic_input)

        assert error is None
        assert result is not None
        assert isinstance(result, BlockerResponse)
        assert result.acknowledged is True
        assert result.blocker_id == "blocker-001"
        assert result.status == "blocked"

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_task_not_found(self, mock_get_service, mock_work_map_service, basic_input):
        """Test error when task doesn't exist."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = None

        result, error = await signal_blocker(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "TASK_NOT_FOUND"
        assert "work-123" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_blocker_add_failed(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test error when blocker creation fails."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = None

        result, error = await signal_blocker(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "BLOCKER_ADD_FAILED"

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_dependency_blocker_with_resolution_task(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker, dependency_input
    ):
        """Test dependency blocker returns resolution_task_id."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        result, error = await signal_blocker(dependency_input)

        assert error is None
        assert result is not None
        assert result.resolution_task_id == "work-100"

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_non_dependency_blocker_no_resolution_task(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker, basic_input
    ):
        """Test non-dependency blocker has no resolution_task_id."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        result, error = await signal_blocker(basic_input)

        assert error is None
        assert result is not None
        assert result.resolution_task_id is None

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_suggested_resolution_appended(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker, input_with_resolution
    ):
        """Test that suggested resolution is appended to description."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        await signal_blocker(input_with_resolution)

        call_kwargs = mock_work_map_service.add_blocker.call_args.kwargs
        assert "Unclear requirements for auth flow" in call_kwargs["description"]
        assert "Need PM to clarify OAuth vs SAML" in call_kwargs["description"]
        assert "Suggested resolution:" in call_kwargs["description"]

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_service_unavailable(self, mock_get_service, basic_input):
        """Test error when work map service is unavailable."""
        mock_get_service.side_effect = RuntimeError("Service not initialized")

        result, error = await signal_blocker(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "SERVICE_UNAVAILABLE"
        assert "not initialized" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_internal_error(
        self, mock_get_service, mock_work_map_service, mock_work, basic_input
    ):
        """Test error handling for unexpected exceptions."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.side_effect = Exception("Database error")

        result, error = await signal_blocker(basic_input)

        assert result is None
        assert error is not None
        assert error.code == "INTERNAL_ERROR"
        assert "Database error" in error.message

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_blocker_type_mapping_dependency(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker
    ):
        """Test DEPENDENCY blocker type mapping."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.DEPENDENCY,
            description="Waiting for task"
        )

        await signal_blocker(input_data)

        call_kwargs = mock_work_map_service.add_blocker.call_args.kwargs
        assert call_kwargs["blocker_type"] == WorkBlockerType.DEPENDENCY

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_blocker_type_mapping_clarification(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker
    ):
        """Test CLARIFICATION blocker type mapping."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.CLARIFICATION,
            description="Need clarification"
        )

        await signal_blocker(input_data)

        call_kwargs = mock_work_map_service.add_blocker.call_args.kwargs
        assert call_kwargs["blocker_type"] == WorkBlockerType.CLARIFICATION

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_blocker_type_mapping_access(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker
    ):
        """Test ACCESS blocker type maps to RESOURCE."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.ACCESS,
            description="No access"
        )

        await signal_blocker(input_data)

        call_kwargs = mock_work_map_service.add_blocker.call_args.kwargs
        assert call_kwargs["blocker_type"] == WorkBlockerType.RESOURCE

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_blocker_type_mapping_technical(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker
    ):
        """Test TECHNICAL blocker type mapping."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.TECHNICAL,
            description="Technical issue"
        )

        await signal_blocker(input_data)

        call_kwargs = mock_work_map_service.add_blocker.call_args.kwargs
        assert call_kwargs["blocker_type"] == WorkBlockerType.TECHNICAL

    @pytest.mark.asyncio
    @patch("mcp.tools.blocker.get_work_map_service")
    async def test_blocker_type_mapping_other(
        self, mock_get_service, mock_work_map_service, mock_work, mock_blocker
    ):
        """Test OTHER blocker type maps to EXTERNAL."""
        mock_get_service.return_value = mock_work_map_service
        mock_work_map_service.get_work.return_value = mock_work
        mock_work_map_service.add_blocker.return_value = mock_blocker

        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.OTHER,
            description="Other issue"
        )

        await signal_blocker(input_data)

        call_kwargs = mock_work_map_service.add_blocker.call_args.kwargs
        assert call_kwargs["blocker_type"] == WorkBlockerType.EXTERNAL


class TestBlockerTypeMapping:
    """Test cases for blocker type mapping."""

    def test_all_mcp_types_mapped(self):
        """Test that all MCP blocker types are mapped."""
        for mcp_type in MCPBlockerType:
            assert mcp_type in BLOCKER_TYPE_MAP


class TestSignalBlockerInputModel:
    """Test cases for the SignalBlockerInput model."""

    def test_required_fields(self):
        """Test that required fields are enforced."""
        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.TECHNICAL,
            description="Test blocker"
        )

        assert input_data.task_id == "work-123"
        assert input_data.blocker_type == MCPBlockerType.TECHNICAL
        assert input_data.description == "Test blocker"
        assert input_data.suggested_resolution is None
        assert input_data.blocking_task_id is None

    def test_optional_fields(self):
        """Test optional fields."""
        input_data = SignalBlockerInput(
            task_id="work-123",
            blocker_type=MCPBlockerType.DEPENDENCY,
            description="Waiting",
            suggested_resolution="Complete work-100",
            blocking_task_id="work-100"
        )

        assert input_data.suggested_resolution == "Complete work-100"
        assert input_data.blocking_task_id == "work-100"


class TestBlockerResponseModel:
    """Test cases for the BlockerResponse model."""

    def test_model_creation(self):
        """Test creating a blocker response."""
        response = BlockerResponse(
            acknowledged=True,
            blocker_id="blocker-001",
            resolution_task_id="work-100",
            status="blocked"
        )

        assert response.acknowledged is True
        assert response.blocker_id == "blocker-001"
        assert response.resolution_task_id == "work-100"
        assert response.status == "blocked"

    def test_no_resolution_task(self):
        """Test response without resolution task."""
        response = BlockerResponse(
            acknowledged=True,
            blocker_id="blocker-002",
            status="blocked"
        )

        assert response.resolution_task_id is None
