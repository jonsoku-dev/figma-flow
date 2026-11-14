function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'className') node.className = value;
    else if (key === 'textContent') node.textContent = value;
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, String(value));
  }
  for (const child of children) {
    if (child !== null && child !== undefined) {
      node.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
  }
  return node;
}

function resolveTokenCssVar(tokenRef) {
  return `var(--${String(tokenRef).replace(/\./g, '-')})`;
}

function applyDesignTokensAndVariants(design) {
  const rootStyle = document.documentElement.style;
  for (const [groupName, group] of Object.entries(design.tokens || {})) {
    for (const [tokenKey, tokenDef] of Object.entries(group || {})) {
      if (tokenDef && typeof tokenDef === 'object' && '$value' in tokenDef) {
        rootStyle.setProperty(`--${groupName}-${tokenKey}`, String(tokenDef.$value));
      }
    }
  }
  const rules = [];
  for (const [cmpName, cmpDef] of Object.entries(design.components || {})) {
    for (const [variantName, styleMap] of Object.entries(cmpDef.variants || {})) {
      const decls = Object.entries(styleMap)
        .map(([cssProp, tokenRef]) => `${cssProp}: ${resolveTokenCssVar(tokenRef)};`)
        .join(' ');
      rules.push(`.cmp-${cmpName}--${variantName} { ${decls} }`);
    }
  }
  const styleEl = document.createElement('style');
  styleEl.id = 'canonical-component-styles';
  styleEl.textContent = rules.join('\n');
  document.head.appendChild(styleEl);
}

function idFromSelector(selector, fallback) {
  const match = String(selector || '').match(/#([A-Za-z0-9_-]+)/);
  return match ? match[1] : fallback;
}

function renderFormField(elSpec, stateMap) {
  const props = elSpec.property_values || {};
  const dom = elSpec.dom_source || {};
  const controlSwap = props.control || { component: 'input', variant: 'default' };
  const controlId = dom.label_for || idFromSelector(dom.control_selector, elSpec.id);
  const helpId = dom.error_id || `help-${controlId}`;
  const isError = elSpec.variant === 'error';
  const isDisabled = elSpec.variant === 'disabled' || Boolean(dom.disabled);
  const isCheckbox = controlSwap.component === 'checkbox';

  const labelEl = el('label', { for: controlId, textContent: props.label || elSpec.text });
  const inputAttrs = {
    id: controlId,
    name: controlId,
    type: dom.input_type || (isCheckbox ? 'checkbox' : 'text'),
    className: isCheckbox ? '' : `control-input cmp-${controlSwap.component}--${controlSwap.variant}`,
    required: Boolean(dom.required),
    disabled: isDisabled,
    'aria-invalid': isError ? 'true' : null,
    'aria-describedby': props.showHelp ? helpId : null,
    'data-element-id': elSpec.id,
    'data-family': 'field',
  };
  if (isCheckbox) {
    inputAttrs.checked = stateMap.checked.get(elSpec.id) ?? (controlSwap.variant === 'checked');
  } else {
    inputAttrs.value = isDisabled ? controlId.toUpperCase() : '';
  }
  const inputEl = el('input', inputAttrs);

  const wrapper = el(
    'div',
    {
      className: `field-group cmp-${elSpec.component}--${elSpec.variant}`,
      'data-element-id': elSpec.id,
      'data-variant': elSpec.variant,
    },
    [],
  );

  if (isCheckbox) {
    const controlRow = el('div', { className: `checkbox-row cmp-checkbox--${controlSwap.variant}` }, [
      inputEl,
      labelEl,
    ]);
    wrapper.appendChild(controlRow);
  } else {
    wrapper.appendChild(labelEl);
    wrapper.appendChild(inputEl);
  }

  let helpEl = null;
  if (props.showHelp) {
    helpEl = el('p', {
      id: helpId,
      className: 'field-help',
      role: isError ? 'alert' : null,
      textContent: props.helpText || '',
    });
    wrapper.appendChild(helpEl);
  }

  if (isCheckbox) {
    inputEl.addEventListener('change', () => {
      const checked = inputEl.checked;
      stateMap.checked.set(elSpec.id, checked);
      const nextVariant = checked ? 'default' : 'error';
      const nextControlVariant = checked ? 'checked' : 'unchecked';
      wrapper.dataset.variant = nextVariant;
      wrapper.className = `field-group cmp-field--${nextVariant}`;
      inputEl.parentElement.className = `checkbox-row cmp-checkbox--${nextControlVariant}`;
      inputEl.setAttribute('aria-invalid', checked ? 'false' : 'true');
    });
  }

  return wrapper;
}

function renderRadioGroup(radioSpecs, stateMap) {
  const firstDom = radioSpecs[0].dom_source || {};
  const fieldset = el('fieldset', { className: 'session-group', 'data-family': 'radio' }, [
    el('legend', { textContent: firstDom.fieldset_legend || radioSpecs[0].component }),
  ]);

  const rows = [];
  for (const spec of radioSpecs) {
    const dom = spec.dom_source || {};
    const props = spec.property_values || {};
    const controlId = dom.label_for || idFromSelector(dom.control_selector, spec.id);
    const selected = (stateMap.selectedRadio ?? radioSpecs.find(r => r.variant === 'selected')?.id) === spec.id;
    const radioInput = el('input', {
      id: controlId,
      type: 'radio',
      name: dom.radio_name || 'session_choice',
      value: spec.id,
      checked: selected,
      disabled: spec.variant === 'disabled' || Boolean(dom.disabled),
      'data-element-id': spec.id,
    });
    const labelEl = el('label', { for: controlId, textContent: props.choiceLabel || spec.text });
    const row = el(
      'div',
      {
        className: `radio-row cmp-radio--${selected ? 'selected' : 'unselected'}`,
        'data-element-id': spec.id,
        'data-variant': selected ? 'selected' : 'unselected',
      },
      [radioInput, labelEl],
    );
    rows.push({ spec, row, radioInput });
    fieldset.appendChild(row);
  }

  for (const item of rows) {
    item.radioInput.addEventListener('change', () => {
      if (!item.radioInput.checked) return;
      stateMap.selectedRadio = item.spec.id;
      for (const sibling of rows) {
        const isSel = sibling.spec.id === item.spec.id;
        const nextVar = sibling.spec.variant === 'disabled' ? 'disabled' : isSel ? 'selected' : 'unselected';
        sibling.row.dataset.variant = nextVar;
        sibling.row.className = `radio-row cmp-radio--${nextVar}`;
      }
    });
  }

  return fieldset;
}

function renderTable(rowSpecs, stateMap) {
  const headerSpec = rowSpecs.find(r => r.dom_source?.th_scope === 'col') || rowSpecs[0];
  const bodySpecs = rowSpecs.filter(r => r.id !== headerSpec.id);
  const captionText = headerSpec.dom_source?.table_caption || headerSpec.text;

  const theadRow = el('tr', { 'data-element-id': headerSpec.id });
  const headerCells = String(headerSpec.text || '').split(' / ').slice(0, 2);
  while (headerCells.length < 2) headerCells.push('');
  headerCells.forEach((cellLabel, idx) => {
    const slotKey = idx === 0 ? 'firstCell' : 'secondCell';
    const slotDef = (headerSpec.property_values || {})[slotKey] || { component: 'table-cell', variant: 'header' };
    theadRow.appendChild(
      el('th', {
        scope: 'col',
        className: `cmp-${slotDef.component}--${slotDef.variant}`,
        textContent: cellLabel,
      }),
    );
  });

  const tbody = el('tbody');
  const renderedRows = [];
  for (const rowSpec of bodySpecs) {
    const props = rowSpec.property_values || {};
    const dom = rowSpec.dom_source || {};
    const cells = String(rowSpec.text || '').split(' / ').slice(0, 2);
    while (cells.length < 2) cells.push('');
    const showSecond = props.showSecondCell !== false;
    const isSelected = stateMap.selectedTableRow
      ? stateMap.selectedTableRow === rowSpec.id
      : rowSpec.variant === 'selected';

    const tr = el('tr', {
      tabindex: '0',
      'aria-selected': isSelected ? 'true' : 'false',
      className: `cmp-table-row--${isSelected ? 'selected' : 'default'}`,
      'data-element-id': rowSpec.id,
      'data-variant': isSelected ? 'selected' : 'default',
    });

    const firstDef = props.firstCell || { component: 'table-cell', variant: 'default' };
    const secondDef = props.secondCell || { component: 'table-cell', variant: 'default' };
    tr.appendChild(
      el('th', {
        scope: dom.th_scope || 'row',
        className: `cmp-${firstDef.component}--${firstDef.variant}`,
        textContent: cells[0] || '',
      }),
    );
    tr.appendChild(
      el('td', {
        className: `cmp-${secondDef.component}--${secondDef.variant}${showSecond ? '' : ' hidden-cell'}`,
        'aria-hidden': showSecond ? null : 'true',
        textContent: cells[1] || '',
      }),
    );

    const activateRow = () => {
      stateMap.selectedTableRow = rowSpec.id;
      for (const entry of renderedRows) {
        const active = entry.spec.id === rowSpec.id;
        entry.tr.setAttribute('aria-selected', active ? 'true' : 'false');
        entry.tr.dataset.variant = active ? 'selected' : 'default';
        entry.tr.className = `cmp-table-row--${active ? 'selected' : 'default'}`;
      }
    };
    tr.addEventListener('click', activateRow);
    tr.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activateRow();
      }
    });
    renderedRows.push({ spec: rowSpec, tr });
    tbody.appendChild(tr);
  }

  return el('div', { className: 'table-scroll' }, [
    el('table', { className: 'data-table' }, [
      el('caption', { textContent: captionText }),
      el('thead', {}, [theadRow]),
      tbody,
    ]),
  ]);
}

async function mountFamiliesDemo() {
  const [designRes, graphRes] = await Promise.all([
    fetch('./design.json'),
    fetch('./graph.json'),
  ]);
  const design = await designRes.json();
  const graph = await graphRes.json();
  applyDesignTokensAndVariants(design);

  const screen = design.screens[0];
  const allElements = design.screens.flatMap(s => s.elements);
  const stateMap = {
    checked: new Map(),
    selectedRadio: null,
    selectedTableRow: null,
  };

  const fields = allElements.filter(e => e.component === 'field');
  const radios = allElements.filter(e => e.component === 'radio');
  const undeclaredButtons = allElements.filter(e => e.component === 'action-button');
  const tableRows = allElements.filter(e => e.component === 'table-row');

  const statusOutput = el('p', {
    id: 'form-live-status',
    className: 'status-banner',
    role: 'status',
    'aria-live': 'polite',
    textContent: `${screen.id}: ${design.componentFamilies.length} families`,
  });

  const form = el('form', { className: 'booking-form', novalidate: true }, [
    ...fields.map(fieldSpec => renderFormField(fieldSpec, stateMap)),
    ...(radios.length ? [renderRadioGroup(radios, stateMap)] : []),
    el(
      'div',
      { className: 'form-actions' },
      undeclaredButtons.map(btn =>
        el('button', {
          id: idFromSelector(btn.dom_source?.selector, btn.id),
          type: btn.dom_source?.button_type || 'submit',
          className: `action-button cmp-${btn.component}--${btn.variant}`,
          'data-element-id': btn.id,
          'data-undeclared-family': 'true',
          textContent: btn.text,
        }),
      ),
    ),
    statusOutput,
  ]);

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const participantInput = document.getElementById('id_participant_name');
    const consentInput = document.getElementById('id_safety_consent');
    const selectedRadioEl = form.querySelector('input[type="radio"]:checked');
    statusOutput.textContent = JSON.stringify({
      participant: participantInput ? participantInput.value : '',
      consent: consentInput ? consentInput.checked : false,
      session: selectedRadioEl ? selectedRadioEl.value : '',
      selectedRow: stateMap.selectedTableRow || 'roster-row-1',
    });
  });

  const root = document.getElementById('families-root');
  root.replaceChildren(
    el('header', { className: 'panel panel-header' }, [
      el('h1', { textContent: graph.title }),
      el('p', { className: 'panel-meta', textContent: screen.title }),
    ]),
    el('section', { className: 'panel', 'aria-labelledby': 'heading-form' }, [
      el('h2', { id: 'heading-form', textContent: screen.title }),
      form,
    ]),
    el('section', { className: 'panel', 'aria-labelledby': 'heading-table' }, [
      el('h2', { id: 'heading-table', textContent: tableRows[0]?.dom_source?.table_caption || 'Table' }),
      renderTable(tableRows, stateMap),
    ]),
  );
  root.dataset.mounted = 'true';
}

mountFamiliesDemo();
