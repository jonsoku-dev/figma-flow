const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const codePath = path.join(__dirname, '../figma-bridge/code.js');
const code = fs.readFileSync(codePath, 'utf8');
const context = {figma: {ui: {}, showUI() {}}, __html__: ''};
vm.createContext(context);
vm.runInContext(code, context);

const button = {
  variants: {sm: {padding: 'space.card'}, md: {padding: 'space.card'}, disabled: {padding: 'space.card'}, loading: {padding: 'space.card'}, error: {padding: 'space.card'}},
  variant_axes: {size: ['sm', 'md'], state: ['disabled', 'loading', 'error']}
};
const groups = context.componentVariantGroups(button);
const summary = groups.map(group => ({axis: group.axis, variants: group.variants.map(([variant]) => variant)}));
assert.equal(JSON.stringify(summary), JSON.stringify([
  {axis: 'size', variants: ['sm', 'md']},
  {axis: 'state', variants: ['disabled', 'loading', 'error']}
]));
const created = summary.flatMap(group => group.variants.map(variant => group.axis + '=' + variant));
assert.equal(created.length, Object.keys(button.variants).length);
assert.equal(created.some(name => name.includes('sm') && name.includes('disabled')), false);

const legacy = context.componentVariantGroups({variants: {primary: {}, secondary: {}}});
assert.equal(JSON.stringify(legacy.map(group => ({axis: group.axis, variants: group.variants.map(([variant]) => variant)}))),
  JSON.stringify([{axis: 'Variant', variants: ['primary', 'secondary']}]));
assert.equal(context.componentUsageText(button), undefined);
assert.equal(context.componentUsageText({...button, usage: '확인에 사용'}), '확인에 사용');
assert.equal(context.componentSwapTargets(button), undefined);
assert.match(code, /componentVariantGroups\(definition\)/);
assert.match(code, /componentUsageText\(definition\)/);
