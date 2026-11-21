import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Action, Notice, Section } from './components.jsx';

const shown = (value, fallback) => (typeof value === 'string' && value.trim() ? value : fallback);

export function WorkspaceHandoffHelp({ capabilities, tr }) {
  if (!capabilities?.devHandoff) return null;
  return (
    <details className="workspace-profile-handoff">
      <summary>{tr('profile.devHandoffTitle')}</summary>
      <p>{tr(capabilities.devInspect ? 'profile.devHandoffInspect' : 'profile.devHandoffDesign')}</p>
      <p>{tr('profile.devHandoffBoundary')}</p>
    </details>
  );
}

export default function WorkspaceProfile({ profile, tr, onSave, onRefresh, onClose, saving = false, busy = false, refreshing = false, error = '' }) {
  const planOptions = Array.isArray(profile?.options?.plans) ? profile.options.plans : [];
  const seatOptions = Array.isArray(profile?.options?.seats) ? profile.options.seats : [];
  const declaredPlan = planOptions.includes(profile?.declared?.plan) ? profile.declared.plan : 'unknown';
  const declaredSeat = seatOptions.includes(profile?.declared?.seat) ? profile.declared.seat : 'unknown';
  const [plan, setPlan] = useState(declaredPlan);
  const [seat, setSeat] = useState(declaredSeat);
  const context = profile?.context || {};
  const capabilities = profile?.capabilities || {};
  const setup = profile?.needsSetup === true;
  const workflow = capabilities.designEdit ? 'edit' : capabilities.designRead ? 'read' : 'none';
  const disabled = saving || busy || refreshing;
  const contextIncomplete = !context.userId || !context.userName || !context.fileKey || !context.pageId;
  const showContextRefresh = contextIncomplete || profile?.storage === 'session';
  const saveErrorKey = error === 'profile-save-failed' ? error : 'unknown';
  const details = useMemo(() => [
    ['userId', 'profile.context.userId'],
    ['fileKey', 'profile.context.fileKey'],
    ['pageId', 'profile.context.pageId'],
    ['apiVersion', 'profile.context.apiVersion'],
    ['pluginVersion', 'profile.context.pluginVersion'],
    ['pluginId', 'profile.context.pluginId'],
    ['locale', 'profile.context.locale'],
  ], []);

  useEffect(() => {
    setPlan(declaredPlan);
    setSeat(declaredSeat);
  }, [profile?.schemaVersion, context.userId, context.fileKey, declaredPlan, declaredSeat]);

  const save = (nextPlan = plan, nextSeat = seat) => onSave?.(nextPlan, nextSeat);
  const rows = [
    ['userName', 'profile.context.userName'],
    ['fileName', 'profile.context.fileName'],
    ['pageName', 'profile.context.pageName'],
  ];

  return (
    <Section
      className="workspace-profile"
      title={tr(setup ? 'profile.setupTitle' : 'profile.settingsTitle')}
      description={tr(setup ? 'profile.setupDescription' : 'profile.settingsDescription')}
    >
      <div className="workspace-profile-context">
        <h3>{tr('profile.observedContext')}</h3>
        <dl>
          {rows.map(([field, label]) => (
            <React.Fragment key={field}>
              <dt>{tr(label)}</dt>
              <dd>{shown(context[field], tr('profile.notAvailable'))}</dd>
            </React.Fragment>
          ))}
          <dt>{tr('profile.context.editorMode')}</dt>
          <dd>
            {shown(context.editorType, tr('profile.notAvailable'))} · {shown(context.mode, tr('profile.notAvailable'))}
          </dd>
        </dl>
        <details className="workspace-profile-technical">
          <summary>{tr('profile.technicalContext')}</summary>
          <dl>
            {details.map(([field, label]) => (
              <React.Fragment key={field}>
                <dt>{tr(label)}</dt>
                <dd>{shown(context[field], tr('profile.notAvailable'))}</dd>
              </React.Fragment>
            ))}
          </dl>
        </details>
        {showContextRefresh && onRefresh && (
          <Action variant="quiet" icon={RefreshCw} disabled={disabled} onClick={onRefresh}>
            {tr(refreshing ? 'profile.refreshingContext' : 'profile.refreshContext')}
          </Action>
        )}
      </div>

      <WorkspaceHandoffHelp capabilities={capabilities} tr={tr} />

      <div className="workspace-profile-declaration">
        <h3>{tr('profile.declarations')}</h3>
        <p>{tr('profile.declarationBoundary')}</p>
        <label>
          {tr('profile.planLabel')}
          <select value={plan} disabled={disabled} onChange={(event) => setPlan(event.target.value)}>
            {planOptions.map((value) => <option key={value} value={value}>{tr('profile.plan.' + value)}</option>)}
          </select>
        </label>
        <label>
          {tr('profile.seatLabel')}
          <select value={seat} disabled={disabled} onChange={(event) => setSeat(event.target.value)}>
            {seatOptions.map((value) => <option key={value} value={value}>{tr('profile.seat.' + value)}</option>)}
          </select>
        </label>
        {!setup && <p className="workspace-profile-source">{tr('profile.workflow.' + workflow)}</p>}
      </div>

      <div className="workspace-profile-storage" data-storage={profile?.storage || 'session'}>
        {tr(profile?.storage === 'local' ? 'profile.storageLocal' : 'profile.storageSession')}
      </div>

      {error && <Notice state="error" title={tr('profile.saveErrorTitle')} body={tr('profile.saveError.' + saveErrorKey)} />}
      {saving && <p role="status" aria-live="polite">{tr('profile.saving')}</p>}
      {busy && !refreshing && <p role="status" aria-live="polite">{tr('profile.operationBusy')}</p>}
      {refreshing && <p role="status" aria-live="polite">{tr('profile.refreshingContext')}</p>}

      <div className="workspace-profile-actions">
        {setup && (
          <Action variant="quiet" disabled={disabled} onClick={() => save('unknown', 'unknown')}>
            {tr('profile.continueUnknown')}
          </Action>
        )}
        <Action variant="primary" disabled={disabled} onClick={() => save()}>
          {tr(saving ? 'profile.saving' : 'profile.save')}
        </Action>
        {!setup && onClose && <Action variant="quiet" disabled={saving || refreshing} onClick={onClose}>{tr('profile.close')}</Action>}
      </div>
    </Section>
  );
}
