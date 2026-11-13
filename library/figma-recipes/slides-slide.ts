async function main(): Promise<void> {
  if (figma.editorType !== 'slides') throw new Error('Open this recipe in Figma Slides.');
  const page = figma.currentPage;
  const selection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };
  try {
    const font: FontName = { family: 'Inter', style: 'Bold' };
    await figma.loadFontAsync(font);
    const slide = track(figma.createSlide());
    slide.name = 'Recipe · Title slide';
    slide.fills = [{ type: 'SOLID', color: { r: 0.95, g: 0.96, b: 1 } }];
    const title = track(figma.createText());
    slide.appendChild(title);
    title.name = 'Title';
    title.fontName = font;
    title.fontSize = 72;
    title.characters = 'A new idea';
    title.x = 120;
    title.y = 120;
    title.fills = [{ type: 'SOLID', color: { r: 0.12, g: 0.17, b: 0.35 } }];
    slide.setSlideTransition({
      style: 'DISSOLVE', duration: 0.5, curve: 'EASE_IN_AND_OUT', timing: { type: 'ON_CLICK' },
    });
    figma.currentPage.selection = [slide];
    figma.viewport.scrollAndZoomIntoView([slide]);
    figma.closePlugin('Created a title slide with a dissolve transition.');
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
