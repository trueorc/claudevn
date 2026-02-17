"""Tests for RegistryStorage backend."""

import json
import pytest
from pathlib import Path

from storage.registry_storage import RegistryStorage


@pytest.fixture
def tmp_storage(tmp_path):
    """Create a RegistryStorage backed by a temp directory."""
    return RegistryStorage(str(tmp_path))


class TestLoadAllInstancesCompute:
    """Test load_all_instances for compute instances."""

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_storage):
        """Returns empty dict when no compute instances are stored."""
        result = await tmp_storage.load_all_instances()
        assert result == {}

    @pytest.mark.asyncio
    async def test_loads_compute_instances(self, tmp_storage):
        """Returns dict keyed by instance_id for saved compute instances."""
        await tmp_storage.save_compute_instance("inst-001", {
            "instance_id": "inst-001",
            "name": "Instance 1",
        })
        await tmp_storage.save_compute_instance("inst-002", {
            "instance_id": "inst-002",
            "name": "Instance 2",
        })

        result = await tmp_storage.load_all_instances()

        assert len(result) == 2
        assert "inst-001" in result
        assert "inst-002" in result
        assert result["inst-001"]["name"] == "Instance 1"
        assert result["inst-002"]["name"] == "Instance 2"

    @pytest.mark.asyncio
    async def test_falls_back_to_filename_stem(self, tmp_storage):
        """Uses filename stem as key when instance_id field is missing."""
        file_path = tmp_storage._compute_path / "fallback-id.json"
        with open(file_path, "w") as f:
            json.dump({"name": "No ID field"}, f)

        result = await tmp_storage.load_all_instances()

        assert "fallback-id" in result
        assert result["fallback-id"]["name"] == "No ID field"

    @pytest.mark.asyncio
    async def test_skips_corrupt_files(self, tmp_storage):
        """Skips files with invalid JSON gracefully."""
        await tmp_storage.save_compute_instance("good", {
            "instance_id": "good",
            "name": "Good Instance",
        })
        corrupt_path = tmp_storage._compute_path / "bad.json"
        corrupt_path.write_text("{invalid json")

        result = await tmp_storage.load_all_instances()

        assert len(result) == 1
        assert "good" in result


class TestLoadAllInstancesMarketplaces:
    """Test load_all_instances for marketplace instances."""

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_storage):
        """Returns empty dict when no marketplaces are stored."""
        result = await tmp_storage.load_all_instances("marketplaces")
        assert result == {}

    @pytest.mark.asyncio
    async def test_loads_marketplace_instances(self, tmp_storage):
        """Returns dict keyed by marketplace_id for saved marketplaces."""
        await tmp_storage.save_marketplace("mkt-001", {
            "marketplace_id": "mkt-001",
            "name": "Marketplace 1",
        })
        await tmp_storage.save_marketplace("mkt-002", {
            "marketplace_id": "mkt-002",
            "name": "Marketplace 2",
        })

        result = await tmp_storage.load_all_instances("marketplaces")

        assert len(result) == 2
        assert "mkt-001" in result
        assert "mkt-002" in result
        assert result["mkt-001"]["name"] == "Marketplace 1"

    @pytest.mark.asyncio
    async def test_does_not_mix_compute_and_marketplace(self, tmp_storage):
        """Compute and marketplace instances are stored separately."""
        await tmp_storage.save_compute_instance("inst-001", {
            "instance_id": "inst-001",
        })
        await tmp_storage.save_marketplace("mkt-001", {
            "marketplace_id": "mkt-001",
        })

        compute_result = await tmp_storage.load_all_instances()
        marketplace_result = await tmp_storage.load_all_instances("marketplaces")

        assert len(compute_result) == 1
        assert "inst-001" in compute_result
        assert len(marketplace_result) == 1
        assert "mkt-001" in marketplace_result

    @pytest.mark.asyncio
    async def test_skips_corrupt_marketplace_files(self, tmp_storage):
        """Skips corrupt marketplace files gracefully."""
        await tmp_storage.save_marketplace("good", {
            "marketplace_id": "good",
            "name": "Good Marketplace",
        })
        corrupt_path = tmp_storage._marketplace_path / "bad.json"
        corrupt_path.write_text("not valid json!!!")

        result = await tmp_storage.load_all_instances("marketplaces")

        assert len(result) == 1
        assert "good" in result
