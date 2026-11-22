async function main(): Promise<void> {
  if (figma.editorType !== 'figma') throw new Error('Open this recipe in Figma Design.');
  const design = RECIPE_VISUALS['design-grid'];
  const page = figma.currentPage;
  const selection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };
  try {
    const x = page.children.reduce((right, node) => {
      const bounds = node.absoluteBoundingBox;
      return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
    }, 0) + design.frame.pageXOffset;
    const grid = track(figma.createFrame());
    grid.name = 'Recipe · Two by two auto layout grid';
    grid.x = x;
    grid.resize(design.frame.width, design.frame.height);
    grid.layoutMode = design.grid.mode;
    grid.gridAutoTracks = design.grid.autoTracks;
    grid.gridRowCount = design.grid.rows;
    grid.gridColumnCount = design.grid.columns;
    grid.gridRowGap = design.grid.rowGap;
    grid.gridColumnGap = design.grid.columnGap;
    for (let index = 0; index < design.cells.count; index++) {
      const cell = track(figma.createRectangle());
      grid.appendChild(cell);
      cell.name = `Cell ${index + 1}`;
      cell.resize(design.cells.width, design.cells.height);
      cell.fills = [{ type: design.cells.fillType, color: {
        r: design.cells.fill.r + index * design.cells.redStep,
        g: design.cells.fill.g,
        b: design.cells.fill.b,
      } }];
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
