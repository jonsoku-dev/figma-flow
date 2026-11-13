async function main(): Promise<void> {
  if (figma.editorType !== 'figma') throw new Error('Open this recipe in Figma Design.');
  const page = figma.currentPage;
  const selection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };
  try {
    const x = page.children.reduce((right, node) => {
      const bounds = node.absoluteBoundingBox;
      return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
    }, 0) + 160;
    const container = track(figma.createSection());
    container.name = 'Recipe · Smart Animate prototype';
    container.x = x;
    container.resizeWithoutConstraints(840, 300);
    const start = track(figma.createFrame());
    container.appendChild(start);
    start.name = 'Start · click the dot';
    start.resize(360, 240);
    start.x = 24;
    start.y = 30;
    const dot = track(figma.createEllipse());
    dot.name = 'Moving dot';
    dot.resize(64, 64);
    start.appendChild(dot);
    dot.x = 24;
    dot.y = 88;
    dot.fills = [{ type: 'SOLID', color: { r: 0.24, g: 0.35, b: 0.85 } }];
    const finish = track(start.clone());
    finish.name = 'Finish · click the dot to return';
    finish.x = 420;
    const movedDot = finish.children[0];
    movedDot.x = 272;
    const transition: SimpleTransition = {
      type: 'SMART_ANIMATE', easing: { type: 'EASE_IN_AND_OUT' }, duration: 0.6,
    };
    await dot.setReactionsAsync([{
      trigger: { type: 'ON_CLICK' },
      actions: [{ type: 'NODE', destinationId: finish.id, navigation: 'NAVIGATE', transition }],
    }]);
    if ('setReactionsAsync' in movedDot) {
      await movedDot.setReactionsAsync([{
        trigger: { type: 'ON_CLICK' },
        actions: [{ type: 'NODE', destinationId: start.id, navigation: 'NAVIGATE', transition }],
      }]);
    }
    page.selection = [start];
    figma.viewport.scrollAndZoomIntoView([start, finish]);
    figma.closePlugin('Present the selected Start frame and click the dot.');
  } catch (error: unknown) {
    for (const node of [...owned].reverse()) {
      if (!node.removed) { try { node.remove(); } catch (_) {} }
    }
    if (figma.currentPage.id === page.id) page.selection = selection.filter(node => !node.removed);
    const remaining = owned.filter(node => !node.removed);
    if (remaining.length) throw new Error(String(error) + '; cleanup failed for ' + remaining.map(node => node.id).join(', '));
    throw error;
  }
}
main().catch((error: unknown) => figma.closePlugin(String(error)));
