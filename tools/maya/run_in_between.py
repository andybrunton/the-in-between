"""
The In-Between — Maya companion tool entry point.

Drag into Maya 2026 Script Editor or add to a shelf:

    import run_in_between
    run_in_between.show()

Dev reload (after editing any in_between/*.py):

    import run_in_between
    run_in_between.show(reload=True)

Or reload without opening the UI:

    import run_in_between
    run_in_between.reload_all()
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys


def _bootstrap_path():
    this_dir = os.path.dirname(os.path.abspath(__file__))
    if this_dir not in sys.path:
        sys.path.insert(0, this_dir)


def _close_ui():
    try:
        from in_between.ui.main_window import _close_existing_windows

        _close_existing_windows()
    except ImportError:
        pass


def _import_package(package_name: str) -> None:
    """Import package and every submodule so reload_all sees the full tree."""
    pkg = importlib.import_module(package_name)
    if not hasattr(pkg, "__path__"):
        return
    for mod in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        importlib.import_module(mod.name)


def reload_all() -> list[str]:
    """
    Reload every loaded in_between.* module (deepest first).

    Closes any open In-Between window first. Returns reloaded module names.
    """
    _bootstrap_path()
    _close_ui()

    _import_package("in_between")

    names = sorted(
        (n for n in sys.modules if n == "in_between" or n.startswith("in_between.")),
        key=lambda n: n.count("."),
        reverse=True,
    )
    reloaded: list[str] = []
    for name in names:
        importlib.reload(sys.modules[name])
        reloaded.append(name)
    return reloaded


def show(reload: bool = False):
    _bootstrap_path()
    if reload:
        reload_all()
    from in_between.ui.main_window import show as _show

    return _show()


if __name__ == "__main__":
    show()
