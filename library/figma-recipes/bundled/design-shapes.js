"use strict";
async function main() {
    if (figma.editorType !== 'figma')
        throw new Error('Open this recipe in Figma Design.');
    const page = figma.currentPage;
    const selection = [...page.selection];
    const owned = [];
    const track = (node) => { owned.push(node); return node; };
    try {
        const x = page.children.reduce((right, node) => {
            const bounds = node.absoluteBoundingBox;
            return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
        }, 0) + 160;
        const container = track(figma.createFrame());
        container.name = 'Recipe · Booleans and alpha mask';
        container.x = x;
        container.resize(880, 380);
        container.fills = [];
        container.clipsContent = false;
        const operations = ['UNION', 'SUBTRACT', 'INTERSECT', 'EXCLUDE'];
        for (const [index, operation] of operations.entries()) {
            const first = track(figma.createRectangle());
            container.appendChild(first);
            first.resize(100, 100);
            first.x = index * 180;
            const second = track(figma.createEllipse());
            container.appendChild(second);
            second.resize(100, 100);
            second.x = first.x + 40;
            second.y = 40;
            let result;
            switch (operation) {
                case 'UNION':
                    result = track(figma.union([first, second], container));
                    break;
                case 'SUBTRACT':
                    result = track(figma.subtract([first, second], container));
                    break;
                case 'INTERSECT':
                    result = track(figma.intersect([first, second], container));
                    break;
                case 'EXCLUDE':
                    result = track(figma.exclude([first, second], container));
                    break;
            }
            result.name = operation;
            result.fills = [{ type: 'SOLID', color: { r: 0.24, g: 0.35, b: 0.85 } }];
        }
        const mask = track(figma.createEllipse());
        container.appendChild(mask);
        mask.resize(120, 120);
        mask.y = 220;
        mask.isMask = true;
        mask.maskType = 'ALPHA';
        const content = track(figma.createRectangle());
        container.appendChild(content);
        content.resize(180, 80);
        content.y = 240;
        content.fills = [{ type: 'SOLID', color: { r: 0.95, g: 0.45, b: 0.2 } }];
        const masked = track(figma.group([mask, content], container));
        masked.name = 'Alpha mask · ellipse clips rectangle';
        page.selection = [container];
        figma.viewport.scrollAndZoomIntoView([container]);
        figma.closePlugin('Created booleans and an alpha mask in a new frame.');
    }
    catch (error) {
        for (const node of [...owned].reverse()) {
            if (!node.removed) {
                try {
                    node.remove();
                }
                catch (_) { }
            }
        }
        if (figma.currentPage.id === page.id)
            page.selection = selection.filter(node => !node.removed);
        const remaining = owned.filter(node => !node.removed);
        if (remaining.length)
            throw new Error(String(error) + '; cleanup failed for ' + remaining.map(node => node.id).join(', '));
        throw error;
    }
}
main().catch((error) => figma.closePlugin(String(error)));
