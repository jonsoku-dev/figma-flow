const counted = new Set(['pending', 'requested', 'running', 'finished', 'readback', 'baseline', 'verified', 'failed']);

export function workspaceActivity(tasks = [], history = []) {
  const events = Array.isArray(history) ? history : [];
  const latest = new Map();
  for (const task of Array.isArray(tasks) ? tasks : []) {
    const event = [...events].reverse().find(item => item.taskKey === task.key && item.revision === task.revision &&
      item.operation !== 'download' && !item.operation.startsWith('chat:'));
    latest.set(task.key + '\0' + task.revision, {task, event});
  }
  const counts = Object.fromEntries([...counted].map(state => [state, 0]));
  for (const {event} of latest.values()) counts[counted.has(event?.status) ? event.status : 'pending']++;
  const current = new Set([...latest.keys()]);
  const flows = new Map(), legacy = [];
  events.forEach((event, index) => {
    const flow = {event, index, current: current.has(event.taskKey + '\0' + event.revision)};
    if (typeof event.executionId === 'string' && event.executionId) {
      const key = JSON.stringify([event.taskKey, event.revision, event.executionId]);
      if (!flows.has(key)) flows.set(key, []);
      flows.get(key).push(flow);
    } else legacy.push(flow);
  });
  return {counts, taskStates: [...latest.values()], flows: [...flows].map(([key, steps]) => ({key, executionId: steps[0].event.executionId, steps}))
    .sort((left, right) => right.steps.at(-1).index - left.steps.at(-1).index), legacy};
}
