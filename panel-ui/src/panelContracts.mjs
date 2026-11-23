import panelGraph from '../../library/panel-design/contracts.json' with { type: 'json' };
import designGraph from '../../library/panel-design/tokens.json' with { type: 'json' };
import activityGraph from '../../specs/workspace-activity/graph.json' with { type: 'json' };
import chatInputGraph from '../../figma-bridge/chat-input.json' with { type: 'json' };

function contractNode(graph, id) {
  const matches = graph.nodes.filter((node) => node.id === id);
  if (matches.length !== 1) throw new Error(`Expected one panel contract node: ${id}`);
  return matches[0];
}

if (panelGraph.schema !== 'figma-flow-panel-contract-graph-v1' || activityGraph.version !== 1) {
  throw new Error('Unsupported panel domain contract graph');
}

const dependencyContract = contractNode(panelGraph, 'dependency-artifacts');
export const dependencyArtifacts = Object.freeze([...dependencyContract.values]);
export const dependencyRelation = dependencyContract.relation;
export const dependencyDirections = Object.freeze([...dependencyContract.directions]);
const assetStatusRows = contractNode(panelGraph, 'asset-inventory-statuses').statuses;
export const assetStatuses = Object.freeze(assetStatusRows.map(({ value }) => value));
export const assetProblemStatuses = Object.freeze(assetStatusRows.filter(({ severity }) => severity === 'problem').map(({ value }) => value));
export const operationDetailContract = Object.freeze(contractNode(panelGraph, 'operation-detail-v1'));
const chatErrors = contractNode(panelGraph, 'chat-error-codes').codes;
if (new Set(chatErrors.map(({ code }) => code)).size !== chatErrors.length) {
  throw new Error('Panel chat error codes must be unique');
}
export const chatErrorMessageKeys = Object.freeze(Object.fromEntries(chatErrors.map(({ code, messageKey }) => [code, messageKey])));
export const workspaceActivityContract = Object.freeze(contractNode(activityGraph, 'CONTRACT-ACTIVITY-01'));
const { message: chatMessageInput, preview: chatPreviewInput } = chatInputGraph;
if (![chatMessageInput?.maxCharacters, chatMessageInput?.rows, chatPreviewInput?.reactRows]
  .every(value => Number.isSafeInteger(value) && value > 0)) {
  throw new Error('Invalid shared chat input dimensions');
}
export const chatInputPolicy = Object.freeze({
  message: Object.freeze({ ...chatMessageInput }),
  preview: Object.freeze({ ...chatPreviewInput }),
});
const fieldSet = (name, consumer) => Object.freeze(operationDetailContract.fieldPolicies[name]
  .filter((field) => field[consumer])
  .map((field) => field.id));
export const operationDetailPanelFields = Object.freeze({
  design: fieldSet('designFields', 'panel'),
  text: fieldSet('textFields', 'panel'),
});
export const workspaceHistoryDisplay = Object.freeze({
  phases: Object.freeze([...operationDetailContract.nativePhases, ...operationDetailContract.displayPhaseFallbacks]),
  diffReasons: Object.freeze([
    ...Object.values(operationDetailContract.diffReasonCodes),
    ...Object.values(operationDetailContract.displayDiffReasonCodes),
  ]),
  unavailableReasons: Object.freeze(Object.values(operationDetailContract.unavailableReasonCodes)),
  errorReasons: Object.freeze(Object.values(operationDetailContract.errorReasonCodes)),
  failureCodes: operationDetailContract.failureCodes,
  failureActions: operationDetailContract.failureActions,
  fallbacks: operationDetailContract.fallbacks,
  scopeNotices: operationDetailContract.scopeNotices,
});
const designSurface = designGraph.surfaces.find((surface) => surface.id === 'panel-workbench');
const designTokens = new Map(designGraph.tokens.map((token) => [token.id, token]));
export const panelDesignMetrics = Object.freeze(Object.fromEntries(
  Object.entries(designSurface?.metrics || {}).map(([key, tokenId]) => {
    const value = designTokens.get(tokenId)?.light;
    const parsed = Number.parseFloat(value);
    if (!Number.isFinite(parsed)) throw new Error(`Unknown panel design metric token: ${tokenId}`);
    return [key, parsed];
  }),
));
