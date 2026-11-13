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
    const grid = track(figma.createFrame());
    grid.name = 'Recipe · Two by two auto layout grid';
    grid.x = x;
    grid.resize(420, 280);
    grid.layoutMode = 'GRID';
    grid.gridAutoTracks = 'NONE';
    grid.gridRowCount = 2;
    grid.gridColumnCount = 2;
    grid.gridRowGap = 16;
    grid.gridColumnGap = 16;
    for (let index = 0; index < 4; index++) {
      const cell = track(figma.createRectangle());
      grid.appendChild(cell);
      cell.name = `Cell ${index + 1}`;
      cell.resize(160, 100);
      cell.fills = [{ type: 'SOLID', color: { r: 0.2 + index * 0.15, g: 0.4, b: 0.8 } }];
    }
    page.selection = [grid];
    figma.viewport.scrollAndZoomIntoView([grid]);
    figma.closePlugin('Created an auto layout grid in a new frame.');
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
