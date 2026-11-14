const FILE_KEY = /^[A-Za-z0-9_-]{1,128}$/;
const NODE_ID = /^\d+(?:[:-]\d+)$/;
const SLUG = /^[A-Za-z0-9_-]{1,128}$/;
const PARAMS = ['node-id', 'starting-point-node-id', 'page-id', 'scaling'];

/**
 * Accept a host Present reply only when its URL is the Figma prototype link for the
 * file, page and flow-start frame of a current carousel the panel already lists.
 */
export function verifiedPresentationLink(message, { fileKey, tasks, history }) {
  if (message?.type !== 'workspace-carousel-presented' || typeof message.url !== 'string' || message.url.length > 512) return null;
  const task = tasks.find(item => item.key === message.taskKey);
  const event = [...history].reverse().find(item => item.taskKey === message.taskKey
    && item.executionId === message.executionId && item.carousel);
  const carousel = event?.carousel;
  if (!task || !carousel || task.kind !== 'native-edit' || event.revision !== task.revision || carousel.status !== 'current'
      || !FILE_KEY.test(fileKey || '') || task.fileKey !== fileKey || carousel.file_key !== fileKey
      || carousel.page_id !== task.pageId || !NODE_ID.test(carousel.page_id) || !NODE_ID.test(carousel.flow_start_node_id)
      || message.nodeId !== carousel.flow_start_node_id || message.stateId !== carousel.initial_state) return null;
  let url;
  try { url = new URL(message.url); } catch { return null; }
  const [, kind, key, slug, ...rest] = url.pathname.split('/');
  const dashed = id => id.replaceAll(':', '-');
  const node = dashed(carousel.flow_start_node_id);
  if (url.href !== message.url || url.protocol !== 'https:' || url.hostname !== 'www.figma.com' || url.port
      || url.username || url.password || url.hash || kind !== 'proto' || key !== fileKey || !SLUG.test(slug || '') || rest.length
      || [...url.searchParams.keys()].length !== PARAMS.length || PARAMS.some(name => url.searchParams.getAll(name).length !== 1)
      || url.searchParams.get('node-id') !== node || url.searchParams.get('starting-point-node-id') !== node
      || url.searchParams.get('page-id') !== dashed(carousel.page_id) || url.searchParams.get('scaling') !== 'scale-down') return null;
  return { taskKey: task.key, executionId: event.executionId, url: url.href };
}
