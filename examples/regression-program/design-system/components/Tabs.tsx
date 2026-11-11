type TabsProps = { label: string };

export function Tabs(props: TabsProps) {
  return { component: 'Tabs', label: props.label };
}
