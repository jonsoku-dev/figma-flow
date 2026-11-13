#!/usr/bin/env python3
"""Prepare a bounded read-only probe from pinned Figma node property declarations."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from figma_api_inventory import inherited_members, load as load_catalog
import api_priority

AUDIT_PATH = ROOT / 'library' / 'figma-api' / 'audit' / 'members.json'
AUDIT_CANDIDATE_RELEASE = '0.28.0'
SELECTION_SCHEMA = 'figma-flow-native-api-probe-selection-v1'
READBACK_SCHEMA = 'figma-flow-graph-native-discovery-v1'
CONFIG_SCHEMA = 'figma-flow-native-api-probe-config-v1'
MAX_TARGETS = 24
MAX_CANDIDATES_PER_TYPE = 16
MAX_ELIGIBLE_PER_TYPE = 64
AUDIT_MEMBER_COUNT = 1382
MAX_GETTERS = MAX_TARGETS * MAX_CANDIDATES_PER_TYPE
MAX_ELAPSED_MS = 3000
MAX_ANCESTORS = 32
NODE_ID = re.compile(r'(?:I?\d+:\d+)(?:;\d+:\d+)*\Z')
SAFE_TYPES = {'FRAME': 'FrameNode', 'ELLIPSE': 'EllipseNode',
              'BOOLEAN_OPERATION': 'BooleanOperationNode', 'SECTION': 'SectionNode',
              'INSTANCE': 'InstanceNode', 'COMPONENT': 'ComponentNode',
              'TEXT': 'TextNode', 'RECTANGLE': 'RectangleNode', 'COMPONENT_SET': 'ComponentSetNode',
              'GROUP': 'GroupNode', 'VECTOR': 'VectorNode', 'DOCUMENT': 'DocumentNode',
              'PAGE': 'PageNode', 'SLICE': 'SliceNode',
              'LINE': 'LineNode', 'POLYGON': 'PolygonNode', 'STAR': 'StarNode',
              'TEXT_PATH': 'TextPathNode', 'SLOT': 'SlotNode'}

# These fields are safe scalar, geometry, layout, or solid-color foundations.
# Every entry still requires a matching unresolved PropertySignature in the audit.
SAFE_FIELDS = {
    # High-ranked native scalar properties with useful observed receivers.
    # Keep style identities, variable maps, geometry payloads and nested node
    # collections out of the readback; these candidates expose only scalars.
    'hasMissingFont': ('text-style', 'boolean', 0, ('TEXT',)),
    'fontWeight': ('text-style', 'font-weight-range', 0, ('TEXT',)),
    'textWrapStyle': ('text-style', 'enum', 0, ('TEXT',)),
    'textDecorationStyle': ('text-style', 'enum', 0, ('TEXT',)),
    'minWidth': ('layout', 'nullable-number', 1),
    'maxWidth': ('layout', 'nullable-number', 1),
    'minHeight': ('layout', 'nullable-number', 1),
    'maxHeight': ('layout', 'nullable-number', 1),
    'layoutGrow': ('layout', 'number', 1),
    'layoutPositioning': ('layout', 'enum', 1),
    'layoutAlign': ('layout', 'enum', 1),
    'strokesIncludedInLayout': ('layout', 'boolean', 1),
    'cornerSmoothing': ('appearance', 'number', 2),
    'constrainProportions': ('layout', 'boolean', 2),
    'maskType': ('appearance', 'enum', 2),
    'targetAspectRatio': ('geometry', 'nullable-number', 2),
    'gridColumnSpan': ('grid', 'number', 2),
    'gridRowSpan': ('grid', 'number', 2),
    'gridChildHorizontalAlign': ('grid', 'enum', 2),
    'gridChildVerticalAlign': ('grid', 'enum', 2),
    'gridColumnAnchorIndex': ('grid', 'number', 2),
    'gridRowAnchorIndex': ('grid', 'number', 2),
    'isAsset': ('state', 'boolean', 3),
    'removed': ('state', 'boolean', 3),
    # Opaque identifiers are reduced to state. Collection-valued properties
    # expose counts or a small enum summary, never their contents or identities.
    'fillStyleId': ('appearance', 'style-state', 0),
    'effectStyleId': ('appearance', 'style-state', 0),
    'strokeStyleId': ('appearance', 'style-state', 0),
    'backgroundStyleId': ('appearance', 'style-state', 1),
    'gridStyleId': ('layout', 'style-state', 1),
    'textStyleId': ('text-style', 'style-state', 0, ('TEXT',)),
    'exportSettings': ('export', 'bounded-count', 1),
    'animationStyles': ('motion', 'bounded-count', 1),
    'explicitVariableModes': ('variables', 'map-count', 1),
    'inferredVariables': ('variables', 'map-count', 1),
    'constraints': ('layout', 'constraints-summary', 1),
    'layoutGrids': ('layout', 'layout-grid-summary', 1),
    'strokeGeometry': ('geometry', 'bounded-count', 2),
    'fillGeometry': ('geometry', 'bounded-count', 2),
    'numberOfFixedChildren': ('prototype', 'number', 2),
    'textTruncation': ('text-style', 'enum', 2, ('TEXT',)),
    'booleanOperation': ('shape', 'enum', 0, ('BOOLEAN_OPERATION',)),
    'sectionContentsHidden': ('section', 'boolean', 0, ('SECTION',)),
    'arcData': ('ellipse', 'arc', 0, ('ELLIPSE',)),
    'scaleFactor': ('instance', 'number', 0, ('INSTANCE',)),
    'isExposedInstance': ('instance', 'boolean', 1, ('INSTANCE',)),
    'textCase': ('text-style', 'enum', 0, ('TEXT',)),
    'textDecoration': ('text-style', 'enum', 0, ('TEXT',)),
    'textAutoResize': ('text-style', 'enum', 0, ('TEXT',)),
    'textAlignVertical': ('text-style', 'enum', 0, ('TEXT',)),
    'paragraphIndent': ('text-style', 'number', 0, ('TEXT',)),
    'paragraphSpacing': ('text-style', 'number', 0, ('TEXT',)),
    'maxLines': ('text-style', 'nullable-number', 0, ('TEXT',)),
    'gridRowCount': ('grid', 'number', 1),
    'gridColumnCount': ('grid', 'number', 1),
    'gridRowGap': ('grid', 'number', 1),
    'gridColumnGap': ('grid', 'number', 1),
    'gridAutoTracks': ('grid', 'enum', 1),
    'gridItemsPositioning': ('grid', 'enum', 1),
    'layoutSizingHorizontal': ('layout', 'enum', 2),
    'layoutSizingVertical': ('layout', 'enum', 2),
    'layoutMode': ('layout', 'enum', 2),
    'layoutWrap': ('layout', 'enum', 2),
    'primaryAxisSizingMode': ('layout', 'enum', 2),
    'counterAxisSizingMode': ('layout', 'enum', 2),
    'primaryAxisAlignItems': ('layout', 'enum', 2),
    'counterAxisAlignItems': ('layout', 'enum', 2),
    'counterAxisSpacing': ('layout', 'number', 2),
    'horizontalPadding': ('layout', 'number', 2),
    'verticalPadding': ('layout', 'number', 2),
    'paddingLeft': ('layout', 'number', 2),
    'paddingTop': ('layout', 'number', 2),
    'paddingRight': ('layout', 'number', 2),
    'paddingBottom': ('layout', 'number', 2),
    'itemSpacing': ('layout', 'number', 2),
    'locked': ('state', 'boolean', 3),
    'opacity': ('appearance', 'number', 3),
    'strokeWeight': ('appearance', 'number', 3),
    'strokeAlign': ('appearance', 'enum', 3),
    'strokeCap': ('appearance', 'enum', 3),
    'strokeJoin': ('appearance', 'enum', 3),
    'strokeMiterLimit': ('appearance', 'number', 3),
    'dashPattern': ('appearance', 'number-list', 3),
    'blendMode': ('appearance', 'enum', 3),
    'visible': ('state', 'boolean', 3),
    'isMask': ('state', 'boolean', 3),
    'clipsContent': ('state', 'boolean', 3),
    'cornerRadius': ('appearance', 'number', 3),
    'topLeftRadius': ('appearance', 'number', 3, ('RECTANGLE', 'COMPONENT_SET')),
    'topRightRadius': ('appearance', 'number', 3, ('RECTANGLE', 'COMPONENT_SET')),
    'bottomLeftRadius': ('appearance', 'number', 3, ('RECTANGLE', 'COMPONENT_SET')),
    'bottomRightRadius': ('appearance', 'number', 3, ('RECTANGLE', 'COMPONENT_SET')),
    'fills': ('appearance', 'solid-paints', 3),
    'strokes': ('appearance', 'solid-paints', 3),
    'absoluteRenderBounds': ('geometry', 'rect', 4),
    'relativeTransform': ('geometry', 'matrix', 4),
    'absoluteTransform': ('geometry', 'matrix', 4),
    'x': ('geometry', 'number', 4),
    'y': ('geometry', 'number', 4),
    'width': ('geometry', 'number', 4),
    'height': ('geometry', 'number', 4),
    'rotation': ('geometry', 'number', 4),
    # Additional Design receivers and scalar or identity-free summaries.
    'type': ('state', 'enum', 0),
    'documentColorProfile': ('state', 'enum', 0, ('DOCUMENT',)),
    'selection': ('state', 'bounded-count', 1, ('PAGE',)),
    'prototypeStartNode': ('prototype', 'reference-state', 1, ('PAGE',)),
    'isPageDivider': ('prototype', 'boolean', 2, ('PAGE',)),
    'children': ('structure', 'bounded-count', 2, ('DOCUMENT',)),
    'backgrounds': ('appearance', 'solid-paints', 2, ('PAGE', 'COMPONENT', 'COMPONENT_SET', 'FRAME', 'GROUP', 'INSTANCE', 'SLOT')),
    'prototypeBackgrounds': ('appearance', 'solid-paints', 2, ('PAGE',)),
    'flowStartingPoints': ('prototype', 'bounded-count', 2, ('PAGE',)),
    'guides': ('layout', 'bounded-count', 2, ('PAGE', 'COMPONENT', 'COMPONENT_SET', 'FRAME', 'INSTANCE', 'SLOT')),
    'exposedInstances': ('component', 'bounded-count', 2, ('INSTANCE',)),
    'documentationLinks': ('component', 'bounded-count', 2, ('COMPONENT', 'COMPONENT_SET')),
    'strokeTopWeight': ('appearance', 'number', 2, ('COMPONENT', 'COMPONENT_SET', 'FRAME', 'INSTANCE', 'RECTANGLE')),
    'strokeRightWeight': ('appearance', 'number', 2, ('COMPONENT', 'COMPONENT_SET', 'FRAME', 'INSTANCE', 'RECTANGLE')),
    'strokeBottomWeight': ('appearance', 'number', 2, ('COMPONENT', 'COMPONENT_SET', 'FRAME', 'INSTANCE', 'RECTANGLE')),
    'strokeLeftWeight': ('appearance', 'number', 2, ('COMPONENT', 'COMPONENT_SET', 'FRAME', 'INSTANCE', 'RECTANGLE')),
    'variableWidthStrokeProperties': ('appearance', 'bounded-object-summary', 2),
    'complexStrokeProperties': ('appearance', 'bounded-object-summary', 2),
    'inferredAutoLayout': ('layout', 'layout-summary', 2),
    'animations': ('motion', 'map-count', 2),
    'manualKeyframeTracks': ('motion', 'map-count', 2),
    'timelines': ('motion', 'bounded-count', 2),
    'expanded': ('state', 'boolean', 2, ('BOOLEAN_OPERATION', 'COMPONENT', 'COMPONENT_SET', 'FRAME', 'GROUP', 'INSTANCE', 'SLOT')),
    'devStatus': ('state', 'bounded-object-summary', 2, ('COMPONENT', 'COMPONENT_SET', 'FRAME', 'INSTANCE', 'SECTION', 'SLOT')),
    'counterAxisAlignContent': ('layout', 'enum', 2),
    'itemReverseZIndex': ('layout', 'boolean', 2),
    'gridRowSizes': ('layout', 'grid-track-summary', 2),
    'gridColumnSizes': ('layout', 'grid-track-summary', 2),
    'detachedInfo': ('component', 'reference-state', 2),
    'overlayBackgroundInteraction': ('prototype', 'enum', 2),
    'overlayPositionType': ('prototype', 'enum', 2),
    'overflowDirection': ('prototype', 'enum', 2),
    'overlayBackground': ('prototype', 'bounded-object-summary', 2),
    'textDecorationStyle': ('text-style', 'mixed-enum', 1, ('TEXT',)),
    'textAlignHorizontal': ('text-style', 'enum', 1, ('TEXT_PATH',)),
    'textAlignVertical': ('text-style', 'enum', 1, ('TEXT_PATH',)),
    'textDecorationColor': ('text-style', 'decoration-color', 1, ('TEXT',)),
    'textDecorationThickness': ('text-style', 'unit-value', 1, ('TEXT',)),
    'textDecorationOffset': ('text-style', 'unit-value', 1, ('TEXT',)),
    'textDecorationSkipInk': ('text-style', 'mixed-boolean', 1, ('TEXT',)),
    'lineHeight': ('text-style', 'unit-value', 1, ('TEXT',)),
    'letterSpacing': ('text-style', 'unit-value', 1, ('TEXT',)),
    'openTypeFeatures': ('text-style', 'mixed-map-count', 2),
    'hyperlink': ('text-style', 'reference-state', 2),
    'hangingList': ('text-style', 'boolean', 2, ('TEXT',)),
    'hangingPunctuation': ('text-style', 'boolean', 2, ('TEXT',)),
    'leadingTrim': ('text-style', 'enum', 2, ('TEXT',)),
    'listSpacing': ('text-style', 'mixed-number', 2, ('TEXT',)),
    'handleMirroring': ('geometry', 'mixed-enum', 2, ('TEXT_PATH', 'VECTOR')),
    'autoRename': ('state', 'boolean', 2, ('TEXT', 'TEXT_PATH')),
    'description': ('component', 'string-state', 2),
    'descriptionMarkdown': ('component', 'string-state', 2),
    'remote': ('component', 'boolean', 2),
    'key': ('component', 'style-state', 2),
    'variantProperties': ('component', 'map-count', 2),
    'defaultVariant': ('component', 'reference-state', 2, ('COMPONENT_SET',)),
    'variantGroupProperties': ('component', 'map-count', 2, ('COMPONENT_SET',)),
    'textStyleId': ('text-style', 'style-state', 2, ('TEXT', 'TEXT_PATH')),
    'textPathStartData': ('geometry', 'bounded-object-summary', 2, ('TEXT_PATH',)),
    'selectedTextRange': ('text-style', 'range-state', 2, ('PAGE',)),
    'vectorPaths': ('geometry', 'bounded-count', 2, ('TEXT_PATH', 'VECTOR')),
    'vectorNetwork': ('geometry', 'vector-summary', 2, ('TEXT_PATH', 'VECTOR')),
    'attachedConnectors': ('prototype', 'bounded-count', 2),
    'pointCount': ('geometry', 'number', 2, ('POLYGON', 'STAR')),
    'innerRadius': ('geometry', 'number', 2, ('STAR',)),
    'limitViolations': ('component', 'bounded-count', 2, ('SLOT',)),
}

# Methods are called only through explicit static branches in the bridge runtime.
# Text range methods derive their bounds from characters.length without emitting the text.
SAFE_METHODS = {
    'getCSSAsync': ('css', 'css-summary', 0, ('*',)),
    'getRangeFontName': ('text-style', 'font-range', 0, ('TEXT',)),
    'getRangeFontSize': ('text-style', 'font-size-range', 0, ('TEXT',)),
    'getRangeFontWeight': ('text-style', 'font-weight-range', 0, ('TEXT',)),
    'getRangeFills': ('text-style', 'solid-paints', 0, ('TEXT',)),
    'getMainComponentAsync': ('component', 'reference-state', 0, ('INSTANCE',)),
    'getInstancesAsync': ('component', 'bounded-count', 0, ('COMPONENT',)),
}


def _audit_rows(catalog, audit):
    source = catalog['source']
    candidate = audit.get('comparison', {}).get('candidate', {})
    if (audit.get('schema') != 'figma-flow-plugin-api-member-audit-v1'
            or len(audit.get('members', [])) != AUDIT_MEMBER_COUNT
            or audit.get('counts', {}).get('members') != AUDIT_MEMBER_COUNT
            or candidate.get('api_catalog_member_count') != AUDIT_MEMBER_COUNT
            or candidate.get('plugin_version') != AUDIT_CANDIDATE_RELEASE
            or candidate.get('api_source_ref') != source.get('ref')
            or candidate.get('api_source_version') != source.get('version')
            or candidate.get('api_source_files') != source.get('files')):
        raise ValueError('The unresolved-candidate audit does not match the pinned official API catalog.')
    result = {}
    for row in audit.get('members', []):
        result.setdefault((row.get('owner'), row.get('name'), row.get('signature')), []).append(row)
    return result


def _node_types(catalog):
    result = {}
    for row in catalog['nodes']:
        match = re.fullmatch(r"(?:readonly )?type: ['\"]([A-Z_]+)['\"]", row['type_signatures'][0]) if row.get('type_signatures') else None
        if match:
            result[match.group(1)] = row['name']
    return result


def candidates_for_type(catalog, audit_rows, node_type, *, include_observed=False):
    node_interface = SAFE_TYPES.get(node_type)
    if node_interface is None or _node_types(catalog).get(node_type) != node_interface:
        return []
    members = inherited_members(catalog, node_interface)
    ancestors = {node_interface}
    declarations = {row['name']: row for row in catalog['declarations']}
    pending = [node_interface]
    while pending:
        name = pending.pop()
        for base in declarations.get(name, {}).get('extends', []):
            if base not in ancestors:
                ancestors.add(base)
                pending.append(base)
    depth = {node_interface: 0}
    pending_depth = [node_interface]
    while pending_depth:
        name = pending_depth.pop(0)
        for base in declarations.get(name, {}).get('extends', []):
            next_depth = depth[name] + 1
            if base not in depth or next_depth < depth[base]:
                depth[base] = next_depth
                pending_depth.append(base)
    by_name = {}
    for member in members:
        access = 'property' if member.get('kind') == 'PropertySignature' and member.get('name') in SAFE_FIELDS else (
            'method' if member.get('kind') == 'MethodSignature' and member.get('name') in SAFE_METHODS else None)
        if access is None:
            continue
        docs = member.get('documentation', '')
        if (not isinstance(docs, str) or not docs.strip() or member.get('restricted_access')
                or member.get('required_permissions')
                or re.search(r'proposed\s+api|private\s+api|enablePrivatePluginApi', docs, re.I)
                or (member.get('documented_editors') and 'figma' not in member['documented_editors'])):
            continue
        audited = audit_rows.get((member['owner'], member['name'], member['signature']), [])
        eligible_audit_rows = [row for row in audited
                               if row.get('kind') == member.get('kind')
                               and (row.get('release_status', {}).get('candidate', {}).get('status') == 'unresolved'
                                    or (include_observed and row.get('release_status', {}).get('candidate', {}).get('status') == 'observed'))]
        if not eligible_audit_rows:
            continue
        selected = member
        field_policy = SAFE_FIELDS[member['name']] if access == 'property' else SAFE_METHODS[member['name']]
        foundation, value_kind, priority = field_policy[:3]
        allowed_receivers = field_policy[3] if len(field_policy) == 4 else ('*',)
        if '*' not in allowed_receivers and node_type not in allowed_receivers:
            continue
        by_name.setdefault(member['name'], []).append({
            'api_member_id': eligible_audit_rows[0]['key'],
            'official_member_id': member['id'],
            'owner': member['owner'],
            'property': member['name'],
            'signature': member['signature'],
            'foundation': foundation,
            'value_kind': value_kind,
            'receiver_type': node_type,
            'allowed_receivers': list(allowed_receivers),
            'audit_status': 'unresolved',
            'audit_release': AUDIT_CANDIDATE_RELEASE,
            'access': access,
            '_priority': priority,
            '_depth': depth.get(selected['owner'], 999),
        })
    selected = [min(rows, key=lambda row: (row['_depth'], row['official_member_id']))
                for rows in by_name.values()]
    selected.sort(key=lambda row: (row['_priority'], row['_depth'], row['property'], row['official_member_id']))
    return [{key: value for key, value in row.items() if not key.startswith('_')} for row in selected]


def _safe_semantic_id(value):
    return (isinstance(value, str) and 1 <= len(value) <= 160 and value.strip() == value
            and not any(ord(char) < 32 or ord(char) == 127 for char in value)
            and not re.search(r'\bBearer\s+\S{16,}|\bsk-[A-Za-z0-9_-]{16,}', value))


def _readback_timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed > datetime.now(timezone.utc):
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _previous_statuses(previous, file_key, page_id, selected):
    if (not isinstance(previous, dict) or previous.get('schema') != READBACK_SCHEMA
            or previous.get('fileKey') != file_key or previous.get('pageId') != page_id
            or not _readback_timestamp(previous.get('observed_at'))):
        return None
    probe = previous.get('api_probe')
    if not isinstance(probe, dict) or probe.get('schema') != 'figma-flow-native-api-probe-v1':
        return None
    selected_keys = {(row['semantic_id'], row['observed_node_id']) for row in selected}
    result = {}
    observations = probe.get('observations')
    if not isinstance(observations, list) or len(observations) > MAX_GETTERS:
        return None
    for row in observations:
        allowed = {'semantic_id', 'observed_node_id', 'observed_type', 'api_member_id', 'official_member_id',
                   'owner', 'property', 'signature', 'foundation', 'status', 'previous_status', 'delta', 'value', 'reason'}
        if (not isinstance(row, dict) or not set(row) <= allowed
                or (row.get('semantic_id'), row.get('observed_node_id')) not in selected_keys
                or not isinstance(row.get('api_member_id'), str)
                or row.get('status') not in {'success', 'unavailable', 'unsupported', 'blocked'}):
            return None
        key = (row['semantic_id'], row['observed_node_id'], row['api_member_id'])
        if key in result:
            return None
        result[key] = row['status']
    return {'observed_at': _readback_timestamp(previous['observed_at']), 'statuses': result,
            'auditRelease': probe.get('auditRelease'), 'apiSource': probe.get('apiSource'),
            'auditSha256': probe.get('auditSha256'), 'fieldPolicySha256': probe.get('fieldPolicySha256'),
            'selectionSha256': probe.get('selectionSha256'),
            'comparable': True, 'reason': None}


def prepare(selection, *, file_key, page_id, catalog=None, audit=None, previous_readback=None,
            candidate_offset=None):
    """Build a fixed allowlisted plan; this function never invokes Figma APIs."""
    catalog = catalog or load_catalog()
    if audit is None:
        raw_audit = AUDIT_PATH.read_bytes()
        audit = json.loads(raw_audit)
        audit_sha = hashlib.sha256(raw_audit).hexdigest()
    else:
        audit_sha = hashlib.sha256(json.dumps(audit, ensure_ascii=False, sort_keys=True,
                                             separators=(',', ':')).encode()).hexdigest()
    audit_rows = _audit_rows(catalog, audit)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', str(file_key)) or not re.fullmatch(r'\d+:\d+', str(page_id)):
        raise ValueError('A file key and page ID are required to bind the probe request.')
    if (not isinstance(selection, dict) or selection.get('schema') != SELECTION_SCHEMA
            or set(selection) - {'schema', 'fileKey', 'pageId', 'nodes', 'previous_readback',
                                 'candidate_offset', 'recheck_member_ids', 'candidate_member_ids'}):
        raise ValueError('Expected a figma-flow-native-api-probe-selection-v1 request.')
    if selection.get('fileKey') != file_key or selection.get('pageId') != page_id:
        raise ValueError('Probe selection file/page differs from the admitted discovery scope.')
    selected = selection.get('nodes')
    if not isinstance(selected, list) or not 1 <= len(selected) <= MAX_TARGETS:
        raise ValueError(f'Select 1–{MAX_TARGETS} exact previously observed scene nodes.')
    offset = selection.get('candidate_offset', 0) if candidate_offset is None else candidate_offset
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 or offset % MAX_CANDIDATES_PER_TYPE:
        raise ValueError(f'Candidate batch offset must be a nonnegative multiple of {MAX_CANDIDATES_PER_TYPE}.')
    seen_semantic, seen_native = set(), set()
    targets, eligible_by_type, candidates_by_type, eligibility_by_type = [], {}, {}, {}
    inventory = api_priority.build(include_public_overlays=True)
    if 'recheck_member_ids' in selection and 'candidate_member_ids' in selection:
        raise ValueError('Choose either an observed-key recheck or a targeted candidate batch.')
    if 'recheck_member_ids' in selection:
        requested = selection['recheck_member_ids']
        if (not isinstance(requested, list) or not 1 <= len(requested) <= MAX_CANDIDATES_PER_TYPE
                or not all(isinstance(key, str) for key in requested) or len(set(requested)) != len(requested)):
            raise ValueError('Recheck requires unique exact member keys in a single bounded batch.')
        admitted = {row['api_member_id']: row for row in inventory['rows']
                    if row['evidence_status'] in ('observed', 'observed-in-observation-graph')}
        if any(key not in admitted for key in requested) or offset:
            raise ValueError('Recheck requires previously observed audit keys and offset zero.')
        ranked_rows = [admitted[key] for key in requested]
    elif 'candidate_member_ids' in selection:
        requested = selection['candidate_member_ids']
        if (not isinstance(requested, list) or not 1 <= len(requested) <= MAX_CANDIDATES_PER_TYPE
                or not all(isinstance(key, str) for key in requested) or len(set(requested)) != len(requested)):
            raise ValueError('Targeted candidates require unique exact member keys in a single bounded batch.')
        admitted = {row['api_member_id']: row for row in api_priority.queue(
            inventory, limit=None, feasible_only=True)}
        if any(key not in admitted for key in requested) or offset:
            raise ValueError('Targeted candidates must be unresolved feasible audit keys and use offset zero.')
        ranked_rows = [admitted[key] for key in requested]
    else:
        ranked_rows = api_priority.queue(inventory, limit=None, feasible_only=True)
    priority_order = {row['api_member_id']: index for index, row in enumerate(ranked_rows)}
    priority_by_id = {row['api_member_id']: row for row in ranked_rows}
    if not priority_order:
        raise ValueError('The validated priority queue has no remaining feasible API members.')
    for row in selected:
        if (not isinstance(row, dict) or set(row) != {'semantic_id', 'observed_node_id', 'observed_type'}
                or not _safe_semantic_id(row.get('semantic_id'))
                or not isinstance(row.get('observed_node_id'), str) or not NODE_ID.fullmatch(row['observed_node_id'])
                or row.get('observed_type') not in SAFE_TYPES
                or row['semantic_id'] in seen_semantic or row['observed_node_id'] in seen_native):
            raise ValueError('Each selected item needs unique exact semantic_id, observed_node_id, and a supported observed_type.')
        seen_semantic.add(row['semantic_id'])
        seen_native.add(row['observed_node_id'])
        if row['observed_type'] not in eligible_by_type:
            candidates = candidates_for_type(catalog, audit_rows, row['observed_type'],
                include_observed='recheck_member_ids' in selection)
            ordered = sorted(
                (candidate for candidate in candidates if candidate['api_member_id'] in priority_order),
                key=lambda candidate: priority_order[candidate['api_member_id']])
            eligible_by_type[row['observed_type']] = [{**candidate,
                'priority_score': priority_by_id[candidate['api_member_id']]['priority_score'],
                'feasibility': priority_by_id[candidate['api_member_id']]['feasibility'],
                'priority_reasons': priority_by_id[candidate['api_member_id']]['priority_reasons'],
                'role_matches': priority_by_id[candidate['api_member_id']]['role_matches']}
                for candidate in ordered]
        all_candidates = eligible_by_type[row['observed_type']]
        if len(all_candidates) > MAX_ELIGIBLE_PER_TYPE:
            raise ValueError(f'{row["observed_type"]} has more than {MAX_ELIGIBLE_PER_TYPE} eligible getters; narrow the probe policy.')
        batch = candidates_by_type.setdefault(row['observed_type'], all_candidates[offset:offset + MAX_CANDIDATES_PER_TYPE])
        eligibility_by_type[row['observed_type']] = {
            'eligible': len(all_candidates), 'offset': offset, 'planned': len(batch),
            'remaining_after_batch': max(0, len(all_candidates) - offset - len(batch)),
            'status': ('no-candidate' if not all_candidates else 'batch-empty' if offset >= len(all_candidates)
                       else 'batch-ready' if offset + len(batch) < len(all_candidates) else 'last-batch'),
            'staticBatchEnd': offset >= len(all_candidates) or offset + len(batch) >= len(all_candidates),
        }
        targets.append({'semantic_id': row['semantic_id'], 'observed_node_id': row['observed_node_id'],
                        'observed_type': row['observed_type']})
    total = sum(len(candidates_by_type[row['observed_type']]) for row in targets)
    if total > MAX_GETTERS:
        raise ValueError('Selected API probe exceeds the getter-call budget.')
    previous_readback = previous_readback if previous_readback is not None else selection.get('previous_readback')
    previous = _previous_statuses(previous_readback, file_key, page_id, targets)
    if previous_readback is not None and previous is None:
        raise ValueError('Previous readback must have a valid actual receipt timestamp and match the exact file/page scope.')
    api_source = {'version': catalog['source']['version'], 'ref': catalog['source']['ref']}
    if 'recheck_member_ids' in selection or 'candidate_member_ids' in selection:
        requested = selection.get('recheck_member_ids', selection.get('candidate_member_ids', []))
        reachable = {item['api_member_id'] for items in candidates_by_type.values() for item in items}
        if set(requested) != reachable:
            raise ValueError('Requested member keys must be supported by the selected receivers and static projection policy.')
    field_policy = {name: {'foundation': values[0], 'value_kind': values[1], 'priority': values[2],
                           'allowed_receivers': list(values[3]) if len(values) == 4 else ['*'],
                           'access': 'property'} for name, values in SAFE_FIELDS.items()}
    field_policy.update({name: {'foundation': values[0], 'value_kind': values[1], 'priority': values[2],
                                'allowed_receivers': list(values[3]), 'access': 'method'}
                         for name, values in SAFE_METHODS.items()})
    field_policy_sha = hashlib.sha256(json.dumps(field_policy, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    selection_sha = hashlib.sha256(json.dumps(targets, ensure_ascii=False, sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
    if previous is not None:
        old_probe = previous_readback.get('api_probe', {})
        if (old_probe.get('auditRelease') != AUDIT_CANDIDATE_RELEASE
                or old_probe.get('apiSource') != api_source or old_probe.get('auditSha256') != audit_sha
                or old_probe.get('fieldPolicySha256') != field_policy_sha
                or old_probe.get('selectionSha256') != selection_sha or previous.get('comparable') is False):
            previous.update(statuses={}, comparable=False, reason='catalog-or-selection-hash-mismatch')
        else:
            previous.update(comparable=True, reason=None)
    return {
        'schema': CONFIG_SCHEMA,
        'fileKey': file_key,
        'pageId': page_id,
        'auditRelease': AUDIT_CANDIDATE_RELEASE,
        'apiSource': api_source,
        'auditSha256': audit_sha,
        'fieldPolicy': field_policy,
        'fieldPolicySha256': field_policy_sha,
        'nodeTypeInterfaces': {node_type: SAFE_TYPES[node_type]
                               for node_type in sorted({row['observed_type'] for row in targets})},
        'selectionSha256': selection_sha,
        'candidateOffset': offset,
        'targets': targets,
        'candidatesByType': candidates_by_type,
        'eligibleByType': eligible_by_type,
        'eligibilityByType': eligibility_by_type,
        'previous': None if previous is None else {'observed_at': previous['observed_at'],
            'auditRelease': previous['auditRelease'], 'apiSource': previous['apiSource'],
            'auditSha256': previous['auditSha256'], 'fieldPolicySha256': previous['fieldPolicySha256'],
            'selectionSha256': previous['selectionSha256'],
            'comparable': previous['comparable'], 'reason': previous['reason'],
            'statuses': [{'semantic_id': semantic, 'observed_node_id': native, 'api_member_id': member,
                          'status': status}
                         for (semantic, native, member), status in sorted(previous['statuses'].items())]},
        'budget': {'max_targets': MAX_TARGETS, 'max_candidates_per_type': MAX_CANDIDATES_PER_TYPE,
                   'max_getters': MAX_GETTERS, 'max_elapsed_ms': MAX_ELAPSED_MS,
                   'max_ancestor_checks_per_target': MAX_ANCESTORS,
                   'planned_getters': total},
    }


def normalize_selection(selection, *, file_key, page_id, catalog=None, audit=None, previous_readback=None,
                        candidate_offset=None):
    """Validate and return the small selection request accepted by `discover --api-probe`."""
    config = prepare(selection, file_key=file_key, page_id=page_id, catalog=catalog, audit=audit,
                     previous_readback=previous_readback, candidate_offset=candidate_offset)
    result = {'schema': SELECTION_SCHEMA, 'fileKey': file_key, 'pageId': page_id,
              'nodes': config['targets']}
    result['candidate_offset'] = config['candidateOffset']
    if 'recheck_member_ids' in selection:
        result['recheck_member_ids'] = list(selection['recheck_member_ids'])
    if 'candidate_member_ids' in selection:
        result['candidate_member_ids'] = list(selection['candidate_member_ids'])
    if config['previous'] is not None:
        result['previous_readback'] = {'schema': READBACK_SCHEMA, 'fileKey': file_key, 'pageId': page_id,
            'observed_at': config['previous']['observed_at'],
            'api_probe': {'schema': 'figma-flow-native-api-probe-v1',
                'auditRelease': config['previous']['auditRelease'], 'apiSource': config['previous']['apiSource'],
                'auditSha256': config['previous']['auditSha256'],
                'fieldPolicySha256': config['previous']['fieldPolicySha256'],
                'selectionSha256': config['previous']['selectionSha256'],
                'previousComparable': config['previous']['comparable'],
                'previousReason': config['previous']['reason'],
                'observations': config['previous']['statuses']}}
    return result, config


def _read_json(path, limit):
    path = Path(path).expanduser().absolute()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Input must be a bounded regular JSON file without symlinks.')
    return json.loads(path.read_text(encoding='utf-8'))


def _write_private_new(path, content):
    path = Path(path).expanduser().absolute()
    if (any(parent.is_symlink() for parent in [path, *path.parents])
            or not path.parent.is_dir()):
        raise ValueError('Output parent must exist and must not contain symlinks.')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(content.encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('prepare', help='Prepare one deterministic getter batch from explicit observed node IDs',
        epilog=('Selection files use schema figma-flow-native-api-probe-selection-v1 with fileKey, pageId, and '
                'nodes [{semantic_id, observed_node_id, observed_type}]. Candidate offsets are 0, 16, 32, ...; '
                'repeat with the latest saved probe readback until each eligibleByType.coverage is complete. '
                'A no-candidate type has no getters and is never reported as covered. Preparation only emits a '
                'selection request; execution happens only through the registered discovery workspace task.'))
    command.add_argument('--selection', type=Path, required=True,
                         help='JSON containing exact semantic and previously observed native node IDs')
    command.add_argument('--file-key', required=True)
    command.add_argument('--page-id', required=True)
    command.add_argument('--candidate-offset', type=int, help='Deterministic per-type batch offset: 0, 16, 32, ...')
    command.add_argument('--previous-readback', type=Path,
                         help='Saved actual probe readback from the same file, page, and semantic/native node selection')
    command.add_argument('--out', type=Path, help='New path for the normalized --api-probe selection request')
    args = parser.parse_args(argv)
    try:
        selection = _read_json(args.selection, 256 * 1024)
        previous = _read_json(args.previous_readback, 1024 * 1024) if args.previous_readback else None
        result, plan = normalize_selection(selection, file_key=args.file_key, page_id=args.page_id,
                                            previous_readback=previous,
                                            candidate_offset=args.candidate_offset)
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        if args.out:
            target = Path(args.out).expanduser().absolute()
            _write_private_new(target, encoded)
            print(json.dumps({'api_probe_selection': str(args.out), 'targets': len(plan['targets']),
                              'planned_getters': plan['budget']['planned_getters'],
                              'candidate_offset': plan['candidateOffset'],
                              'eligible_by_type': plan['eligibilityByType'],
                              'previous_receipt': plan['previous']['observed_at'] if plan['previous'] else None}))
        else:
            print(encoded, end='')
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f'native-api-probe: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
