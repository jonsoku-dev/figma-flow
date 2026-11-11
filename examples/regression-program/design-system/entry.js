import * as Button from './components/Button.tsx';
import * as Field from './components/Field.tsx';
import * as Table from './components/Table.tsx';
import * as Dialog from './components/Dialog.tsx';
import * as Tabs from './components/Tabs.tsx';
import * as Nav from './components/Nav.tsx';

globalThis.RegressionDesignSystem = {
  Button: Button.Button,
  Field: Field.Field,
  Table: Table.Table,
  Dialog: Dialog.Dialog,
  Tabs: Tabs.Tabs,
  Nav: Nav.Nav,
};
