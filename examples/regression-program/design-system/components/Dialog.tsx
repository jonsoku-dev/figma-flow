type DialogProps = { label: string };

export function Dialog(props: DialogProps) {
  return { component: 'Dialog', label: props.label };
}
