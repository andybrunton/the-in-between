"""Behaviour registry and build orchestration."""

from __future__ import annotations

from typing import Callable, Dict, List

import maya.cmds as cmds

from in_between.builders.angle_push import build as build_angle_push
from in_between.builders.bounded_bow import build as build_bounded_bow
from in_between.builders.muscle_curve import build as build_muscle_curve
from in_between.builders.skin_wrinkle import build as build_skin_wrinkle
from in_between.builders.volume_3d import build as build_volume_3d
from in_between.builders.wave_billow import build as build_wave_billow
from in_between.core.context import RigContext, RigResult
from in_between.core.drive import DRIVE_ANGLE, DRIVE_DISTANCE
from in_between.core.dag_targets import (
    list_selected_targets,
    resolve_transform_for_parent,
    validate_dag_target,
)
from in_between.core.naming import sanitize_name

BUILDERS: Dict[str, Callable[[RigContext], RigResult]] = {
    "muscle_curve": build_muscle_curve,
    "volume_3d": build_volume_3d,
    "angle_push": build_angle_push,
    "wave_billow": build_wave_billow,
    "skin_wrinkle": build_skin_wrinkle,
    "bounded_bow": build_bounded_bow,
}

BEHAVIOUR_LABELS: Dict[str, str] = {
    "muscle_curve": "Muscle Curve",
    "volume_3d": "3D Volume Preservation",
    "angle_push": "Angle Push",
    "wave_billow": "Wave Billow",
    "skin_wrinkle": "Skin Wrinkle",
    "bounded_bow": "Bounded Bow",
}


def behaviour_ids() -> List[str]:
    return list(BUILDERS.keys())


def validate_transform(name: str, label: str) -> str:
    return validate_dag_target(name, label)


def build_rig(ctx: RigContext) -> RigResult:
    ctx.start = validate_transform(ctx.start, "Start")
    ctx.end = validate_transform(ctx.end, "End")
    if ctx.start == ctx.end:
        raise ValueError("Start and end must be different transforms.")
    if ctx.drive_mode not in (DRIVE_DISTANCE, DRIVE_ANGLE):
        raise ValueError(f"Unknown drive mode: {ctx.drive_mode}")
    if ctx.reference:
        ctx.reference = validate_transform(ctx.reference, "Reference")
        if ctx.reference in (ctx.start, ctx.end):
            raise ValueError("Reference must be different from start and end.")
    if ctx.bulge_twist:
        resolved = resolve_transform_for_parent(ctx.bulge_twist)
        if not resolved:
            raise ValueError("Bulge guide must be a transform.")
        ctx.bulge_twist = resolved

    for label, value in [
        ("Local parent", ctx.local_parent),
        ("World parent", ctx.world_parent),
        ("Joint parent", ctx.joint_parent),
    ]:
        if value and not resolve_transform_for_parent(value):
            raise ValueError(f"{label} must be a transform, not a shape: {value}")

    builder = BUILDERS.get(ctx.behaviour_id)
    if not builder:
        raise ValueError(f"Unknown behaviour: {ctx.behaviour_id}")

    cmds.undoInfo(openChunk=True)
    try:
        result = builder(ctx)
        print(
            f"In-Between: built {BEHAVIOUR_LABELS[ctx.behaviour_id]} "
            f"as '{ctx.base_name}' ({len(result.joint_chain)} joints)."
        )
        return result
    finally:
        cmds.undoInfo(closeChunk=True)


def suggest_rig_label_from_selection() -> str:
    sel = list_selected_targets()
    if not sel:
        return "rig"
    return sanitize_name(sel[0]) or "rig"
