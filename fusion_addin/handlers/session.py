"""
Session handler — ping/status queries, timeline inspection, and checkpoints.
These run on the main thread via CustomEvent dispatch.
"""

import adsk.core
import adsk.fusion
import json
from datetime import datetime

CHECKPOINT_ATTR_GROUP = "fusion4ai"
CHECKPOINT_ATTR_NAME = "checkpoints"


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
                try:
                    if group and group.name:
                        entry["name"] = group.name
                except Exception:
                    pass
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
                # Surface embedded design intent so the timeline reads as a build log
                try:
                    attrs = getattr(entity, "attributes", None)
                    if attrs:
                        attr = attrs.itemByName("fusion4ai", "context")
                        if attr and attr.value:
                            intent = json.loads(attr.value).get("intent")
                            if intent:
                                entry["intent"] = intent
                except Exception:
                    pass
            else:
                entry["type"] = "unknown"
        except Exception:
            entry["type"] = "unknown"

        items.append(entry)

    return {
        "items": items,
        "count": timeline.count,
        "marker_position": marker,
        "checkpoints": _load_checkpoints(design),
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


# ---------------------------------------------------------------------------
# Checkpoints — named timeline positions for part-level rollback
# ---------------------------------------------------------------------------

def _get_design_or_raise() -> adsk.fusion.Design:
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise RuntimeError("No active design.")
    return design


def _load_checkpoints(design: adsk.fusion.Design) -> list:
    try:
        attr = design.rootComponent.attributes.itemByName(
            CHECKPOINT_ATTR_GROUP, CHECKPOINT_ATTR_NAME
        )
        if attr and attr.value:
            return json.loads(attr.value)
    except Exception:
        pass
    return []


def _save_checkpoints(design: adsk.fusion.Design, checkpoints: list) -> None:
    value = json.dumps(checkpoints, ensure_ascii=False, separators=(",", ":"))
    attrs = design.rootComponent.attributes
    existing = attrs.itemByName(CHECKPOINT_ATTR_GROUP, CHECKPOINT_ATTR_NAME)
    if existing:
        existing.value = value
    else:
        attrs.add(CHECKPOINT_ATTR_GROUP, CHECKPOINT_ATTR_NAME, value)


def set_checkpoint(params: dict) -> dict:
    """Record a named checkpoint at the current end of the timeline.
    Call before starting a new part; rollback_to_checkpoint undoes back to it."""
    design = _get_design_or_raise()
    label = params.get("label")
    if not label:
        raise ValueError("Checkpoint requires a 'label'.")

    checkpoints = _load_checkpoints(design)
    checkpoints = [c for c in checkpoints if c.get("label") != label]
    checkpoints.append({
        "label": label,
        "position": design.timeline.count,
        "at": datetime.now().isoformat(timespec="seconds"),
    })
    _save_checkpoints(design, checkpoints)
    return {"checkpoint": label, "position": design.timeline.count, "checkpoints": checkpoints}


def list_checkpoints(params: dict) -> dict:
    design = _get_design_or_raise()
    return {
        "checkpoints": _load_checkpoints(design),
        "timeline_count": design.timeline.count,
    }


def rollback_to_checkpoint(params: dict) -> dict:
    """Permanently delete all timeline items created after a checkpoint.
    Use to undo one failed part instead of abandoning it or starting a new design."""
    design = _get_design_or_raise()
    timeline = design.timeline

    checkpoints = _load_checkpoints(design)
    if "label" in params:
        matches = [c for c in checkpoints if c.get("label") == params["label"]]
        if not matches:
            known = [c.get("label") for c in checkpoints]
            raise ValueError(f"Checkpoint not found: {params['label']}. Known: {known}")
        position = matches[-1]["position"]
    elif "position" in params:
        position = int(params["position"])
    else:
        raise ValueError("Specify 'label' or 'position'.")

    if position > timeline.count:
        raise ValueError(
            f"Checkpoint position {position} is beyond timeline count {timeline.count}."
        )

    # Ensure nothing is rolled back before deleting from the end
    try:
        timeline.moveToEnd()
    except Exception:
        pass

    deleted = []
    while timeline.count > position:
        before = timeline.count
        item = timeline.item(timeline.count - 1)
        info = {"index": timeline.count - 1}
        try:
            info["name"] = item.name
        except Exception:
            pass

        if item.isGroup:
            group = adsk.fusion.TimelineGroup.cast(item)
            info["type"] = "Group"
            if not group.deleteMe(True):  # True = delete group AND contents
                raise RuntimeError(f"Failed to delete timeline group: {info}. Deleted so far: {deleted}")
        else:
            entity = item.entity
            info["type"] = type(entity).__name__ if entity else "unknown"
            if entity and hasattr(entity, "deleteMe"):
                if not entity.deleteMe():
                    raise RuntimeError(f"Failed to delete timeline item: {info}. Deleted so far: {deleted}")
            else:
                raise RuntimeError(f"Cannot delete timeline item: {info}. Deleted so far: {deleted}")

        if timeline.count >= before:
            raise RuntimeError(f"Timeline did not shrink after deleting {info}; aborting rollback.")
        deleted.append(info)

    # Drop checkpoints that now point beyond the timeline
    checkpoints = [c for c in checkpoints if c.get("position", 0) <= timeline.count]
    _save_checkpoints(design, checkpoints)

    return {
        "rolled_back_to": position,
        "deleted_items": deleted,
        "deleted_count": len(deleted),
        "timeline_count": timeline.count,
        "checkpoints": checkpoints,
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
    "set_checkpoint": set_checkpoint,
    "list_checkpoints": list_checkpoints,
    "rollback_to_checkpoint": rollback_to_checkpoint,
}
