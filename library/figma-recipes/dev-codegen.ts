if (figma.editorType !== 'dev' || figma.mode !== 'codegen') {
  figma.closePlugin('Open this recipe as a Dev Mode code generation plugin.');
} else {
  figma.codegen.on('generate', ({ node }): CodegenResult[] => [{
    title: 'Selected node geometry',
    language: 'JSON',
    code: JSON.stringify({
      id: node.id,
      name: node.name,
      type: node.type,
      width: node.width,
      height: node.height,
    }, null, 2),
  }]);
}
