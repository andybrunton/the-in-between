"""Rig build context passed to every behaviour builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from in_between.core.naming import sanitize_name


@dataclass
class RigContext:
    behaviour_id: str
    start: str
    end: str
    rig_label: str = "rig"
    local_parent: Optional[str] = None
    world_parent: Optional[str] = None
    joint_parent: Optional[str] = None
    num_joints: int = 8
    build_joints: bool = True
    drive_mode: str = "distance"
    reference: Optional[str] = None
    bulge_twist: Optional[str] = None

    @property
    def base_name(self) -> str:
        """Rig namespace root from user label."""
        return sanitize_name(self.rig_label) or "rig"

    def node(self, suffix: str) -> str:
        """Logical node name before uniqueness pass — builders call unique in parents."""
        return f"{self.base_name}_{suffix}"


@dataclass
class RigResult:
    root: str
    settings: Optional[str] = None
    curve: Optional[str] = None
    joint_chain: List[str] = field(default_factory=list)
    local_root: Optional[str] = None
    world_root: Optional[str] = None
    joint_root: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)
