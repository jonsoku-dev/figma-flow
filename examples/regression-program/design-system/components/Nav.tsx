type NavProps = { label: string };

export function Nav(props: NavProps) {
  return { component: 'Nav', label: props.label };
}
