const assert = require('node:assert/strict');
const {renderAuditExport} = require('../figma-bridge/audit_log.js');
const value = 'https://alice:fixture-secret@example.test/font.woff2?token=fixture-query#private';
const exported = renderAuditExport({input_summary:[{ref:value,source:value,kind:'font',status:'external-unverified'}]});
assert.ok(!JSON.stringify(exported).includes('fixture-secret'), 'diagnostic export must redact URL userinfo independently');
assert.ok(!JSON.stringify(exported).includes('fixture-query'), 'diagnostic export must redact query credentials');
assert.ok(JSON.stringify(exported).includes('example.test'));
console.log('Diagnostic JSON and text redact URL credentials while preserving safe origin.');
