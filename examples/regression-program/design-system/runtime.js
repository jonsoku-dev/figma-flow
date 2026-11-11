(() => {
  // examples/regression-program/design-system/components/Button.tsx
  function Button(props) {
    return { component: "Button", label: props.label };
  }

  // examples/regression-program/design-system/components/Field.tsx
  function Field(props) {
    return { component: "Field", label: props.label, value: props.value || "" };
  }

  // examples/regression-program/design-system/components/Table.tsx
  function Table(props) {
    return { component: "Table", label: props.label, columns: props.columns || [], rows: props.rows || [] };
  }

  // examples/regression-program/design-system/components/Dialog.tsx
  function Dialog(props) {
    return { component: "Dialog", label: props.label, open: !!props.open };
  }

  // examples/regression-program/design-system/components/Tabs.tsx
  function Tabs(props) {
    return { component: "Tabs", label: props.label, tabs: props.tabs || [] };
  }

  // examples/regression-program/design-system/components/Nav.tsx
  function Nav(props) {
    return { component: "Nav", label: props.label, items: props.items || [] };
  }

  // examples/regression-program/design-system/entry.js
  globalThis.RegressionDesignSystem = {
    Button,
    Field,
    Table,
    Dialog,
    Tabs,
    Nav
  };
})();
