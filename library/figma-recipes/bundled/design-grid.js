"use strict";
/* GENERATED from design-examples.graph.json; edit the canonical graph only. */
const RECIPE_VISUALS = {
    "design-grid": {
        "cells": {
            "count": 4,
            "fill": {
                "b": 0.8,
                "g": 0.4,
                "r": 0.2
            },
            "fillType": "SOLID",
            "height": 100,
            "redStep": 0.15,
            "width": 160
        },
        "frame": {
            "height": 280,
            "pageXOffset": 160,
            "width": 420
        },
        "grid": {
            "autoTracks": "NONE",
            "columnGap": 16,
            "columns": 2,
            "mode": "GRID",
            "rowGap": 16,
            "rows": 2
        }
    }
};
async function main() {
    if (figma.editorType !== 'figma')
        throw new Error('Open this recipe in Figma Design.');
    const design = RECIPE_VISUALS['design-grid'];
    const page = figma.currentPage;
    const selection = [...page.selection];
    const owned = [];
    const track = (node) => { owned.push(node); return node; };
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
