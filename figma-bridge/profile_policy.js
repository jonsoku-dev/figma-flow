/* Shared by Design and the local Inspect pilot. A declaration can limit authoring
   or suggest a handoff; the running Figma context determines the actual surface. */
function evaluateProfileCapabilities(policy, context, declared, confirmed) {
  const values = { ...context, plan: declared.plan, seat: declared.seat, confirmed };
  const facts = {};
  for (const [id, conditions] of Object.entries(policy.facts)) {
    facts[id] = Object.entries(conditions).every(([field, allowed]) => allowed.includes(values[field]));
  }
  const capabilities = {};
  for (const [id, alternatives] of Object.entries(policy.capabilities)) {
    capabilities[id] = alternatives.some(required => required.every(fact => facts[fact] === true));
  }
  return capabilities;
}

function profileOperationNeedsAdmission(policy, operation) {
  return policy.refreshBeforeDispatch.includes(policy.operations[operation]);
}
