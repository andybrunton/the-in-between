"""Unique naming for multiple rigs per scene."""

from __future__ import annotations

import re

import maya.cmds as cmds


def sanitize_name(name: str) -> str:
    """Maya-safe short name fragment (no path, no illegal chars)."""
    if not name:
        return ""
    short = name.split("|")[-1].strip()
    short = re.sub(r"[^\w]", "_", short)
    short = re.sub(r"_+", "_", short).strip("_")
    return short


def unique_name(base: str) -> str:
    """Return base if free, else base_01, base_02, …"""
    base = sanitize_name(base) or "rig"
    if not cmds.objExists(base):
        return base
    index = 1
    while cmds.objExists(f"{base}_{index:02d}"):
        index += 1
    return f"{base}_{index:02d}"


def token_name(prefix: str, suffix: str, ctx_name: str) -> str:
    """Build a node name: {ctx_name}_{suffix} with uniqueness."""
    return unique_name(f"{ctx_name}_{suffix}")
