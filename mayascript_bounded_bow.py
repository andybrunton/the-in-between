import maya.cmds as cmds
import math

def build_bounded_bow_curve():
    sel = cmds.ls(selection=True)
    if not sel or len(sel) < 2:
        cmds.warning("Please select at least two objects to act as Start and End.")
        return
        
    start_obj = sel[0]
    end_obj = sel[1]
    name = "BoundedBow"
    
    if cmds.objExists(f"{name}_Grp"):
        cmds.delete(f"{name}_Grp")
        
    # 1. Hierarchy Setup & Bend Angle Roll Group
    root = cmds.group(em=True, name=f"{name}_Grp")
    space_grp = cmds.group(em=True, name=f"{name}_Space")
    orient_grp = cmds.group(em=True, name=f"{name}_Orient") 
    
    cmds.parent(orient_grp, space_grp)
    cmds.parent(space_grp, root)
    
    cmds.matchTransform(space_grp, start_obj, pos=True, rot=False)
    cmds.pointConstraint(start_obj, space_grp, maintainOffset=False)
    cmds.aimConstraint(end_obj, space_grp, aimVector=(1, 0, 0), upVector=(0, 1, 0), 
                       worldUpType="objectrotation", worldUpObject=start_obj, worldUpVector=(0, 1, 0))
    
    pos1 = cmds.xform(start_obj, q=True, ws=True, t=True)
    pos2 = cmds.xform(end_obj, q=True, ws=True, t=True)
    rest_dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos1, pos2)))
    
    # 2. Settings Node Setup
    settings = cmds.spaceLocator(name=f"{name}_Settings")[0]
    cmds.parent(settings, root)
    cmds.xform(settings, ws=True, t=((pos1[0]+pos2[0])/2, (pos1[1]+pos2[1])/2, (pos1[2]+pos2[2])/2))
    cmds.setAttr(f"{settings}.visibility", 0)
    
    cmds.addAttr(settings, ln="weight", at="float", dv=1.0, k=True)
    cmds.addAttr(settings, ln="tangentWeight", at="float", dv=0.55, k=True, min=0, max=1)
    cmds.addAttr(settings, ln="restLength", at="float", dv=rest_dist, k=True)
    cmds.addAttr(settings, ln="bendAngle", at="float", dv=0.0, k=True)
    
    cmds.connectAttr(f"{settings}.bendAngle", f"{orient_grp}.rotateX")
    
    # 3. Curve Generation
    p_init = [(rest_dist * (i / 6.0), 0, 0) for i in range(7)]
    curve = cmds.curve(d=3, p=p_init, k=[0,0,0, 1,1,1, 2,2,2], name=f"{name}_Crv")
    
    cmds.parent(curve, orient_grp)
    for attr in ['tx', 'ty', 'tz', 'rx', 'ry', 'rz']:
        cmds.setAttr(f"{curve}.{attr}", 0)
    cmds.setAttr(f"{curve}.inheritsTransform", 1)
    
    # 4. Base Distance & Compression Math
    dist_node = cmds.createNode('distanceBetween', name=f"{name}_Dist")
    decomp1 = cmds.createNode('decomposeMatrix', name=f"{name}_StartDecomp")
    decomp2 = cmds.createNode('decomposeMatrix', name=f"{name}_EndDecomp")
    
    cmds.connectAttr(f"{start_obj}.worldMatrix[0]", f"{decomp1}.inputMatrix")
    cmds.connectAttr(f"{end_obj}.worldMatrix[0]", f"{decomp2}.inputMatrix")
    cmds.connectAttr(f"{decomp1}.outputTranslate", f"{dist_node}.point1")
    cmds.connectAttr(f"{decomp2}.outputTranslate", f"{dist_node}.point2")
    
    remap = cmds.createNode('setRange', name=f"{name}_Remap")
    cmds.setAttr(f"{remap}.oldMinX", rest_dist * 0.35) 
    cmds.connectAttr(f"{settings}.restLength", f"{remap}.oldMaxX")
    cmds.setAttr(f"{remap}.minX", 1.0)
    cmds.setAttr(f"{remap}.maxX", 0.0)
    cmds.connectAttr(f"{dist_node}.distance", f"{remap}.valueX")
    
    # 5. Cleaned Up Math Nodes (No Skew)
    mult_L = cmds.createNode('multiplyDivide', name=f"{name}_L_Fracs")
    cmds.connectAttr(f"{dist_node}.distance", f"{mult_L}.input1X")
    cmds.connectAttr(f"{dist_node}.distance", f"{mult_L}.input1Y")
    cmds.connectAttr(f"{dist_node}.distance", f"{mult_L}.input1Z")
    cmds.setAttr(f"{mult_L}.input2X", 0.5)
    cmds.setAttr(f"{mult_L}.input2Y", 0.25)
    cmds.setAttr(f"{mult_L}.input2Z", 0.75)
    
    # Calculate Base Tangent Offset (T)
    mult_params = cmds.createNode('multiplyDivide', name=f"{name}_TangentScale")
    cmds.connectAttr(f"{settings}.tangentWeight", f"{mult_params}.input1X")
    cmds.connectAttr(f"{mult_L}.outputX", f"{mult_params}.input2X") 
    
    mult_T = cmds.createNode('multiplyDivide', name=f"{name}_T_Fracs")
    cmds.connectAttr(f"{mult_params}.outputX", f"{mult_T}.input1X")
    cmds.connectAttr(f"{mult_params}.outputX", f"{mult_T}.input1Y")
    cmds.connectAttr(f"{mult_params}.outputX", f"{mult_T}.input1Z")
    cmds.setAttr(f"{mult_T}.input2X", 0.5)
    cmds.setAttr(f"{mult_T}.input2Y", 0.25)
    cmds.setAttr(f"{mult_T}.input2Z", -0.25) 
    
    # Y-Axis Bulge Math
    mult_hEff = cmds.createNode('multiplyDivide', name=f"{name}_hEff_Base")
    cmds.connectAttr(f"{remap}.outValueX", f"{mult_hEff}.input1X")
    cmds.connectAttr(f"{settings}.weight", f"{mult_hEff}.input2X")
    
    mult_hEff_final = cmds.createNode('multiplyDivide', name=f"{name}_hEff_Final")
    cmds.setAttr(f"{mult_hEff_final}.input2X", rest_dist * 0.42) 
    cmds.connectAttr(f"{mult_hEff}.outputX", f"{mult_hEff_final}.input1X")
    
    mult_hEff_fracs = cmds.createNode('multiplyDivide', name=f"{name}_hEff_Fracs")
    cmds.connectAttr(f"{mult_hEff_final}.outputX", f"{mult_hEff_fracs}.input1X")
    cmds.connectAttr(f"{mult_hEff_final}.outputX", f"{mult_hEff_fracs}.input1Y")
    cmds.setAttr(f"{mult_hEff_fracs}.input2X", 0.5)
    cmds.setAttr(f"{mult_hEff_fracs}.input2Y", 0.75)
    
    # Simplified CV Coordinate Sums
    def make_pma(name, inputs, op=1):
        pma = cmds.createNode('plusMinusAverage', name=name)
        cmds.setAttr(f"{pma}.operation", op)
        for i, plug in enumerate(inputs):
            cmds.connectAttr(plug, f"{pma}.input1D[{i}]")
        return f"{pma}.output1D"
        
    cv2_x = make_pma(f"{name}_CV2_X", [f"{mult_L}.outputY", f"{mult_T}.outputY"])
    cv4_x = make_pma(f"{name}_CV4_X", [f"{mult_L}.outputZ", f"{mult_T}.outputZ"])
    cv5_x = make_pma(f"{name}_CV5_X", [f"{dist_node}.distance", f"{mult_T}.outputX"], op=2)
    
    # 6. Wire to Curve Control Points
    cvs = f"{curve}.controlPoints"
    
    cmds.connectAttr(f"{mult_T}.outputX", f"{cvs}[1].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputX", f"{cvs}[1].yValue")
    
    cmds.connectAttr(cv2_x, f"{cvs}[2].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputY", f"{cvs}[2].yValue")
    
    # CV 3 (Peak) plugs directly into L_half now, saving a PMA node
    cmds.connectAttr(f"{mult_L}.outputX", f"{cvs}[3].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputY", f"{cvs}[3].yValue")
    
    cmds.connectAttr(cv4_x, f"{cvs}[4].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputY", f"{cvs}[4].yValue")
    
    cmds.connectAttr(cv5_x, f"{cvs}[5].xValue")
    cmds.connectAttr(f"{mult_hEff_fracs}.outputX", f"{cvs}[5].yValue")
    
    cmds.connectAttr(f"{dist_node}.distance", f"{cvs}[6].xValue")
    
    cmds.select(settings)
    print(f"Bounded Bow Curve rigged between {start_obj} and {end_obj}")

build_bounded_bow_curve()