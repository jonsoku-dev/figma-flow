export function graphSelection(changes, selected) {
  const list = Array.isArray(changes) ? changes : [];
  const allow = selected == null ? null : new Set(selected);
  const rows = list.map((change, index) => {
    const identity = String((change && (change.identity || change.name || change.key)) || index);
    const targets = change && Array.isArray(change.targets) && change.targets.length
      ? change.targets.filter((item) => typeof item === 'string')
      : [String((change && (change.name || change.key)) || identity)];
    return { identity, targets, selected: allow == null || allow.has(identity) };
  });
  return { rows, count: rows.filter((row) => row.selected).length, identities: rows.map((row) => row.identity) };
}
