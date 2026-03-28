"""
Session handler — ping and status queries.
These run on the main thread via CustomEvent dispatch.
"""

import adsk.core
import adsk.fusion


def ping(params: dict) -> dict:
    """Return Fusion version and active document name."""
    app = adsk.core.Application.get()
    version = app.version if app else "unknown"
    doc = app.activeDocument
    doc_name = doc.name if doc else "(no document)"
    return {"version": version, "document": doc_name}


def status(params: dict) -> dict:
    """Return detailed design status."""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if not doc:
        return {"document": "(no document)", "body_count": 0, "component_count": 0}

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        return {"document": doc.name, "body_count": 0, "component_count": 0}

    root = design.rootComponent
    body_count = root.bRepBodies.count

    # Count bodies across all components
    all_components = design.allComponents
    total_bodies = 0
    for i in range(all_components.count):
        comp = all_components.item(i)
        total_bodies += comp.bRepBodies.count

    return {
        "document": doc.name,
        "body_count": total_bodies,
        "component_count": all_components.count,
        "root_bodies": body_count,
    }


def debug_plane(params: dict) -> dict:
    """Test construction plane creation with various methods."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return {"error": "No active design"}

    root = design.rootComponent
    results = {}

    # Report design type
    results["design_type"] = str(design.designType)

    # Test 1: Check if setByPlane exists
    planes = root.constructionPlanes
    plane_input = planes.createInput()
    results["plane_input_methods"] = [m for m in dir(plane_input) if m.startswith("set")]

    # Test 2: Try setByThreePoints
    try:
        # Create 3 points on the Z=0 plane
        p1 = adsk.core.Point3D.create(0, 0, 0)
        p2 = adsk.core.Point3D.create(1, 0, 0)
        p3 = adsk.core.Point3D.create(0, 1, 0)
        plane_input2 = planes.createInput()
        plane_input2.setByThreePoints(p1, p2, p3)
        cp = planes.add(plane_input2)
        results["setByThreePoints"] = "SUCCESS" if cp else "returned None"
        if cp:
            cp.deleteMe()
    except Exception as e:
        results["setByThreePoints"] = f"FAILED: {e}"

    # Test 3: Try setByAngle from XY plane
    try:
        plane_input3 = planes.createInput()
        # setByAngle needs a linear edge and an angle
        results["setByAngle_signature"] = "needs edge + angle"
    except Exception as e:
        results["setByAngle"] = f"FAILED: {e}"

    # Test 4: Try splitBodyFeatures availability
    try:
        split_feats = root.features.splitBodyFeatures
        results["splitBodyFeatures"] = "available"
    except Exception as e:
        results["splitBodyFeatures"] = f"FAILED: {e}"

    return results


def undo(params: dict) -> dict:
    """Undo the last operation(s) in the design timeline."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active design.")

    count = params.get("count", 1)
    timeline = design.timeline
    total = timeline.count

    if total == 0:
        return {"message": "Nothing to undo.", "timeline_count": 0}

    undone = 0
    for _ in range(count):
        if timeline.count == 0:
            break
        # Move the marker back by one
        marker = timeline.markerPosition
        if marker <= 0:
            break
        timeline.markerPosition = marker - 1
        undone += 1

    return {
        "undone": undone,
        "timeline_position": timeline.markerPosition,
        "timeline_count": timeline.count,
    }


def redo(params: dict) -> dict:
    """Redo previously undone operation(s)."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active design.")

    count = params.get("count", 1)
    timeline = design.timeline
    total = timeline.count

    redone = 0
    for _ in range(count):
        marker = timeline.markerPosition
        if marker >= total:
            break
        timeline.markerPosition = marker + 1
        redone += 1

    return {
        "redone": redone,
        "timeline_position": timeline.markerPosition,
        "timeline_count": timeline.count,
    }


ACTIONS = {
    "ping": ping,
    "status": status,
    "debug_plane": debug_plane,
    "undo": undo,
    "redo": redo,
}
