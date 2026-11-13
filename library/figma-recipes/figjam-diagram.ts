async function main(): Promise<void> {
  if (figma.editorType !== 'figjam') throw new Error('Open this recipe in FigJam.');
  const page = figma.currentPage;
  const selection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };
  try {
    const font: FontName = { family: 'Inter', style: 'Medium' };
    await figma.loadFontAsync(font);
    const start = track(figma.createShapeWithText());
    start.name = 'Recipe · Request';
    start.shapeType = 'ROUNDED_RECTANGLE';
    start.resize(200, 100);
    start.x = figma.viewport.center.x - 260;
    start.y = figma.viewport.center.y;
    start.text.fontName = font;
    start.text.characters = 'Request';
    const finish = track(figma.createShapeWithText());
    finish.name = 'Recipe · Result';
    finish.shapeType = 'ROUNDED_RECTANGLE';
    finish.resize(200, 100);
    finish.x = start.x + 360;
    finish.y = start.y;
    finish.text.fontName = font;
    finish.text.characters = 'Result';
    const connector = track(figma.createConnector());
    connector.name = 'Recipe · Request to result';
    connector.connectorLineType = 'ELBOWED';
    connector.connectorStart = { endpointNodeId: start.id, magnet: 'RIGHT' };
    connector.connectorEnd = { endpointNodeId: finish.id, magnet: 'LEFT' };
    connector.connectorEndStrokeCap = 'ARROW_LINES';
    figma.currentPage.selection = [start, finish, connector];
    figma.viewport.scrollAndZoomIntoView([start, finish, connector]);
    figma.closePlugin('Created two shapes and an attached connector.');
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
