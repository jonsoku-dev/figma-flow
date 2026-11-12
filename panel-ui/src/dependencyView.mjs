const artifacts = new Set(['code.js', 'ui.html', 'manifest.json']);

function explicit(edge) {
  return !!edge && edge.relation === 'uses-output' && artifacts.has(edge.artifact) &&
    typeof edge.task_key === 'string' && typeof edge.revision === 'string' &&
    typeof edge.artifact_sha256 === 'string';
}

function neighbor(task, edge, role, currentRevision) {
  return {
    role,
    key: task.key,
    title: typeof task.title === 'string' ? task.title : task.key,
    relation: edge.relation,
    artifact: edge.artifact,
    artifact_sha256: edge.artifact_sha256,
    pinned_revision: edge.revision,
    current_revision: currentRevision,
  };
}

function line(label, item) {
  return `${label} ${item.title} ${item.key} 현재 ${item.current_revision} 고정 ${item.pinned_revision} ${item.relation} ${item.artifact} ${item.artifact_sha256}`;
}

export function dependencyView(tasks, selected) {
  if (!Array.isArray(tasks)) throw new Error('unknown selected task');
  const byKey = new Map();
  for (const task of tasks) {
    if (!task || typeof task.key !== 'string' || byKey.has(task.key)) throw new Error('unknown selected task');
    byKey.set(task.key, task);
  }
  const current = byKey.get(selected);
  if (!current) throw new Error('unknown selected task');
  const predecessors = [];
  for (const edge of Array.isArray(current.depends_on) ? current.depends_on : []) {
    if (!explicit(edge)) continue;
    const prior = byKey.get(edge.task_key);
    if (!prior || prior.key === selected) continue;
    predecessors.push(neighbor(prior, edge, 'predecessor', prior.revision));
  }
  const successors = [];
  for (const task of tasks) {
    if (!task || task.key === selected) continue;
    for (const edge of Array.isArray(task.depends_on) ? task.depends_on : []) {
      if (!explicit(edge) || edge.task_key !== selected) continue;
      successors.push(neighbor(task, edge, 'successor', current.revision));
    }
  }
  const text = [
    ...predecessors.map((item) => line('선행', item)),
    ...successors.map((item) => line('후속', item)),
  ];
  if (!text.length) text.push('연결된 선행·후속이 없습니다');
  return { selected, predecessors, successors, text };
}
