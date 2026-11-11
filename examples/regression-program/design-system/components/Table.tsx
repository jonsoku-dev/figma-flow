type TableProps = { label: string };

export function Table(props: TableProps) {
  return { component: 'Table', label: props.label };
}
