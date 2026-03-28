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


ACTIONS = {
    "ping": ping,
    "status": status,
}
