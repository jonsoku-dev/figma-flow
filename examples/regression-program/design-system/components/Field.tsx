type FieldProps = { label: string; value?: string };

export function Field(props: FieldProps) {
  return { component: 'Field', label: props.label, value: props.value || '' };
}
