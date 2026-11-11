(function () {
  function Button(props) { return { component: 'Button', label: props.label, variant: props.variant || 'md' }; }
  function Field(props) { return { component: 'Field', label: props.label, value: props.value || '' }; }
  function Table(props) { return { component: 'Table', columns: props.columns || [], rows: props.rows || [] }; }
  function Dialog(props) { return { component: 'Dialog', title: props.title, open: !!props.open }; }
  function Tabs(props) { return { component: 'Tabs', tabs: props.tabs || [] }; }
  function Nav(props) { return { component: 'Nav', items: props.items || [] }; }
  globalThis.RegressionDesignSystem = { Button: Button, Field: Field, Table: Table, Dialog: Dialog, Tabs: Tabs, Nav: Nav };
})();
