type NavProps = { label: string; items?: unknown[] };

export function Nav(props: NavProps) {
  return { component: 'Nav', label: props.label, items: props.items || [] };
}
