const test = require('node:test');
const assert = require('node:assert/strict');

test('current task distribution ignores stale, orphan, chat, and download events', async () => {
  const {workspaceActivity} = await import('../panel-ui/src/WorkspaceActivity.mjs');
  const tasks = [
    {key:'a', revision:'r2'}, {key:'b', revision:'r1'}, {key:'c', revision:'r1'}, {key:'d', revision:'r1'}
  ];
  const event = (taskKey, revision, status, operation = 'read', executionId) => ({taskKey, revision, status, operation, time:'2026-11-12T00:00:00.000Z', ...(executionId ? {executionId} : {})});
  const history = [
    event('a','r2','requested','apply','exec-a'), event('a','r2','running','apply','exec-a'), event('a','r2','finished','apply','exec-a'),
    event('a','r2','requested','apply','exec-b'), event('a','r2','failed','apply','exec-b'),
    event('b','r1','requested','download'), event('b','r1','finished','chat:open','old-chat'),
    event('c','r1','readback','read','exec-c1'), event('c','r1','verified','verification','exec-c1'),
    event('c','r1','requested','read','exec-c2'),
    event('d','old','verified','read','stale'), event('removed','gone','failed','read','orphan'),
    event('legacy','old','failed','read')
  ];
  const result = workspaceActivity(tasks, history);
  assert.deepEqual(result.counts, {pending:2, requested:1, running:0, finished:0, readback:0, baseline:0, verified:0, failed:1});
  assert.deepEqual(result.flows.map(flow => flow.executionId), ['orphan','stale','exec-c2','exec-c1','old-chat','exec-b','exec-a']);
  assert.deepEqual(result.flows.find(flow => flow.executionId === 'exec-a').steps.map(step => step.event.status), ['requested','running','finished']);
  assert.equal(result.flows.find(flow => flow.executionId === 'stale').steps[0].current, false);
  assert.equal(result.legacy.length, 2);
});

test('identical stored execution IDs do not join different tasks or revisions', async () => {
  const {workspaceActivity} = await import('../panel-ui/src/WorkspaceActivity.mjs');
  const events = [
    {taskKey:'a',revision:'old',operation:'read',status:'failed',executionId:'same'},
    {taskKey:'b',revision:'r1',operation:'read',status:'requested',executionId:'same'},
    {taskKey:'a',revision:'r1',operation:'read',status:'requested',executionId:'same'},
    {taskKey:'a',revision:'r1',operation:'read',status:'readback',executionId:'same'},
  ];
  const result = workspaceActivity([{key:'a',revision:'r1'},{key:'b',revision:'r1'}], events);
  assert.deepEqual(result.flows.map(flow => flow.steps.length), [2,1,1]);
  assert.equal(result.counts.readback, 1);
  assert.equal(result.counts.requested, 1);
  assert.equal(result.flows.at(-1).steps[0].current, false);
});
