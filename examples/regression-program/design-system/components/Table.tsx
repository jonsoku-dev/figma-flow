type TableProps = { label: string; columns?: string[]; rows?: unknown[][] };

export function Table(props: TableProps) {
  return { component: 'Table', label: props.label, columns: props.columns || [], rows: props.rows || [] };
}
