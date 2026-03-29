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


def get_timeline(params: dict) -> dict:
    """List all items in the design timeline with index, type, and name."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active design.")

    timeline = design.timeline
    marker = timeline.markerPosition
    items = []

    for i in range(timeline.count):
        item = timeline.item(i)
        entry = {
            "index": i,
            "rolled_back": i >= marker,
        }

        try:
            entry["suppressed"] = item.isSuppressed
        except Exception:
            entry["suppressed"] = False

        try:
            # Check if this is a group
            if item.isGroup:
                group = adsk.fusion.TimelineGroup.cast(item)
                entry["type"] = "Group"
                entry["group_count"] = group.count if group else 0
                items.append(entry)
                continue
        except Exception:
            pass

        # Get the entity (feature, sketch, etc.)
        try:
            entity = item.entity
            if entity:
                entry["type"] = type(entity).__name__
                if hasattr(entity, "name"):
                    entry["name"] = entity.name
            else:
                entry["type"] = "unknown"
        except Exception:
            entry["type"] = "unknown"

        items.append(entry)

    return {
        "items": items,
        "count": timeline.count,
        "marker_position": marker,
    }


def delete_feature(params: dict) -> dict:
    """Delete a feature or sketch by timeline index or name."""
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active design.")

    timeline = design.timeline

    # Find the timeline item
    target = None
    if "index" in params:
        idx = params["index"]
        if idx < 0 or idx >= timeline.count:
            raise ValueError(f"Timeline index {idx} out of range (0-{timeline.count-1})")
        target = timeline.item(idx)
    elif "name" in params:
        name = params["name"]
        for i in range(timeline.count):
            item = timeline.item(i)
            entity = item.entity
            if entity and hasattr(entity, "name") and entity.name == name:
                target = item
                break
        if not target:
            raise ValueError(f"No timeline item found with name: {name}")
    else:
        raise ValueError("Specify 'index' or 'name' to identify the item to delete.")

    entity = target.entity
    deleted_info = {
        "type": type(entity).__name__ if entity else "unknown",
        "name": entity.name if entity and hasattr(entity, "name") else "unknown",
    }

    # Delete the entity
    if entity and hasattr(entity, "deleteMe"):
        ok = entity.deleteMe()
        if not ok:
            raise RuntimeError(f"deleteMe() returned False for {deleted_info}")
    else:
        raise RuntimeError(f"Cannot delete: {deleted_info}")

    return {
        "deleted": deleted_info,
        "timeline_count": timeline.count,
    }


def new_design(params: dict) -> dict:
    """Create a new empty design document."""
    app = adsk.core.Application.get()
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    return {
        "document": doc.name,
        "design_type": "parametric" if design.designType == adsk.fusion.DesignTypes.ParametricDesignType else "direct",
    }


ACTIONS = {
    "ping": ping,
    "status": status,
    "debug_plane": debug_plane,
    "undo": undo,
    "redo": redo,
    "get_timeline": get_timeline,
    "delete_feature": delete_feature,
    "new_design": new_design,
}
