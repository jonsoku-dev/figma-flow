// The prepared draft receiver is the sole network endpoint used by the panel.
export async function postDraftReceipt(pair, data, signal) {
  const url = new URL(pair.url);
  if (url.protocol !== 'http:' || url.hostname !== 'localhost' || !url.port ||
      url.pathname !== '/draft-readback' || url.username || url.password || url.search || url.hash ||
      !/^[0-9a-f]{64}$/.test(pair.capability)) {
    throw new Error('An exact prepared local draft pairing is required');
  }
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + pair.capability,
    },
    body: JSON.stringify(data),
    signal,
    redirect: 'error',
  });
  const receipt = await response.json();
  if (typeof receipt?.passed !== 'boolean' || (!response.ok && receipt.passed !== false)) {
    const errors = Array.isArray(receipt?.errors) ? receipt.errors.join('; ') : '';
    throw new Error(errors || receipt?.error || response.status);
  }
  return { passed: response.ok && receipt.passed, receipt };
}
