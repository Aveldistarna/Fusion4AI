"""
Design Script engine — execute a complete CSG design from YAML/JSON description.

AI writes a design script describing shapes, boolean operations, fillets, and patterns.
The engine resolves position references, expands patterns, and calls existing handlers.
"""

import json
import math
import os
import re
import traceback
from typing import Any, Dict, List, Optional, Tuple

# Try YAML, fall back to JSON-only
try:
    import yaml
    HAS_YAML = True
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
        import yaml
        HAS_YAML = True
    except ImportError:
        HAS_YAML = False

from . import primitives
from . import modifications
from . import queries


# ---------------------------------------------------------------------------
# Position resolution
# ---------------------------------------------------------------------------

def _resolve_axis(value: Any, bbox: Dict, axis_idx: int) -> float:
    """Resolve a single axis value: number or string expression like 'top-15'."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.match(r'^(top|bottom|center)([+-]\d+\.?\d*)?$', value.strip())
        if m:
            base = m.group(1)
            offset = float(m.group(2)) if m.group(2) else 0.0
            if base == "top":
                return bbox["max"][axis_idx] + offset
            elif base == "bottom":
                return bbox["min"][axis_idx] + offset
            elif base == "center":
                return (bbox["min"][axis_idx] + bbox["max"][axis_idx]) / 2 + offset
    raise ValueError(f"Cannot resolve axis value: {value}")


def resolve_position(at_ref: Any, bbox: Dict) -> List[float]:
    """Resolve a position reference to [x, y, z] in mm."""
    if at_ref is None or at_ref == "origin":
        return [0.0, 0.0, 0.0]

    if isinstance(at_ref, list):
        return [_resolve_axis(v, bbox, i) for i, v in enumerate(at_ref)]

    if isinstance(at_ref, str):
        center_x = (bbox["min"][0] + bbox["max"][0]) / 2
        center_y = (bbox["min"][1] + bbox["max"][1]) / 2
        m = re.match(r'^(top|bottom|center)([+-]\d+\.?\d*)?$', at_ref.strip())
        if m:
            base = m.group(1)
            offset = float(m.group(2)) if m.group(2) else 0.0
            if base == "top":
                return [center_x, center_y, bbox["max"][2] + offset]
            elif base == "bottom":
                return [center_x, center_y, bbox["min"][2] + offset]
            elif base == "center":
                cz = (bbox["min"][2] + bbox["max"][2]) / 2
                return [center_x, center_y, cz + offset]

    raise ValueError(f"Invalid position reference: {at_ref}")


# ---------------------------------------------------------------------------
# Pattern expansion
# ---------------------------------------------------------------------------

def expand_pattern(pattern_str: str) -> List[Tuple[float, float]]:
    """Expand a pattern string to a list of (dx, dy) offsets in mm."""
    m = re.match(r'^(corners|grid|circular)\((.+)\)$', pattern_str.strip())
    if not m:
        raise ValueError(f"Unknown pattern: {pattern_str}")

    kind = m.group(1)
    args = [float(a.strip()) for a in m.group(2).split(",")]

    if kind == "corners":
        s = args[0] / 2
        return [(s, s), (s, -s), (-s, -s), (-s, s)]

    elif kind == "grid":
        nx, ny = int(args[0]), int(args[1])
        sx = args[2]
        sy = args[3] if len(args) > 3 else sx
        offsets = []
        for ix in range(nx):
            for iy in range(ny):
                x = (ix - (nx - 1) / 2) * sx
                y = (iy - (ny - 1) / 2) * sy
                offsets.append((x, y))
        return offsets

    elif kind == "circular":
        count = int(args[0])
        radius = args[1]
        return [
            (radius * math.cos(2 * math.pi * i / count),
             radius * math.sin(2 * math.pi * i / count))
            for i in range(count)
        ]

    return []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

SHAPE_SIZE_COUNTS = {"box": 3, "cylinder": 2, "sphere": 1, "cone": 3, "polygon": None}
KNOWN_OPS = {"union", "subtract", "fillet", "chamfer", "cut_by_plane", "select"}
KNOWN_EDGE_REFS = {"all", "vertical", "horizontal", "perp_to_selection",
                   "top", "bottom", "front", "back", "left", "right"}


def validate_design(design: dict) -> List[str]:
    """Validate a parsed design script. Returns a list of error messages (empty = valid)."""
    errors = []

    # body section
    body = design.get("body")
    if not body:
        errors.append("Missing 'body' section.")
        return errors

    if not isinstance(body, dict):
        errors.append("'body' must be a mapping with 'shape' and 'size'.")
        return errors

    shape = body.get("shape")
    if not shape:
        errors.append("body: missing 'shape'.")
    elif shape not in SHAPE_SIZE_COUNTS:
        errors.append(f"body: unknown shape '{shape}'. Use: {list(SHAPE_SIZE_COUNTS.keys())}")

    if shape == "polygon":
        if not body.get("points"):
            errors.append("body: polygon shape requires 'points'.")
        if not body.get("height"):
            errors.append("body: polygon shape requires 'height'.")
    else:
        size = body.get("size")
        if not size:
            errors.append("body: missing 'size'.")
        elif not isinstance(size, list):
            errors.append("body: 'size' must be a list of numbers.")
        elif shape in SHAPE_SIZE_COUNTS and SHAPE_SIZE_COUNTS[shape] and len(size) != SHAPE_SIZE_COUNTS[shape]:
            errors.append(f"body: shape '{shape}' requires {SHAPE_SIZE_COUNTS[shape]} size values, got {len(size)}.")

    # features
    features = design.get("features", [])
    if not isinstance(features, list):
        errors.append("'features' must be a list.")
        return errors

    for i, feature in enumerate(features):
        prefix = f"feature[{i}]"
        if not isinstance(feature, dict):
            errors.append(f"{prefix}: must be a mapping.")
            continue

        # Find the operation key
        op_keys = [k for k in feature if k in KNOWN_OPS]
        if len(op_keys) == 0:
            errors.append(f"{prefix}: no known operation. Keys: {list(feature.keys())}. Use: {KNOWN_OPS}")
            continue
        if len(op_keys) > 1:
            errors.append(f"{prefix}: multiple operations in one feature: {op_keys}")
            continue

        op = op_keys[0]
        params = feature[op]
        if params is None:
            params = {}
        if not isinstance(params, dict):
            errors.append(f"{prefix} ({op}): parameters must be a mapping, got {type(params).__name__}.")
            continue

        # Validate union/subtract
        if op in ("union", "subtract"):
            if "shape" not in params:
                errors.append(f"{prefix} ({op}): missing 'shape'.")
            elif params["shape"] not in SHAPE_SIZE_COUNTS:
                errors.append(f"{prefix} ({op}): unknown shape '{params['shape']}'.")

            if params.get("shape") == "polygon":
                if "points" not in params:
                    errors.append(f"{prefix} ({op}): polygon requires 'points'.")
                if "height" not in params and "size" not in params:
                    errors.append(f"{prefix} ({op}): polygon requires 'height'.")
            elif "size" not in params:
                errors.append(f"{prefix} ({op}): missing 'size'.")

            if "pattern" in params:
                try:
                    expand_pattern(params["pattern"])
                except ValueError as e:
                    errors.append(f"{prefix} ({op}): invalid pattern: {e}")

        # Validate fillet/chamfer
        elif op == "fillet":
            if "radius" not in params:
                errors.append(f"{prefix} (fillet): missing 'radius'.")
            edges = params.get("edges", "all")
            if not edges.startswith("between:") and edges not in KNOWN_EDGE_REFS:
                errors.append(f"{prefix} (fillet): unknown edges '{edges}'.")

        elif op == "chamfer":
            if "distance" not in params:
                errors.append(f"{prefix} (chamfer): missing 'distance'.")

        elif op == "cut_by_plane":
            if "point" not in params:
                errors.append(f"{prefix} (cut_by_plane): missing 'point'.")
            if "normal" not in params:
                errors.append(f"{prefix} (cut_by_plane): missing 'normal'.")

    return errors


# ---------------------------------------------------------------------------
# Shape parameter mapping
# ---------------------------------------------------------------------------

SHAPE_PARAMS = {
    "box": lambda size: {"width": size[0], "depth": size[1], "height": size[2]},
    "cylinder": lambda size: {"diameter": size[0], "height": size[1]},
    "sphere": lambda size: {"diameter": size[0]},
    "cone": lambda size: {"base_diameter": size[0], "top_diameter": size[1], "height": size[2]},
    "polygon": None,  # polygon uses 'points' + 'height', not 'size'
}

SHAPE_CREATORS = {
    "box": primitives.create_box,
    "cylinder": primitives.create_cylinder,
    "sphere": primitives.create_sphere,
    "cone": primitives.create_cone,
    "polygon": primitives.create_polygon,
}


# ---------------------------------------------------------------------------
# Execution engine
# ---------------------------------------------------------------------------

def execute_design(params: dict) -> dict:
    """Execute a complete design from a YAML/JSON script."""
    script_str = params.get("yaml") or params.get("json")
    if not script_str:
        raise ValueError("No design script provided. Pass 'yaml' or 'json' parameter.")

    # Parse
    try:
        if HAS_YAML:
            design = yaml.safe_load(script_str)
        else:
            design = json.loads(script_str)
    except Exception as e:
        raise ValueError(f"Failed to parse design script: {e}")

    # Validate before execution
    validation_errors = validate_design(design)
    if validation_errors:
        return {
            "status": "validation_error",
            "errors": validation_errors,
        }

    body_spec = design["body"]
    features = design.get("features", [])
    design_name = design.get("name", "Design")
    resume_from = params.get("resume_from", 0)
    resume_body = params.get("body_name")

    results = []

    # --- Step 0: Create base body (unless resuming) ---
    if resume_from == 0:
        shape = body_spec["shape"]
        if shape not in SHAPE_PARAMS:
            raise ValueError(f"Unknown shape: {shape}. Use: {list(SHAPE_PARAMS.keys())}")

        if shape == "polygon":
            create_params = {"points": body_spec["points"], "height": body_spec["height"]}
        else:
            create_params = SHAPE_PARAMS[shape](body_spec["size"])
        create_params["name"] = design_name
        intent = body_spec.get("intent") or design.get("intent")
        if intent:
            create_params["intent"] = intent
        creator = SHAPE_CREATORS[shape]

        body_result = creator(create_params)
        body_name = body_result["name"]
        bbox = body_result["bounding_box"]
        results.append({"step": "body", "result": body_result})
    else:
        # Resuming: use provided body name
        if not resume_body:
            raise ValueError("body_name is required when resuming from checkpoint.")
        body_name = resume_body
        # Get current bbox
        import adsk.core, adsk.fusion
        app = adsk.core.Application.get()
        design_obj = adsk.fusion.Design.cast(app.activeProduct)
        from ..utils.naming import find_body, body_info
        body = find_body(design_obj, body_name)
        if not body:
            raise ValueError(f"Body not found for resume: {body_name}")
        info = body_info(body)
        bbox = info["bounding_box"]

    # --- Execute features ---
    for step_idx, feature in enumerate(features):
        if step_idx < resume_from:
            continue

        # Determine operation type (the single key in the feature dict)
        op_type = None
        op_params = None
        for key in feature:
            if key in ("union", "subtract", "fillet", "chamfer", "select", "cut_by_plane"):
                op_type = key
                op_params = feature[key] if isinstance(feature[key], dict) else {}
                break

        if not op_type:
            results.append({"step": step_idx, "warning": f"Unknown feature: {feature}"})
            continue

        try:
            # --- checkpoint: pause before this step ---
            checkpoint_msg = None
            if isinstance(op_params, dict):
                checkpoint_msg = op_params.pop("checkpoint", None)

            if checkpoint_msg:
                # Take screenshot
                screenshot_path = f"C:/temp/fusion4ai_checkpoint_{step_idx}.png"
                queries.screenshot({"output_path": screenshot_path, "width": 1280, "height": 720})
                return {
                    "status": "checkpoint",
                    "completed_steps": step_idx,
                    "body_name": body_name,
                    "screenshot_path": screenshot_path,
                    "message": checkpoint_msg,
                    "results": results,
                }

            # --- union / subtract ---
            if op_type in ("union", "subtract"):
                shape = op_params["shape"]
                size = op_params.get("size")
                at_ref = op_params.get("at")
                pattern_str = op_params.get("pattern")

                # Resolve base position
                base_pos = resolve_position(at_ref, bbox)

                # Handle "through" height
                if size:
                    height_idx = 1 if shape == "cylinder" else 2
                    if len(size) > height_idx and size[height_idx] == "through":
                        diag = math.sqrt(sum((mx - mn) ** 2 for mn, mx in zip(bbox["min"], bbox["max"])))
                        size = list(size)
                        size[height_idx] = diag * 2

                # Expand pattern or single position
                if pattern_str:
                    offsets = expand_pattern(pattern_str)
                else:
                    offsets = [(0, 0)]

                for dx, dy in offsets:
                    pos = [base_pos[0] + dx, base_pos[1] + dy, base_pos[2]]
                    if shape == "polygon":
                        create_params = {"points": op_params["points"], "height": op_params.get("height", size[0] if size else 1)}
                    else:
                        create_params = SHAPE_PARAMS[shape](size)
                    create_params["position"] = pos
                    create_params["boolean"] = op_type
                    create_params["target"] = body_name
                    if op_params.get("intent"):
                        create_params["intent"] = op_params["intent"]

                    creator = SHAPE_CREATORS[shape]
                    step_result = creator(create_params)

                    # Update bbox from result
                    if "bounding_box" in step_result:
                        bbox = step_result["bounding_box"]
                    if "name" in step_result:
                        body_name = step_result["name"]

                step_summary = {
                    "step": step_idx,
                    "op": op_type,
                    "shape": shape,
                    "count": len(offsets),
                    "volume_cm3": step_result.get("volume_cm3"),
                    "volume_delta_cm3": step_result.get("volume_delta_cm3"),
                }
                if step_result.get("volume_delta_cm3") is not None and abs(step_result["volume_delta_cm3"]) < 1e-6:
                    step_summary["warning"] = "volume unchanged"
                results.append(step_summary)

            # --- fillet ---
            elif op_type == "fillet":
                fillet_params = {
                    "body_name": body_name,
                    "radius": op_params["radius"],
                    "edges": op_params.get("edges", "all"),
                }
                step_result = modifications.add_fillet(fillet_params)
                results.append({
                    "step": step_idx,
                    "op": "fillet",
                    "radius": op_params["radius"],
                    "edges": op_params.get("edges", "all"),
                    "volume_cm3": step_result.get("volume_cm3"),
                })

            # --- chamfer ---
            elif op_type == "chamfer":
                chamfer_params = {
                    "body_name": body_name,
                    "distance": op_params["distance"],
                    "edges": op_params.get("edges", "all"),
                }
                step_result = modifications.add_chamfer(chamfer_params)
                results.append({
                    "step": step_idx,
                    "op": "chamfer",
                    "distance": op_params["distance"],
                    "volume_cm3": step_result.get("volume_cm3"),
                })

            # --- cut_by_plane ---
            elif op_type == "cut_by_plane":
                point = op_params["point"]
                normal = op_params["normal"]
                # Resolve point if it uses references
                if isinstance(point, str) or (isinstance(point, list) and any(isinstance(v, str) for v in point)):
                    point = resolve_position(point, bbox)
                cut_params = {
                    "body_name": body_name,
                    "point": point,
                    "normal": normal,
                }
                step_result = modifications.cut_by_plane(cut_params)
                if "bounding_box" in step_result:
                    bbox = step_result["bounding_box"]
                results.append({
                    "step": step_idx,
                    "op": "cut_by_plane",
                    "volume_cm3": step_result.get("volume_cm3"),
                    "volume_delta_cm3": step_result.get("volume_delta_cm3"),
                })

            # --- select (wait for user) ---
            elif op_type == "select":
                prompt = op_params.get("prompt", "面を選択してください") if isinstance(op_params, dict) else "面を選択してください"
                screenshot_path = f"C:/temp/fusion4ai_select_{step_idx}.png"
                queries.screenshot({"output_path": screenshot_path, "width": 1280, "height": 720})
                return {
                    "status": "select",
                    "completed_steps": step_idx,
                    "body_name": body_name,
                    "screenshot_path": screenshot_path,
                    "message": prompt,
                    "results": results,
                }

        except Exception as e:
            traceback.print_exc()
            return {
                "status": "error",
                "step_index": step_idx,
                "op": op_type,
                "error": str(e),
                "completed_steps": step_idx,
                "body_name": body_name,
                "results": results,
            }

    # --- All steps complete ---
    # Take final screenshot
    screenshot_path = "C:/temp/fusion4ai_design_complete.png"
    try:
        queries.screenshot({"output_path": screenshot_path, "width": 1280, "height": 720, "focus": "fit"})
    except Exception:
        screenshot_path = None

    return {
        "status": "complete",
        "body_name": body_name,
        "steps_executed": len(results),
        "screenshot_path": screenshot_path,
        "results": results,
    }


ACTIONS = {
    "execute_design": execute_design,
}
