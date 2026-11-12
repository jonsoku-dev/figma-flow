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
assert.deepEqual(groups.map(group => group.axis), ['size', 'state']);
const created = groups.flatMap(group => group.variants.map(([variant]) => group.axis + '=' + variant));
assert.deepEqual(created, ['size=sm', 'size=md', 'state=disabled', 'state=loading', 'state=error']);
assert.equal(created.length, Object.keys(button.variants).length);
assert.equal(created.some(name => name.includes('sm') && name.includes('disabled')), false);

const legacy = context.componentVariantGroups({variants: {primary: {}, secondary: {}}});
assert.deepEqual(legacy, [{axis: 'Variant', variants: [['primary', {}], ['secondary', {}]]}]);
assert.equal(context.componentUsageText(button), undefined);
assert.equal(context.componentUsageText({...button, usage: '확인에 사용'}), '확인에 사용');
assert.equal(context.componentSwapTargets(button), undefined);
assert.match(code, /componentVariantGroups\(definition\)/);
assert.match(code, /componentUsageText\(definition\)/);
