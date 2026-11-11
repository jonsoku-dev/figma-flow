type FieldProps = { label: string };

export function Field(props: FieldProps) {
  return { component: 'Field', label: props.label };
}
