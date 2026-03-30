"""Chain analyzer — dependency chain extraction and critical path computation.

Implements Planning System Specification Phase 3:
- Extract dependency chains from the work unit DAG
- Compute critical path (longest chain)
- Identify parallel chains that can execute concurrently
"""

import logging
from typing import Dict, List, Optional, Set

from models.work_unit import WorkUnit

logger = logging.getLogger(__name__)


class DependencyChain:
    """A linear sequence of work units connected by dependencies."""

    def __init__(self, chain_id: str, unit_ids: List[str]):
        self.chain_id = chain_id
        self.unit_ids = unit_ids
        self.is_critical_path = False
        self.parallel_with: List[str] = []  # Other chain IDs

    @property
    def length(self) -> int:
        return len(self.unit_ids)

    def to_dict(self, unit_map: Dict[str, WorkUnit] = None) -> dict:
        result = {
            "chain_id": self.chain_id,
            "unit_ids": self.unit_ids,
            "length": self.length,
            "is_critical_path": self.is_critical_path,
            "parallel_with": self.parallel_with,
        }
        if unit_map:
            result["units"] = [
                {
                    "id": uid,
                    "description": unit_map[uid].description if uid in unit_map else "",
                    "complexity": unit_map[uid].estimated_complexity if uid in unit_map else "",
                }
                for uid in self.unit_ids
            ]
        return result


class ChainAnalysis:
    """Result of chain analysis on a set of work units."""

    def __init__(self):
        self.chains: List[DependencyChain] = []
        self.critical_path_id: Optional[str] = None
        self.parallel_groups: List[List[str]] = []  # Groups of chain IDs that can run concurrently
        self.max_depth: int = 0

    def to_dict(self, unit_map: Dict[str, WorkUnit] = None) -> dict:
        return {
            "chains": [c.to_dict(unit_map) for c in self.chains],
            "critical_path_id": self.critical_path_id,
            "parallel_groups": self.parallel_groups,
            "max_depth": self.max_depth,
            "total_chains": len(self.chains),
        }


class ChainAnalyzer:
    """Extracts dependency chains and computes critical path.

    A chain is a maximal sequence of units where each depends on the previous.
    Independent units (no deps, no dependents) form single-unit chains.
    Fork/join points create separate chains.
    """

    def analyze(self, units: List[WorkUnit]) -> ChainAnalysis:
        """Analyze work units and extract dependency chains.

        Args:
            units: Work units with resolved dependencies.

        Returns:
            ChainAnalysis with chains, critical path, and parallel groups.
        """
        result = ChainAnalysis()

        if not units:
            return result

        unit_map = {u.id: u for u in units}

        # Build adjacency
        deps_of: Dict[str, List[str]] = {}       # unit -> units it depends on
        dependents_of: Dict[str, List[str]] = {}  # unit -> units that depend on it
        all_ids = set(unit_map.keys())

        for u in units:
            valid_deps = [d for d in u.independence.depends_on if d in all_ids]
            deps_of[u.id] = valid_deps
            for d in valid_deps:
                dependents_of.setdefault(d, []).append(u.id)

        # Find chain roots: units with no dependencies, or with multiple dependents (fork points)
        # A chain starts at a root and follows the dependent path
        roots = [uid for uid in all_ids if not deps_of.get(uid)]

        # Extract chains using DFS from each root
        visited: Set[str] = set()
        chain_idx = 0

        for root in sorted(roots):
            chains_from_root = self._extract_chains_from(
                root, deps_of, dependents_of, visited, all_ids,
            )
            for chain_units in chains_from_root:
                chain_idx += 1
                chain = DependencyChain(
                    chain_id=f"chain-{chain_idx}",
                    unit_ids=chain_units,
                )
                result.chains.append(chain)

        # Pick up any orphaned units not yet visited (e.g., in cycles)
        for uid in all_ids - visited:
            chain_idx += 1
            result.chains.append(DependencyChain(
                chain_id=f"chain-{chain_idx}",
                unit_ids=[uid],
            ))
            visited.add(uid)

        # Compute critical path (longest chain)
        if result.chains:
            longest = max(result.chains, key=lambda c: c.length)
            longest.is_critical_path = True
            result.critical_path_id = longest.chain_id

        # Compute max depth from the DAG
        result.max_depth = self._compute_max_depth(deps_of)

        # Identify parallel groups
        result.parallel_groups = self._find_parallel_groups(result.chains, deps_of, unit_map)

        # Set parallel_with on each chain
        for group in result.parallel_groups:
            for cid in group:
                chain = next((c for c in result.chains if c.chain_id == cid), None)
                if chain:
                    chain.parallel_with = [g for g in group if g != cid]

        return result

    def _extract_chains_from(
        self,
        start: str,
        deps_of: Dict[str, List[str]],
        dependents_of: Dict[str, List[str]],
        visited: Set[str],
        all_ids: Set[str],
    ) -> List[List[str]]:
        """Extract chains starting from a root node.

        Follows dependents forward. At fork points (multiple dependents),
        splits into separate chains. At join points (multiple deps),
        ends the current chain.
        """
        chains = []
        current_chain = []
        stack = [start]

        while stack:
            uid = stack.pop()
            if uid in visited:
                continue
            visited.add(uid)

            # If this unit has multiple dependencies (join point) and we have a chain,
            # it might belong to a different chain. Start a new chain.
            if deps_of.get(uid) and len(deps_of[uid]) > 1 and current_chain:
                if current_chain:
                    chains.append(current_chain)
                current_chain = []

            current_chain.append(uid)

            # Follow dependents
            next_units = [d for d in dependents_of.get(uid, []) if d not in visited and d in all_ids]

            if len(next_units) == 0:
                # End of chain
                if current_chain:
                    chains.append(current_chain)
                    current_chain = []
            elif len(next_units) == 1:
                # Continue the chain
                stack.append(next_units[0])
            else:
                # Fork point — end current chain, start new chains from each dependent
                if current_chain:
                    chains.append(current_chain)
                    current_chain = []
                for dep in sorted(next_units):
                    sub_chains = self._extract_chains_from(dep, deps_of, dependents_of, visited, all_ids)
                    chains.extend(sub_chains)

        if current_chain:
            chains.append(current_chain)

        return chains

    def _compute_max_depth(self, deps_of: Dict[str, List[str]]) -> int:
        """Compute the maximum depth of the DAG."""
        memo: Dict[str, int] = {}

        def depth(uid: str) -> int:
            if uid in memo:
                return memo[uid]
            deps = deps_of.get(uid, [])
            if not deps:
                memo[uid] = 0
                return 0
            memo[uid] = 1 + max(depth(d) for d in deps if d in deps_of)
            return memo[uid]

        if not deps_of:
            return 0
        return max(depth(uid) for uid in deps_of)

    def _find_parallel_groups(
        self,
        chains: List[DependencyChain],
        deps_of: Dict[str, List[str]],
        unit_map: Dict[str, WorkUnit],
    ) -> List[List[str]]:
        """Find groups of chains that can execute in parallel.

        Two chains can run in parallel if no unit in one chain
        depends on any unit in the other chain.
        """
        if len(chains) <= 1:
            return []

        # Build chain unit sets
        chain_units: Dict[str, Set[str]] = {}
        for chain in chains:
            chain_units[chain.chain_id] = set(chain.unit_ids)

        # Build full dependency closure for each chain
        chain_all_deps: Dict[str, Set[str]] = {}
        for chain in chains:
            all_deps = set()
            for uid in chain.unit_ids:
                all_deps.update(deps_of.get(uid, []))
            chain_all_deps[chain.chain_id] = all_deps

        # Two chains are parallel if neither depends on units in the other
        parallel_groups = []
        processed = set()

        for i, c1 in enumerate(chains):
            if c1.chain_id in processed:
                continue
            group = [c1.chain_id]
            for j, c2 in enumerate(chains):
                if i == j or c2.chain_id in processed:
                    continue
                # Check if c1 and c2 are independent
                c1_deps_on_c2 = chain_all_deps[c1.chain_id] & chain_units[c2.chain_id]
                c2_deps_on_c1 = chain_all_deps[c2.chain_id] & chain_units[c1.chain_id]
                if not c1_deps_on_c2 and not c2_deps_on_c1:
                    group.append(c2.chain_id)
            if len(group) > 1:
                for cid in group:
                    processed.add(cid)
                parallel_groups.append(group)

        return parallel_groups
