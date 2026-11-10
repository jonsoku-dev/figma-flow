#!/usr/bin/env python3
"""Canonical workflow graph and derived constants; evidence resolvers are trusted adapters."""
import argparse
import copy
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re

GRAPH_PATH = Path(__file__).resolve().parents[1] / 'library' / 'workflow.json'


def validate_graph(graph):
    """Reject ambiguous, dangling, unreachable, or nonterminal goal definitions."""
    if not isinstance(graph, dict) or graph.get('version') != 1:
        raise ValueError('unsupported workflow version')
    tables = {}
    for name in ('states', 'events', 'guards'):
        rows = graph.get(name)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f'missing {name}')
        ids, symbols = set(), set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f'invalid {name} row')
            identifier, symbol = row.get('id'), row.get('symbol')
            if not isinstance(identifier, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', identifier) or identifier in ids:
                raise ValueError(f'duplicate or invalid {name} id')
            if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', symbol) or symbol in symbols:
                raise ValueError(f'duplicate or invalid {name} symbol')
            ids.add(identifier)
            symbols.add(symbol)
        tables[name] = ids
    states = {row['id']: row for row in graph['states']}
    if graph.get('initial') not in states or not graph.get('goals') or any(g not in states for g in graph['goals']):
        raise ValueError('unknown initial or goals')
    for row in states.values():
        if not isinstance(row.get('label'), str) or not row['label'] or type(row.get('terminal')) is not bool:
            raise ValueError('invalid state label or terminal')
    if any(row.get('authority') not in ('human', 'controller') for row in graph['guards']):
        raise ValueError('unknown guard authority')
    seen, adjacency = set(), {identifier: set() for identifier in states}
    if not isinstance(graph.get('edges'), list):
        raise ValueError('missing edges')
    for edge in graph['edges']:
        if not isinstance(edge, dict):
            raise ValueError('invalid edge')
        if edge.get('from') not in states or edge.get('to') not in states:
            raise ValueError('unknown edge endpoint')
        if edge.get('event') not in tables['events']:
            raise ValueError('unknown edge event')
        guards = edge.get('guards')
        if not isinstance(guards, list) or any(g not in tables['guards'] for g in guards) or len(guards) != len(set(guards)):
            raise ValueError('unknown or duplicate edge guard')
        key = edge['from'], edge['event']
        if key in seen:
            raise ValueError('ambiguous transition')
        seen.add(key)
        if states[edge['from']]['terminal']:
            raise ValueError('terminal state has outgoing edge')
        if not isinstance(edge.get('invalidates', []), list) or any(not isinstance(i, str) or not i for i in edge.get('invalidates', [])):
            raise ValueError('invalid invalidation list')
        adjacency[edge['from']].add(edge['to'])
    reachable, pending = set(), [graph['initial']]
    while pending:
        state = pending.pop()
        if state not in reachable:
            reachable.add(state)
            pending.extend(adjacency[state] - reachable)
    if reachable != set(states):
        raise ValueError('unreachable workflow state')
    if any(not states[g]['terminal'] for g in graph['goals']):
        raise ValueError('goal must be terminal')
    can_finish = set(graph['goals'])
    while True:
        predecessors = {state for state, successors in adjacency.items() if successors & can_finish}
        expanded = can_finish | predecessors
        if expanded == can_finish:
            break
        can_finish = expanded
    if can_finish != set(states):
        raise ValueError('state cannot reach a workflow goal')
    for state, successors in adjacency.items():
        if not states[state]['terminal'] and not successors:
            raise ValueError('nonterminal dead end')
    return graph


def load_graph(path=GRAPH_PATH):
    return validate_graph(json.loads(Path(path).read_text(encoding='utf-8')))


_GRAPH = load_graph()
State = Enum('State', {row['symbol']: row['id'] for row in _GRAPH['states']}, type=str)
Event = Enum('Event', {row['symbol']: row['id'] for row in _GRAPH['events']}, type=str)
Guard = Enum('Guard', {row['symbol']: row['id'] for row in _GRAPH['guards']}, type=str)


def graph_hash():
    """Hash canonical JSON, independent of whitespace and object key ordering."""
    return hashlib.sha256(json.dumps(_GRAPH, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def public_graph():
    """Same source for JS/TS/HTML consumers; embed/export this instead of mirrored enums."""
    return {'graph': copy.deepcopy(_GRAPH), 'graph_sha256': graph_hash(), 'symbols': {
        name: {row['symbol']: row['id'] for row in _GRAPH[name]}
        for name in ('states', 'events', 'guards')}}


@dataclass(frozen=True)
class VerifiedFact:
    """Resolver attestation, never raw caller-supplied guard booleans.

    The integration resolver must verify current source/subject hashes and actual
    human-turn provenance before constructing human selection facts.
    """
    guard: Guard
    subject_sha256: str
    evidence_sha256: str
    authority: str
    current: bool = True


def transition_result(state, event, *, evidence=None, resolver=None):
    """Evaluate a legal edge; return required invalidations for the persistence owner.

    Resolver is trusted code, not an input field. It must bind evidence to the
    current candidate/batch/scope and reject stale or fabricated provenance.
    This pure evaluator performs no asset generation or writes.
    """
    state, event = State(state), Event(event)
    edge = next((e for e in _GRAPH['edges'] if e['from'] == state.value and e['event'] == event.value), None)
    if edge is None:
        raise ValueError(f'unsupported workflow transition: {state.value} / {event.value}')
    guards = {row['id']: row for row in _GRAPH['guards']}
    for identifier in edge['guards']:
        guard = Guard(identifier)
        if not callable(resolver):
            raise ValueError(f'verified evidence resolver required: {identifier}')
        fact = resolver(guard, evidence)
        if not isinstance(fact, VerifiedFact) or not isinstance(fact.guard, Guard) or fact.guard != guard or fact.current is not True:
            raise ValueError(f'missing or stale verified evidence: {identifier}')
        if fact.authority != guards[identifier]['authority']:
            raise ValueError(f'invalid evidence authority: {identifier}')
        if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in (fact.subject_sha256, fact.evidence_sha256)):
            raise ValueError(f'invalid evidence hashes: {identifier}')
    return {'state': State(edge['to']), 'invalidates': list(edge.get('invalidates', [])), 'graph_sha256': graph_hash()}


def transition(state, event, *, evidence=None, resolver=None):
    return transition_result(state, event, evidence=evidence, resolver=resolver)['state']


def mermaid():
    lines = ['stateDiagram-v2', f"    [*] --> {_GRAPH['initial'].replace('-', '_')}"]
    for row in _GRAPH['states']:
        identifier = row['id'].replace('-', '_')
        lines.append(f'    state "{row["label"]}" as {identifier}')
        if row['terminal']:
            lines.append(f'    {identifier} --> [*]')
    for edge in _GRAPH['edges']:
        label = edge['event']
        if edge['guards']:
            label += ' [' + ', '.join(edge['guards']) + ']'
        lines.append(f"    {edge['from'].replace('-', '_')} --> {edge['to'].replace('-', '_')}: {label}")
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=('json', 'mermaid'), default='json')
    args = parser.parse_args()
    print(mermaid() if args.format == 'mermaid' else json.dumps(public_graph(), ensure_ascii=False, indent=2), end='\n' if args.format == 'json' else '')
