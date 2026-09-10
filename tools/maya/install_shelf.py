"""
Drag this file into the Maya viewport to add an In-Between shelf button.

Re-run if you move the repo. Manual run: python install_shelf.py in Script Editor.
"""

SHELF_BUTTON_LABEL = "In-Between"


def onMayaDroppedPythonFile(*args, **kwargs):
    """Maya drag-and-drop entry point — must exist at module level for Maya to find it."""
    _install_from_drop(args)


def _tools_dir_from_drop_args(args):
    import os

    if args and args[0]:
        return os.path.dirname(os.path.abspath(str(args[0])))
    if "__file__" in globals() and globals().get("__file__"):
        return os.path.dirname(os.path.abspath(__file__))
    return None


def _install_from_drop(args=()):
    import os

    import maya.cmds as cmds
    import maya.mel as mel

    tools_maya = _tools_dir_from_drop_args(args)
    if not tools_maya:
        cmds.warning("In-Between install: could not resolve tools/maya path.")
        return

    shelf = mel.eval("string $inBetweenShelf = `tabLayout -query -selectTab $gShelfTopLevel`")
    cmds.setParent(shelf)

    for child in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.shelfButton(child, query=True, label=True) == SHELF_BUTTON_LABEL:
            cmds.deleteUI(child)

    path = tools_maya.replace("\\", "/")
    command = (
        "import sys\n"
        f"_tools_maya = r'{path}'\n"
        "if _tools_maya not in sys.path:\n"
        "    sys.path.insert(0, _tools_maya)\n"
        "import run_in_between\n"
        "run_in_between.show()\n"
    )

    cmds.shelfButton(
        label=SHELF_BUTTON_LABEL,
        annotation="The In-Between — math-driven rigs between two transforms",
        image="pythonFamily.png",
        command=command,
        sourceType="python",
        imageOverlayLabel="InB",
    )

    print(f"In-Between: shelf button added on '{shelf}' (tools at {tools_maya})")


def install():
    """Run from Script Editor: exec(open(...).read()) or import install_shelf; install_shelf.install()"""
    _install_from_drop(())


if __name__ == "__main__":
    install()
