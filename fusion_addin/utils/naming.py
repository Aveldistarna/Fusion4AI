"""
Body/component naming and lookup utilities.
Supports lookup by name or entityToken.
"""

import adsk.core
import adsk.fusion
from typing import Optional


def find_body(
    design: adsk.fusion.Design, body_ref: str
) -> Optional[adsk.fusion.BRepBody]:
    """
    Find a body by name or entityToken.
    Searches all components.
    """
    all_components = design.allComponents
    for i in range(all_components.count):
        comp = all_components.item(i)
        for j in range(comp.bRepBodies.count):
            body = comp.bRepBodies.item(j)
            if body.name == body_ref or body.entityToken == body_ref:
                return body
    return None


def body_info(body: adsk.fusion.BRepBody) -> dict:
    """Return a standardized dict describing a body."""
    from .geometry import body_bounding_box_mm

    return {
        "name": body.name,
        "id": body.entityToken,
        "volume_cm3": body.volume,
        "bounding_box": body_bounding_box_mm(body),
    }
