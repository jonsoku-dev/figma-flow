const test = require('node:test');
const {checkSupportedWidthReuse} = require('./semantic_component_reuse_oracle.cjs');

test('supported widths share one main and structural geometry keeps its own', checkSupportedWidthReuse);
