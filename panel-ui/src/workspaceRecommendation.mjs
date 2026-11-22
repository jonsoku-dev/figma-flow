const terminal = new Set(['finished', 'readback', 'verified', 'baseline']);
const historyOf = (model) => (Array.isArray(model.history) ? model.history : []);
const tasksOf = (model) => (Array.isArray(model.tasks) ? model.tasks : []);

export const latestFor = (model, task) =>
  [...historyOf(model)]
    .reverse()
    .find(
      (event) =>
        event.taskKey === task.key && event.revision === task.revision && event.operation !== 'download',
    );

const phase = (task) =>
  task.kind === 'sync' || (task.kind === 'import' && task.paired) ? 3 : task.kind === 'import' ? 2 : 1;
const progressed = (model, task) =>
  task.kind !== 'review' &&
  (task.productionAdmitted || task.paired) &&
  historyOf(model).some(
    (event) =>
      event.taskKey === task.key &&
      event.revision === task.revision &&
      terminal.has(event.status) &&
      !event.operation.startsWith('chat:'),
  );

export function selectRecommendation(model, tasks) {
  const available = tasks.filter((task) => !task.fileKey || task.fileKey === model.fileKey);
  const admitted = available.filter((task) => task.productionAdmitted);
  const continued = available.filter(
    (task) =>
      (task.kind === 'sync' || task.kind === 'import') &&
      task.paired &&
      tasksOf(model).some(
        (previous) => previous.project === task.project && progressed(model, previous),
      ),
  );
  let candidates =
    admitted.length || continued.length
      ? available.filter((task) => admitted.includes(task) || continued.includes(task))
      : available;
  if (admitted.length || continued.length)
    candidates = candidates.filter(
      (task) =>
        phase(task) >=
        Math.max(
          0,
          ...candidates
            .filter((previous) => previous.project === task.project && progressed(model, previous))
            .map(phase),
        ),
    );
  const failed = candidates.find((task) => latestFor(model, task)?.status === 'failed');
  if (failed) return { task: failed, inspect: false };
  const pending = candidates.find((task) => !latestFor(model, task));
  if (pending) return { task: pending, inspect: false };
  const actual = [...historyOf(model)]
    .reverse()
    .find((event) =>
      candidates.some(
        (task) =>
          task.key === event.taskKey &&
          task.revision === event.revision &&
          event.operation !== 'download',
      ),
    );
  const task = candidates.find((task) => task.key === actual?.taskKey) || candidates[0];
  return task ? { task, inspect: true } : null;
}
