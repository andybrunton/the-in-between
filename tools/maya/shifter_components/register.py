"""Register the In-Between Shifter components with mGear, from inside Maya.

    import sys; sys.path.append(r"C:\\path\\to\\the-in-between\\tools\\maya\\shifter_components")
    import register; register.register()

Re-run register() after every code edit: it flushes both Shifter's component
cache and our own modules so the next guide draw / rig build uses fresh code.

To make it permanent instead, add this folder to the MGEAR_SHIFTER_COMPONENT_PATH
environment variable (it wants the folder that *contains* the components).
"""

import os
import sys

ENV_KEY = "MGEAR_SHIFTER_COMPONENT_PATH"
COMPONENTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _component_names():
    return [
        name
        for name in sorted(os.listdir(COMPONENTS_DIR))
        if os.path.exists(os.path.join(COMPONENTS_DIR, name, "__init__.py"))
    ]


def flush_modules():
    """Drop our component packages from sys.modules so they re-import."""
    for name in _component_names():
        for loaded in [
            m
            for m in sys.modules
            if m == name or m.startswith(name + ".")
        ]:
            del sys.modules[loaded]


def register():
    """Put this folder on MGEAR_SHIFTER_COMPONENT_PATH and clear all caches."""
    paths = [p for p in os.environ.get(ENV_KEY, "").split(os.pathsep) if p]
    if COMPONENTS_DIR not in paths:
        paths.append(COMPONENTS_DIR)
        os.environ[ENV_KEY] = os.pathsep.join(paths)

    flush_modules()

    from mgear import shifter

    shifter.clearComponentCache()

    names = _component_names()
    print("In-Between: registered {} -> {}".format(COMPONENTS_DIR, names))
    return names
