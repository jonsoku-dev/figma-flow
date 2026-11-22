import { useEffect, useState } from 'react';
import { QueryClient, useQuery } from '@tanstack/react-query';

const empty = { status: 'offline', selection: [], selectionTotal: 0 };
const states = new Set(['live', 'offline', 'busy', 'uncertain']);
const nonempty = value => typeof value === 'string' && value.trim() ? value : '';

export function useRelaySnapshot(send) {
  const [client] = useState(() => new QueryClient());
  const [channel] = useState(() => {
    const nonce = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    return { nonce, key: ['viewer', nonce], session: null, fileKey: '', complete: null };
  });
  useEffect(() => {
    function receive(event) {
      const msg = event.data?.pluginMessage;
      if (msg?.type !== 'workspace-relay-viewer-state' || msg.requestId !== channel.nonce ||
          !states.has(msg.status) || typeof msg.workspaceSession !== 'string' ||
          !/^[A-Za-z0-9_-]{1,160}$/.test(msg.workspaceSession) ||
          (channel.session && channel.session !== msg.workspaceSession)) return;
      if (!msg.file || (msg.file.key !== null && typeof msg.file.key !== 'string') ||
          !msg.page || (msg.page.id !== null && typeof msg.page.id !== 'string')) return;
      channel.session = msg.workspaceSession;
      channel.fileKey = nonempty(msg.file.key);
      const selection = Array.isArray(msg.selection) ? msg.selection.slice(0,20).filter(item =>
        typeof item?.id === 'string' && typeof item?.type === 'string' && typeof item?.name === 'string') : [];
      const snapshot = {
        status:msg.status, file:msg.file, page:msg.page, selection,
        selectionTotal:Number.isInteger(msg.selectionTotal) ? Math.max(selection.length,msg.selectionTotal) : selection.length,
        selectionTruncated:msg.selectionTruncated === true,
        lastOkAt:nonempty(msg.lastOkAt), lastResult:['ok','error','uncertain'].includes(msg.lastResult) ? msg.lastResult : null,
        profile:msg.profile && typeof msg.profile === 'object' ? msg.profile : null, error:nonempty(msg.error),
      };
      if (Object.hasOwn(msg, 'locale')) {
        const languages = navigator.languages.map(tag => tag.toLowerCase().split('-')[0]);
        const locale = msg.locale ?? languages.find(code => window.FlowUI.locales.includes(code)) ?? window.FlowUI.locales[0];
        if (locale !== window.FlowUI.locale) window.FlowUI.setLocale(locale);
      }
      // Selection changes can arrive between polls. Publish them immediately.
      client.setQueryData(channel.key, snapshot);
      channel.complete?.();
    }
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [channel, client]);

  const query = useQuery({
    queryKey: channel.key,
    queryFn: ({signal}) => new Promise((resolve, reject) => {
      const finish = error => {
        clearTimeout(timer);
        signal.removeEventListener('abort', abort);
        channel.complete = null;
        if (error) reject(error);
        else resolve(client.getQueryData(channel.key));
      };
      const abort = () => finish(new Error('Viewer closed'));
      const timer = setTimeout(() => finish(new Error('No host update')), 5000);
      signal.addEventListener('abort', abort, {once:true});
      channel.complete = () => finish();
      send(channel.session ? {type:'workspace-control-tick', workspaceSession:channel.session, fileKey:channel.fileKey}
        : {type:'workspace-home-ready', locale:window.FlowUI.locale, requestId:channel.nonce});
    }),
    retry:false, refetchInterval:1000, refetchIntervalInBackground:true, refetchOnWindowFocus:false,
    refetchOnReconnect:false, networkMode:'always', gcTime:0,
  }, client);
  if (query.isError && query.data?.status !== 'busy') return empty;
  return query.data || empty;
}
