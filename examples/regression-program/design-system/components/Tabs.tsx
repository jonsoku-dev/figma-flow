type TabsProps = { label: string; tabs?: string[] };

export function Tabs(props: TabsProps) {
  return { component: 'Tabs', label: props.label, tabs: props.tabs || [] };
}
