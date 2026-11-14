import React, { useRef, useState } from 'react';

const urlStyle = { display: 'block', maxWidth: '100%', overflowWrap: 'anywhere', userSelect: 'all', fontSize: 11, lineHeight: '16px' };
const statusStyle = { margin: 0, color: 'var(--muted)', fontSize: 11, lineHeight: '16px' };

/**
 * Host-verified Present link for one carousel run. Opening is a native anchor click so the
 * browser sees the user's own activation; copying selects the visible URL first so a blocked
 * clipboard still leaves it ready for a manual copy.
 */
export function CarouselPresentLink({ link, event, tr }) {
  const urlText = useRef(null);
  const [copy, setCopy] = useState({ url: '', status: '' });
  if (!link || link.taskKey !== event?.taskKey || link.executionId !== event?.executionId) return null;
  function copyLink() {
    const selection = window.getSelection?.();
    let status = 'manual';
    if (urlText.current && selection && document.createRange) {
      const range = document.createRange();
      range.selectNodeContents(urlText.current);
      selection.removeAllRanges();
      selection.addRange(range);
      try { if (document.execCommand('copy')) status = 'copied'; } catch { /* the selected URL stays available for a manual copy */ }
    }
    setCopy({ url: link.url, status });
  }
  const status = copy.url === link.url ? copy.status : '';
  return (
    <div className="workspace-carousel-link" role="group" aria-label={tr('carouselLinkGroup')}
      style={{ flexBasis: '100%', display: 'grid', gap: 6, minWidth: 0, marginTop: 8 }}>
      <div className="workspace-carousel-actions" style={{ justifyContent: 'flex-start' }}>
        <a className="workspace-carousel-open" href={link.url} target="_blank" rel="noopener noreferrer">{tr('carouselLinkOpen')}</a>
        <button type="button" className="workspace-carousel-select" onClick={copyLink}>{tr('carouselLinkCopy')}</button>
      </div>
      <code ref={urlText} style={urlStyle}>{link.url}</code>
      {status && <p className="workspace-carousel-link-status" role="status" style={statusStyle}>
        {tr(status === 'copied' ? 'carouselLinkCopied' : 'carouselLinkCopyManual')}</p>}
    </div>
  );
}
