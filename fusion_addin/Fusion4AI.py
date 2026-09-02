"""
Fusion4AI — MCP bridge add-in for Autodesk Fusion.

Starts an HTTP server on localhost:7432 that accepts high-level CAD commands
from the Fusion4AI MCP server (Node.js) and executes them via the Fusion API.

Thread safety:
  The HTTP server runs on a background thread, but Fusion API calls must
  happen on the main (UI) thread.  We use a CustomEvent to marshal calls:
    1. HTTP handler puts (request_id, func, params) into a queue
    2. HTTP handler fires the CustomEvent
    3. Main thread picks up the event, runs func(params), puts result in response dict
    4. HTTP handler reads the result and returns it
"""

import adsk.core
import adsk.fusion
import importlib
import queue
import threading
import traceback
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

# Local imports
from .server import Fusion4AIServer, register_handler
from .handlers import session as session_handler
from .handlers import primitives as primitives_handler
from .handlers import queries as queries_handler
from .handlers import modifications as modifications_handler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CUSTOM_EVENT_ID = "fusion4ai_execute"
RESPONSE_TIMEOUT = 120  # seconds (extended for multi-step design scripts)

# ---------------------------------------------------------------------------
# Globals (managed by run/stop lifecycle)
# ---------------------------------------------------------------------------

_app: Optional[adsk.core.Application] = None
_server: Optional[Fusion4AIServer] = None
_custom_event: Optional[adsk.core.CustomEvent] = None
_event_handler: Optional[Any] = None

# Thread-safe queues for main-thread dispatch
_request_queue: "queue.Queue[Tuple[str, Callable, dict]]" = queue.Queue()
_response_map: Dict[str, Any] = {}
_response_events: Dict[str, threading.Event] = {}


# ---------------------------------------------------------------------------
# Main-thread execution bridge
# ---------------------------------------------------------------------------

def execute_on_main_thread(func: Callable, params: dict, timeout: float = RESPONSE_TIMEOUT) -> dict:
    """
    Schedule func(params) to run on Fusion's main thread.
    Blocks the calling (HTTP) thread until the result is ready or timeout.
    Returns the result dict.
    """
    req_id = str(uuid.uuid4())
    event = threading.Event()
    _response_events[req_id] = event

    _request_queue.put((req_id, func, params))

    # Fire the custom event to wake up the main thread
    if _app:
        _app.fireCustomEvent(CUSTOM_EVENT_ID)

    # Wait for result
    if not event.wait(timeout=timeout):
        _response_events.pop(req_id, None)
        _response_map.pop(req_id, None)
        raise TimeoutError(f"Fusion API call timed out after {timeout}s")

    _response_events.pop(req_id, None)
    result = _response_map.pop(req_id)

    if isinstance(result, Exception):
        raise result
    return result


class CustomEventHandler(adsk.core.CustomEventHandler):
    """Processes queued requests on the main thread."""

    def __init__(self):
        super().__init__()

    def notify(self, args: adsk.core.CustomEventArgs) -> None:
        # Drain all pending requests
        while not _request_queue.empty():
            try:
                req_id, func, params = _request_queue.get_nowait()
            except queue.Empty:
                break

            try:
                # Record timeline position before operation
                timeline_start = None
                try:
                    app = adsk.core.Application.get()
                    design = adsk.fusion.Design.cast(app.activeProduct)
                    if design and design.designType == adsk.fusion.DesignTypes.ParametricDesignType:
                        timeline_start = design.timeline.count
                except Exception:
                    pass

                result = func(params)

                # Group timeline entries created by this operation and label
                # them so the timeline reads as a structured build log.
                try:
                    if timeline_start is not None and design:
                        timeline = design.timeline
                        timeline_end = timeline.count - 1
                        label = _timeline_label(params)
                        if timeline_end > timeline_start:
                            # Multiple timeline items created — group them
                            group = timeline.timelineGroups.add(timeline_start, timeline_end)
                            if group and label:
                                group.name = label
                        elif timeline_end == timeline_start and label:
                            # Single item — rename it directly
                            timeline.item(timeline_start).name = label
                except Exception:
                    pass  # Grouping/labeling failure is non-fatal

                _response_map[req_id] = result
            except Exception as e:
                traceback.print_exc()
                _response_map[req_id] = e

            event = _response_events.get(req_id)
            if event:
                event.set()


# ---------------------------------------------------------------------------
# Wrapped handlers (route through main thread)
# ---------------------------------------------------------------------------

def _timeline_label(params: dict) -> Optional[str]:
    """Build a timeline label: explicit timeline_label, or '<op> <subject>'."""
    label = params.get("timeline_label")
    if not label:
        op = params.get("_op") or ""
        subject = params.get("name") or params.get("target") or params.get("body_name") or ""
        label = f"{op} {subject}".strip()
    return label[:80] if label else None


def _make_main_thread_wrapper(func: Callable, action_name: Optional[str] = None) -> Callable:
    """Wrap a handler function to execute on the main thread.
    Injects the action name as params['_op'] for provenance/labeling."""
    def wrapper(params: dict) -> dict:
        if action_name and "_op" not in params:
            params["_op"] = action_name
        return execute_on_main_thread(func, params)
    return wrapper


def _get_handler_modules() -> dict:
    """Return the mapping of handler name -> module."""
    from .handlers import session as session_handler
    from .handlers import context as context_handler
    from .handlers import primitives as primitives_handler
    from .handlers import queries as queries_handler
    from .handlers import modifications as modifications_handler
    from .handlers import modules as modules_handler
    from .handlers import shape as shape_handler
    from .handlers import design_script as design_script_handler
    # Note: context must precede primitives/modifications so importlib.reload
    # refreshes it before its dependents.
    return {
        "session": session_handler,
        "context": context_handler,
        "modules": modules_handler,
        "shape": shape_handler,
        "primitives": primitives_handler,
        "queries": queries_handler,
        "modifications": modifications_handler,
        "design_script": design_script_handler,
    }


def _register_all_handlers(reload: bool = False) -> dict:
    """Register all handler modules, wrapping each action for main-thread execution.
    If reload=True, uses importlib.reload to pick up code changes."""
    handler_modules = _get_handler_modules()

    # Also reload utility modules
    if reload:
        from .utils import geometry as geom_mod
        from .utils import naming as naming_mod
        from .handlers import constraints as constraints_mod
        importlib.reload(geom_mod)
        importlib.reload(naming_mod)
        # constraints is a library, not a handler — reloaded here so edits to
        # the grammar land without restarting the add-in.
        importlib.reload(constraints_mod)

    reloaded = []
    for name, module in handler_modules.items():
        if reload:
            importlib.reload(module)
            reloaded.append(name)
        wrapped_actions = {
            action_name: _make_main_thread_wrapper(action_func, action_name)
            for action_name, action_func in module.ACTIONS.items()
        }
        register_handler(name, wrapped_actions)

    # Register the reload action itself (runs directly, not through handler modules)
    def _reload_action(params: dict) -> dict:
        result = _register_all_handlers(reload=True)
        return result

    register_handler("system", {
        "reload": _make_main_thread_wrapper(_reload_action),
    })

    return {"reloaded": reloaded, "handlers": list(handler_modules.keys())}


# ---------------------------------------------------------------------------
# Add-in lifecycle
# ---------------------------------------------------------------------------

def run(context: dict) -> None:
    global _app, _server, _custom_event, _event_handler

    try:
        _app = adsk.core.Application.get()

        # Register CustomEvent for main-thread dispatch
        _custom_event = _app.registerCustomEvent(CUSTOM_EVENT_ID)
        _event_handler = CustomEventHandler()
        _custom_event.add(_event_handler)

        # Register handler modules
        _register_all_handlers()

        # Start HTTP server
        _server = Fusion4AIServer()
        _server.start()

        # No dialog on successful start — log to the text command palette instead.
        print("[Fusion4AI] MCP bridge started. HTTP server listening on 127.0.0.1:7432")

    except Exception:
        traceback.print_exc()
        if _app:
            _app.userInterface.messageBox(
                f"Fusion4AI failed to start:\n{traceback.format_exc()}",
                "Fusion4AI Error",
            )


def stop(context: dict) -> None:
    global _app, _server, _custom_event, _event_handler

    try:
        if _server:
            _server.stop()
            _server = None

        if _custom_event and _event_handler:
            _custom_event.remove(_event_handler)
            _event_handler = None

        if _app and _custom_event:
            _app.unregisterCustomEvent(CUSTOM_EVENT_ID)
            _custom_event = None

        _app = None

    except Exception:
        traceback.print_exc()
