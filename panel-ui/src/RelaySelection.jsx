import React from 'react';
import { tableFeatures, useTable } from '@tanstack/react-table';

const features = tableFeatures({});
const columns = ['name', 'type', 'id'].map(key => ({accessorKey:key, header:key}));

export default function RelaySelection({ selection, t }) {
  const table = useTable({features, columns, data:selection, getRowId:row => row.id});
  return <table className="relay-layers">
    <caption>{t('relay.selection.title')}</caption>
    <thead><tr>{table.getAllLeafColumns().map(col =>
      <th scope="col" key={col.id}>{t('relay.column.' + col.id)}</th>)}</tr></thead>
    <tbody>{table.getRowModel().rows.map(row => <tr key={row.id}>
      {row.getAllCells().map(cell => <td key={cell.id}>{cell.getValue() || t('relay.selection.unnamed')}</td>)}
    </tr>)}</tbody>
  </table>;
}
