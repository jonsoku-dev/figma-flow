declare function metadata(node: BaseNode, id: string): void;
declare function info(node: BaseNode): {declared_property_keys?: Record<string, string>};
declare function bindOwnedLabelProperty(owner: ComponentSetNode, mains: ComponentNode[], warnings: Set<string>): string | null;
declare function validateDeclaredComponentProperties(payload: typeof PAYLOAD): void;
declare function bindDeclaredComponentProperties(components: Map<string, ComponentNode>, definitions: typeof PAYLOAD.components): void;
declare function applyDeclaredInstanceProperties(instance: InstanceNode, main: ComponentNode,
  element: typeof PAYLOAD.screens[number]['elements'][number], components: Map<string, ComponentNode>): Promise<void>;

async function main(): Promise<void> {
  if (figma.editorType !== 'figma') throw new Error('Open this recipe in Figma Design.');
  const page = figma.currentPage;
  const selection = [...page.selection];
  const owned: SceneNode[] = [];
  const track = <T extends SceneNode>(node: T): T => { owned.push(node); return node; };
  try {
    validateDeclaredComponentProperties(PAYLOAD);
    const font: FontName = {family: 'Inter', style: 'Regular'};
    await figma.loadFontAsync(font);
    const x = page.children.reduce((right, node) => {
      const bounds = node.absoluteBoundingBox;
      return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
    }, 0) + 160;
    const container = track(figma.createFrame());
    container.name = 'Recipe · Native BOOLEAN and INSTANCE_SWAP';
    container.x = x;
    container.layoutMode = 'VERTICAL';
    container.primaryAxisSizingMode = 'AUTO';
    container.counterAxisSizingMode = 'AUTO';
    container.paddingTop = container.paddingBottom = container.paddingLeft = container.paddingRight = 32;
    container.itemSpacing = 20;
    const label = (parent: FrameNode | ComponentNode, value: string): TextNode => {
      const text = track(figma.createText());
      parent.appendChild(text);
      text.fontName = font;
      text.characters = value;
      text.fontSize = 18;
      return text;
    };
    label(container, 'Native component properties · BOOLEAN + INSTANCE_SWAP');
    const components = new class extends Map<string, ComponentNode> {
      get(key: string): ComponentNode | undefined {
        const main = super.get(key);
        return main && new Proxy(main, {get(target, field) {
          if (field === 'createInstance') return () => track(target.createInstance());
          const value = Reflect.get(target, field, target);
          return typeof value === 'function' ? value.bind(target) : value;
        }});
      }
    }();
    const warnings = new Set<string>();
    for (const [name, definition] of Object.entries(PAYLOAD.components)) {
      const mains: ComponentNode[] = [];
      for (const variant of Object.keys(definition.variants)) {
        const main = track(figma.createComponent());
        container.appendChild(main);
        main.name = 'Variant=' + variant;
        main.layoutMode = 'HORIZONTAL';
        main.primaryAxisSizingMode = 'AUTO';
        main.counterAxisSizingMode = 'AUTO';
        main.paddingTop = main.paddingBottom = main.paddingLeft = main.paddingRight = 12;
        main.itemSpacing = 12;
        label(main, name === 'button' ? 'Button label' : variant);
        if (name === 'symbol') {
          const shape = variant === 'circle' ? figma.createEllipse() : figma.createRectangle();
          main.appendChild(shape);
          shape.resize(24, 24);
          shape.fills = [{type: 'SOLID', color: {r: 0.22, g: 0.36, b: 0.85}}];
        }
        metadata(main, 'component:' + name + '/' + variant);
        components.set(JSON.stringify([name, variant]), main);
        mains.push(main);
      }
      const set = track(figma.combineAsVariants(mains, container));
      set.name = 'Main family · ' + name;
      set.layoutMode = 'HORIZONTAL';
      set.primaryAxisSizingMode = 'AUTO';
      set.counterAxisSizingMode = 'AUTO';
      set.itemSpacing = 24;
      bindOwnedLabelProperty(set, mains, warnings);
    }
    bindDeclaredComponentProperties(components, PAYLOAD.components);
    const button = components.get(JSON.stringify(['button', 'default']));
    if (!button) throw new Error('Compiled fixture has no button/default.');
    const cases = [
      'Default · label visible, circle symbol visible',
      'Override · label hidden, square symbol visible',
      'Override · label visible, symbol hidden',
    ];
    const report: Array<{name: string; id: string; labelVisible: boolean; slotVisible: boolean; mainComponentId: string}> = [];
    for (const [index, element] of PAYLOAD.screens[0].elements.entries()) {
      label(container, cases[index]);
      const instance = button.createInstance();
      container.appendChild(instance);
      instance.name = element.id;
      await applyDeclaredInstanceProperties(instance, button, element, components);
      const text = instance.children.find(child => child.type === 'TEXT');
      const slot = instance.children.find(child => child.name === 'slot:symbol');
      if (!text || !slot || slot.type !== 'INSTANCE') throw new Error('Native property targets missing.');
      const main = await slot.getMainComponentAsync();
      if (!main) throw new Error('Native swap main component unavailable.');
      report.push({name: instance.name, id: instance.id, labelVisible: text.visible,
        slotVisible: slot.visible, mainComponentId: main.id});
    }
    const keys = info(button).declared_property_keys;
    if (!keys || button.parent?.type !== 'COMPONENT_SET') throw new Error('Native property keys unavailable.');
    const definitions = button.parent.componentPropertyDefinitions;
    const expected = ['circle', 'square'].map(variant => {
      const main = components.get(JSON.stringify(['symbol', variant]));
      if (!main) throw new Error('Preferred component unavailable.');
      return {type: 'COMPONENT', key: main.key};
    });
    if (definitions[keys.ShowLabel]?.type !== 'BOOLEAN' || definitions[keys.ShowSymbol]?.type !== 'BOOLEAN' ||
        definitions[keys.Symbol]?.type !== 'INSTANCE_SWAP' ||
        JSON.stringify(definitions[keys.Symbol].preferredValues) !== JSON.stringify(expected)) {
      throw new Error('Native definitions or preferred component keys differ.');
    }
    if (!button.children.find(child => child.type === 'TEXT')?.visible ||
        !button.children.find(child => child.name === 'slot:symbol')?.visible) {
      throw new Error('Instance overrides changed a main default.');
    }
    label(container, 'PASS · native definitions, references, defaults, overrides and preferred keys verified');
    container.setPluginData('componentPropertiesRecipeResult', JSON.stringify({status: 'PASS', definitions, report}));
    page.selection = [container];
    figma.viewport.scrollAndZoomIntoView([container]);
    figma.closePlugin('PASS · Created native BOOLEAN and INSTANCE_SWAP examples in a new frame.');
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
