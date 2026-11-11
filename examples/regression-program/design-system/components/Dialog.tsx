type DialogProps = { label: string; open?: boolean };

export function Dialog(props: DialogProps) {
  return { component: 'Dialog', label: props.label, open: !!props.open };
}
