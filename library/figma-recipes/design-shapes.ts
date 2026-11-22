async function main(): Promise<void> {
  if (figma.editorType !== 'figma') throw new Error('Open this recipe in Figma Design.');
  const design = RECIPE_VISUALS['design-shapes'];
  const page = figma.currentPage;
  const selection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };
  try {
    const x = page.children.reduce((right, node) => {
      const bounds = node.absoluteBoundingBox;
      return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
    }, 0) + design.frame.pageXOffset;
    const container = track(figma.createFrame());
    container.name = 'Recipe · Booleans and alpha mask';
    container.x = x;
    container.resize(design.frame.width, design.frame.height);
    container.fills = [...design.frame.fills];
    container.clipsContent = design.frame.clipsContent;
    const operations = design.booleans.operations;
    for (const [index, operation] of operations.entries()) {
      const first = track(figma.createRectangle());
      container.appendChild(first);
      first.resize(design.booleans.shapeWidth, design.booleans.shapeHeight);
      first.x = index * design.booleans.stepX;
      const second = track(figma.createEllipse());
      container.appendChild(second);
      second.resize(design.booleans.shapeWidth, design.booleans.shapeHeight);
      second.x = first.x + design.booleans.overlapX;
      second.y = design.booleans.secondY;
      let result: BooleanOperationNode;
      switch (operation) {
        case 'UNION': result = track(figma.union([first, second], container)); break;
        case 'SUBTRACT': result = track(figma.subtract([first, second], container)); break;
        case 'INTERSECT': result = track(figma.intersect([first, second], container)); break;
        case 'EXCLUDE': result = track(figma.exclude([first, second], container)); break;
      }
      result.name = operation;
      result.fills = [{ type: design.booleans.fillType, color: design.booleans.fill }];
    }
    const mask = track(figma.createEllipse());
    container.appendChild(mask);
    mask.resize(design.mask.size, design.mask.size);
    mask.y = design.mask.y;
    mask.isMask = design.mask.isMask;
    mask.maskType = design.mask.maskType;
    const content = track(figma.createRectangle());
    container.appendChild(content);
    content.resize(design.content.width, design.content.height);
    content.y = design.content.y;
    content.fills = [{ type: design.content.fillType, color: design.content.fill }];
    const masked = track(figma.group([mask, content], container));
    masked.name = 'Alpha mask · ellipse clips rectangle';
    page.selection = [container];
    figma.viewport.scrollAndZoomIntoView([container]);
    figma.closePlugin('Created booleans and an alpha mask in a new frame.');
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
