"use strict";
/* GENERATED from design-examples.graph.json; edit the canonical graph only. */
const RECIPE_VISUALS = {
    "design-motion": {
        "dot": {
            "fill": {
                "b": 0.85,
                "g": 0.35,
                "r": 0.24
            },
            "fillType": "SOLID",
            "finishX": 272,
            "size": 64,
            "x": 24,
            "y": 88
        },
        "frame": {
            "finishX": 420,
            "height": 240,
            "width": 360,
            "x": 24,
            "y": 30
        },
        "section": {
            "height": 300,
            "pageXOffset": 160,
            "width": 840
        },
        "transition": {
            "duration": 0.6,
            "easing": "EASE_IN_AND_OUT",
            "navigation": "NAVIGATE",
            "trigger": "ON_CLICK",
            "type": "SMART_ANIMATE"
        }
    }
};
async function main() {
    if (figma.editorType !== 'figma')
        throw new Error('Open this recipe in Figma Design.');
    const design = RECIPE_VISUALS['design-motion'];
    const page = figma.currentPage;
    const selection = [...page.selection];
    const owned = [];
    const track = (node) => { owned.push(node); return node; };
    try {
        const x = page.children.reduce((right, node) => {
            const bounds = node.absoluteBoundingBox;
            return Math.max(right, bounds ? bounds.x + bounds.width : node.x + node.width);
        }, 0) + design.section.pageXOffset;
        const container = track(figma.createSection());
        container.name = 'Recipe · Smart Animate prototype';
        container.x = x;
        container.resizeWithoutConstraints(design.section.width, design.section.height);
        const start = track(figma.createFrame());
        container.appendChild(start);
        start.name = 'Start · click the dot';
        start.resize(design.frame.width, design.frame.height);
        start.x = design.frame.x;
        start.y = design.frame.y;
        const dot = track(figma.createEllipse());
        dot.name = 'Moving dot';
        dot.resize(design.dot.size, design.dot.size);
        start.appendChild(dot);
        dot.x = design.dot.x;
        dot.y = design.dot.y;
        dot.fills = [{ type: design.dot.fillType, color: design.dot.fill }];
        const finish = track(start.clone());
        finish.name = 'Finish · click the dot to return';
        finish.x = design.frame.finishX;
        const movedDot = finish.children[0];
        movedDot.x = design.dot.finishX;
        const transition = {
            type: design.transition.type, easing: { type: design.transition.easing }, duration: design.transition.duration,
        };
        await dot.setReactionsAsync([{
                trigger: { type: design.transition.trigger },
                actions: [{ type: 'NODE', destinationId: finish.id, navigation: design.transition.navigation, transition }],
            }]);
        if ('setReactionsAsync' in movedDot) {
            await movedDot.setReactionsAsync([{
                    trigger: { type: design.transition.trigger },
                    actions: [{ type: 'NODE', destinationId: start.id, navigation: design.transition.navigation, transition }],
                }]);
        }
        page.selection = [start];
        figma.viewport.scrollAndZoomIntoView([start, finish]);
        figma.closePlugin('Present the selected Start frame and click the dot.');
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
