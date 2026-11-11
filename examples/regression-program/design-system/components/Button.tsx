type ButtonProps = { label: string };

export function Button(props: ButtonProps) {
  return { component: 'Button', label: props.label };
}
