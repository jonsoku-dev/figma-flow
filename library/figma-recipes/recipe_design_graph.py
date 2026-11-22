"""Validate and project canonical visual values for standalone recipe examples."""
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


LIBRARY = Path(__file__).resolve().parent
GRAPH_PATH = LIBRARY / "design-examples.graph.json"
SCHEMA = "figma-flow-recipe-design-graph-v1"
RECIPE_IDS = {
    "design-shapes", "design-grid", "design-motion",
    "design-component-properties", "design-type-review",
}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate design graph JSON key: " + key)
        value[key] = item
    return value


def parse_graph(data: bytes | str) -> dict[str, Any]:
    try:
        graph = json.loads(data, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Invalid recipe design graph JSON: " + str(error)) from error
    if not isinstance(graph, dict):
        raise ValueError("Recipe design graph root must be an object")
    return graph


def _positive_number(value: Any, name: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def _nonnegative_number(value: Any, name: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a nonnegative finite number")


def _color(value: Any, name: str) -> None:
    if not isinstance(value, dict) or set(value) != {"r", "g", "b"}:
        raise ValueError(f"{name} must have red, green, and blue channels")
    for channel in ("r", "g", "b"):
        component = value[channel]
        if type(component) not in (int, float) or not math.isfinite(component) or not 0 <= component <= 1:
            raise ValueError(f"{name}.{channel} must be a normalized finite channel")


def _exact_fields(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} fields differ from the recipe visual graph contract")
    return value


def _validate_visual(recipe: str, value: Any) -> None:
    if recipe == "design-shapes":
        visual = _exact_fields(value, {"frame", "booleans", "mask", "content"}, recipe)
        frame = _exact_fields(visual["frame"], {"width", "height", "pageXOffset", "fills", "clipsContent"}, recipe + ".frame")
        for key in ("width", "height", "pageXOffset"): _positive_number(frame[key], recipe + ".frame." + key)
        if frame["fills"] != [] or frame["clipsContent"] is not False: raise ValueError(recipe + ".frame must remain transparent and unclipped")
        booleans = _exact_fields(visual["booleans"], {"operations", "shapeWidth", "shapeHeight", "stepX", "overlapX", "secondY", "fillType", "fill"}, recipe + ".booleans")
        if booleans["operations"] != ["UNION", "SUBTRACT", "INTERSECT", "EXCLUDE"]: raise ValueError(recipe + ".booleans.operations must cover all four API examples")
        if booleans["fillType"] != "SOLID": raise ValueError(recipe + ".booleans.fillType must use a solid color")
        for key in ("shapeWidth", "shapeHeight", "stepX"): _positive_number(booleans[key], recipe + ".booleans." + key)
        for key in ("overlapX", "secondY"): _nonnegative_number(booleans[key], recipe + ".booleans." + key)
        _color(booleans["fill"], recipe + ".booleans.fill")
        mask = _exact_fields(visual["mask"], {"size", "y", "isMask", "maskType"}, recipe + ".mask")
        _positive_number(mask["size"], recipe + ".mask.size"); _nonnegative_number(mask["y"], recipe + ".mask.y")
        if mask["isMask"] is not True or mask["maskType"] != "ALPHA": raise ValueError(recipe + ".mask must use the authored alpha-mask mode")
        content = _exact_fields(visual["content"], {"width", "height", "y", "fillType", "fill"}, recipe + ".content")
        for key in ("width", "height"): _positive_number(content[key], recipe + ".content." + key)
        _nonnegative_number(content["y"], recipe + ".content.y"); _color(content["fill"], recipe + ".content.fill")
        if content["fillType"] != "SOLID": raise ValueError(recipe + ".content.fillType must use a solid color")
    elif recipe == "design-grid":
        visual = _exact_fields(value, {"frame", "grid", "cells"}, recipe)
        frame = _exact_fields(visual["frame"], {"width", "height", "pageXOffset"}, recipe + ".frame")
        for key, item in frame.items(): _positive_number(item, recipe + ".frame." + key)
        grid = _exact_fields(visual["grid"], {"mode", "autoTracks", "rows", "columns", "rowGap", "columnGap"}, recipe + ".grid")
        if grid["mode"] != "GRID" or grid["autoTracks"] != "NONE": raise ValueError(recipe + ".grid must demonstrate explicit auto-layout grid tracks")
        for key in ("rows", "columns"):
            if type(grid[key]) is not int or grid[key] < 1: raise ValueError(recipe + ".grid." + key + " must be a positive integer")
        for key in ("rowGap", "columnGap"): _nonnegative_number(grid[key], recipe + ".grid." + key)
        cells = _exact_fields(visual["cells"], {"count", "width", "height", "fillType", "fill", "redStep"}, recipe + ".cells")
        if type(cells["count"]) is not int or cells["count"] != grid["rows"] * grid["columns"]:
            raise ValueError(recipe + ".cells.count must match grid rows times columns")
        for key in ("width", "height"): _positive_number(cells[key], recipe + ".cells." + key)
        _color(cells["fill"], recipe + ".cells.fill")
        if cells["fillType"] != "SOLID": raise ValueError(recipe + ".cells.fillType must use a solid color")
        _nonnegative_number(cells["redStep"], recipe + ".cells.redStep")
        if cells["fill"]["r"] + cells["redStep"] * (cells["count"] - 1) > 1:
            raise ValueError(recipe + ".cells red channel exceeds the normalized range")
    elif recipe == "design-motion":
        visual = _exact_fields(value, {"section", "frame", "dot", "transition"}, recipe)
        for section in ("section", "frame", "dot", "transition"):
            if not isinstance(visual[section], dict): raise ValueError(recipe + "." + section + " must be an object")
        for key in ("width", "height", "pageXOffset"): _positive_number(visual["section"][key], recipe + ".section." + key)
        frame = _exact_fields(visual["frame"], {"width", "height", "x", "y", "finishX"}, recipe + ".frame")
        for key in ("width", "height"): _positive_number(frame[key], recipe + ".frame." + key)
        for key in ("x", "y", "finishX"): _nonnegative_number(frame[key], recipe + ".frame." + key)
        dot = _exact_fields(visual["dot"], {"size", "x", "y", "finishX", "fillType", "fill"}, recipe + ".dot")
        _positive_number(dot["size"], recipe + ".dot.size")
        for key in ("x", "y", "finishX"): _nonnegative_number(dot[key], recipe + ".dot." + key)
        _color(dot["fill"], recipe + ".dot.fill")
        if dot["fillType"] != "SOLID": raise ValueError(recipe + ".dot.fillType must use a solid color")
        transition = _exact_fields(visual["transition"], {"type", "navigation", "trigger", "duration", "easing"}, recipe + ".transition")
        _positive_number(transition["duration"], recipe + ".transition.duration")
        if (transition["type"] != "SMART_ANIMATE" or transition["navigation"] != "NAVIGATE"
                or transition["trigger"] != "ON_CLICK" or transition["easing"] != "EASE_IN_AND_OUT"):
            raise ValueError(recipe + ".transition must remain the authored Smart Animate click example")
    elif recipe == "design-component-properties":
        visual = _exact_fields(value, {"frame", "label", "component", "componentSet", "symbol"}, recipe)
        frame = _exact_fields(visual["frame"], {"layoutMode", "primaryAxisSizing", "counterAxisSizing", "pageXOffset", "padding", "itemSpacing"}, recipe + ".frame")
        label = _exact_fields(visual["label"], {"fontFamily", "fontStyle", "fontSize"}, recipe + ".label")
        component = _exact_fields(visual["component"], {"layoutMode", "primaryAxisSizing", "counterAxisSizing", "padding", "itemSpacing"}, recipe + ".component")
        component_set = _exact_fields(visual["componentSet"], {"layoutMode", "primaryAxisSizing", "counterAxisSizing", "itemSpacing"}, recipe + ".componentSet")
        symbol = _exact_fields(visual["symbol"], {"size", "fillType", "fill"}, recipe + ".symbol")
        if frame["layoutMode"] != "VERTICAL" or component["layoutMode"] != "HORIZONTAL" or component_set["layoutMode"] != "HORIZONTAL":
            raise ValueError(recipe + " must use its authored auto-layout modes")
        for layout in (frame, component, component_set):
            if layout["primaryAxisSizing"] != "AUTO" or layout["counterAxisSizing"] != "AUTO":
                raise ValueError(recipe + " auto-layout sizing mode changed")
        for key in ("pageXOffset", "padding", "itemSpacing"): _positive_number(frame[key], recipe + ".frame." + key)
        for key in ("padding", "itemSpacing"): _positive_number(component[key], recipe + ".component." + key)
        _positive_number(component_set["itemSpacing"], recipe + ".componentSet.itemSpacing")
        for key in ("fontFamily", "fontStyle"):
            if not isinstance(label[key], str) or not label[key].strip(): raise ValueError(recipe + ".label." + key + " must be nonempty")
        _positive_number(label["fontSize"], recipe + ".label.fontSize")
        _positive_number(symbol["size"], recipe + ".symbol.size"); _color(symbol["fill"], recipe + ".symbol.fill")
        if symbol["fillType"] != "SOLID": raise ValueError(recipe + ".symbol.fillType must use a solid color")
    elif recipe == "design-type-review":
        visual = _exact_fields(value, {"frame", "layout", "font", "component", "textStyles", "metadata"}, recipe)
        frame = _exact_fields(visual["frame"], {"width", "height", "xOffset", "y"}, recipe + ".frame")
        for key, item in frame.items(): _positive_number(item, recipe + ".frame." + key)
        layout = _exact_fields(visual["layout"], {"mode", "primaryAxisSizing", "counterAxisSizing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "itemSpacing"}, recipe + ".layout")
        if layout["mode"] != "VERTICAL" or layout["primaryAxisSizing"] != "AUTO" or layout["counterAxisSizing"] != "FIXED":
            raise ValueError(recipe + ".layout must use the authored vertical specimen constraints")
        for key in ("paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "itemSpacing"):
            _nonnegative_number(layout[key], recipe + ".layout." + key)
        font = _exact_fields(visual["font"], {"preferred", "regularStylePattern", "strongStylePattern"}, recipe + ".font")
        if (not isinstance(font["preferred"], list) or not font["preferred"]
                or len(set(font["preferred"])) != len(font["preferred"])
                or any(not isinstance(name, str) or not name.strip() for name in font["preferred"])):
            raise ValueError(recipe + ".font.preferred must be a unique list of named font families")
        for key in ("regularStylePattern", "strongStylePattern"):
            if not isinstance(font[key], str) or not font[key].strip():
                raise ValueError(recipe + ".font." + key + " must be nonempty")
            try:
                re.compile(font[key], re.I)
            except re.error as error:
                raise ValueError(recipe + ".font." + key + " is not a valid style matcher") from error
        component = _exact_fields(visual["component"], {"cornerRadius", "strokeWeight", "dashPattern", "strokeOpacity", "strokeVisible", "strokeType", "backgroundType", "stroke", "background", "shadow"}, recipe + ".component")
        _positive_number(component["cornerRadius"], recipe + ".component.cornerRadius"); _positive_number(component["strokeWeight"], recipe + ".component.strokeWeight")
        if type(component["strokeOpacity"]) not in (int, float) or not 0 <= component["strokeOpacity"] <= 1: raise ValueError(recipe + ".component.strokeOpacity must be normalized")
        if component["strokeType"] != "SOLID" or component["backgroundType"] != "SOLID": raise ValueError(recipe + ".component paint types must remain solid")
        if type(component["strokeVisible"]) is not bool: raise ValueError(recipe + ".component.strokeVisible must be boolean")
        if not isinstance(component["dashPattern"], list) or not component["dashPattern"]: raise ValueError(recipe + ".component.dashPattern must be nonempty")
        for item in component["dashPattern"]: _nonnegative_number(item, recipe + ".component.dashPattern")
        _color(component["stroke"], recipe + ".component.stroke"); _color(component["background"], recipe + ".component.background")
        shadow = _exact_fields(component["shadow"], {"type", "color", "opacity", "offsetX", "offsetY", "radius", "spread", "visible", "blendMode"}, recipe + ".component.shadow")
        if shadow["type"] != "DROP_SHADOW" or type(shadow["visible"]) is not bool or shadow["blendMode"] != "NORMAL":
            raise ValueError(recipe + ".component.shadow type, visibility, or blend mode is unsupported")
        if type(shadow["opacity"]) not in (int, float) or not 0 <= shadow["opacity"] <= 1: raise ValueError(recipe + ".component.shadow.opacity must be normalized")
        _color(shadow["color"], recipe + ".component.shadow.color")
        for key in ("radius",): _nonnegative_number(shadow[key], recipe + ".component.shadow." + key)
        for key in ("offsetX", "offsetY", "spread"):
            if type(shadow[key]) not in (int, float) or not math.isfinite(shadow[key]): raise ValueError(recipe + ".component.shadow." + key + " must be finite")
        styles = _exact_fields(visual["textStyles"], {"display", "body", "caption"}, recipe + ".textStyles")
        for key, style in styles.items():
            style = _exact_fields(style, {"label", "sample", "fontSize", "lineHeight", "letterSpacing", "paintType", "fill"}, recipe + ".textStyles." + key)
            for field in ("label", "sample"):
                if not isinstance(style[field], str) or not style[field].strip(): raise ValueError(recipe + ".textStyles." + key + "." + field + " must be nonempty")
            for field in ("fontSize", "lineHeight"): _positive_number(style[field], recipe + ".textStyles." + key + "." + field)
            if type(style["letterSpacing"]) not in (int, float) or not math.isfinite(style["letterSpacing"]): raise ValueError(recipe + ".textStyles." + key + ".letterSpacing must be finite")
            _color(style["fill"], recipe + ".textStyles." + key + ".fill")
            if style["paintType"] != "SOLID": raise ValueError(recipe + ".textStyles." + key + ".paintType must be solid")
        metadata = _exact_fields(visual["metadata"], {"fontSize", "fillType", "fill"}, recipe + ".metadata")
        _positive_number(metadata["fontSize"], recipe + ".metadata.fontSize"); _color(metadata["fill"], recipe + ".metadata.fill")
        if metadata["fillType"] != "SOLID": raise ValueError(recipe + ".metadata.fillType must be solid")
    else:
        raise ValueError("Unknown visual recipe: " + recipe)


def validate_graph(graph: Any) -> dict[str, Any]:
    if (not isinstance(graph, dict) or set(graph) != {"schema", "version", "nodes", "edges"}
            or graph.get("schema") != SCHEMA or type(graph.get("version")) is not int or graph["version"] != 1
            or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list)):
        raise ValueError("Expected the version 1 recipe design graph")
    nodes = {}
    for node in graph["nodes"]:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or node["id"] in nodes:
            raise ValueError("Recipe design graph contains an invalid or duplicate node")
        nodes[node["id"]] = node
    roots = {node.get("recipe") for node in nodes.values() if node.get("type") == "recipe"}
    if roots != RECIPE_IDS:
        raise ValueError("Recipe design graph must define exactly the five manifest recipes")
    values: dict[str, dict[str, Any]] = {}
    payloads = []
    for node in nodes.values():
        kind, recipe = node.get("type"), node.get("recipe")
        if kind == "recipe":
            if set(node) != {"id", "type", "recipe", "entry"} or node["id"] != "recipe:" + recipe or node["entry"] != recipe + ".ts":
                raise ValueError("Recipe root does not match the manifest entry")
        elif kind == "visual":
            if set(node) != {"id", "type", "recipe", "values"} or recipe not in RECIPE_IDS or node["id"] != "visual:" + recipe or recipe in values:
                raise ValueError("Recipe visual node must be a unique recipe-owned record")
            _validate_visual(recipe, node["values"])
            values[recipe] = node["values"]
        elif kind == "payload":
            if set(node) != {"id", "type", "recipe", "values"} or recipe != "design-component-properties" or node["id"] != "payload:declared-component-properties" or payloads:
                raise ValueError("Only the component-properties example can own a payload node")
            if not isinstance(node["values"], dict): raise ValueError("Component property payload must be an object")
            payloads.append(node["values"])
        else:
            raise ValueError("Unsupported recipe design graph node type")
    if set(values) != RECIPE_IDS or len(payloads) != 1:
        raise ValueError("Recipe graph is missing a visual record or declared component payload")
    expected_edges = {("recipe:" + recipe, "visual:" + recipe, "owns-visual-values") for recipe in RECIPE_IDS}
    expected_edges.add(("recipe:design-component-properties", "payload:declared-component-properties", "owns-design-payload"))
    actual_edges = set()
    for edge in graph["edges"]:
        if (not isinstance(edge, dict) or set(edge) != {"from", "to", "type"}
                or edge["from"] not in nodes or edge["to"] not in nodes):
            raise ValueError("Recipe design graph contains a malformed or dangling edge")
        actual_edges.add((edge["from"], edge["to"], edge["type"]))
    if actual_edges != expected_edges:
        raise ValueError("Recipe design graph relationships do not match its visual ownership")
    return {"visuals": values, "componentPayload": payloads[0]}


def load_graph(path: str | Path = GRAPH_PATH) -> dict[str, Any]:
    return validate_graph(parse_graph(Path(path).read_bytes()))


def graph_bytes(path: str | Path = GRAPH_PATH) -> bytes:
    return Path(path).read_bytes()


def graph_sha256(path: str | Path = GRAPH_PATH) -> str:
    return hashlib.sha256(graph_bytes(path)).hexdigest()


def typescript_projection(graph: dict[str, Any], recipe_ids: set[str] | None = None) -> str:
    validated = validate_graph(graph)
    selected = RECIPE_IDS if recipe_ids is None else recipe_ids
    if not selected or not selected <= RECIPE_IDS:
        raise ValueError("Visual projection requires one or more registered recipes")
    values = {key: validated["visuals"][key] for key in sorted(selected)}
    return "/* GENERATED from design-examples.graph.json; edit the canonical graph only. */\nconst RECIPE_VISUALS = " + json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2) + " as const;\n"


def payload_projection(graph: dict[str, Any]) -> str:
    return canonical(validate_graph(graph)["componentPayload"])
