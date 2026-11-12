import React from 'react';
import { ArrowDown, ChevronDown, CircleCheck, Clock3, FileText, TriangleAlert } from 'lucide-react';
import { Section } from './components.jsx';

function StepIcon({ status }) {
  const Icon = status === 'failed' ? TriangleAlert : status === 'verified' ? CircleCheck :
    ['requested', 'running'].includes(status) ? Clock3 : FileText;
  return <Icon size={14} strokeWidth={1.5} aria-hidden="true" />;
}

export function ActivitySummary({ activity, tr }) {
  const entries = Object.entries(activity.counts);
  return (
    <Section title={tr('activityTitle')} className="workspace-activity">
      <p className="workspace-activity-caption">{tr('activityBoundary')}</p>
      <div className="workspace-activity-bar" role="img" aria-label={tr('activityChartLabel', {
        counts: entries.map(([state, count]) => tr(state) + ' ' + count).join(', '),
      })}>
        {entries.filter(([, count]) => count).map(([state, count]) => (
          <span key={state} data-state={state} style={{ flexGrow: count }} />
        ))}
      </div>
      <ul className="workspace-activity-counts">
        {entries.map(([state, count]) => (
          <li key={state}><span data-state={state} aria-hidden="true" />{tr(state)} <strong>{count}</strong></li>
        ))}
      </ul>
    </Section>
  );
}

export function ExecutionFlows({ flows, tasks, tr, stateText, date, rememberFocus }) {
  const operation = event => tr(event.operation === 'verification' ? 'verification' :
    event.operation === 'download' ? 'downloadRequested' : 'op.' + event.operation);
  return (
    <div className="workspace-flows">
      {flows.map(({ key, steps }, index) => {
        const first = steps[0], last = steps.at(-1).event;
        const task = tasks.find(item => item.key === first.event.taskKey);
        const firstForTask = flows.findIndex(flow => flow.steps[0].event.taskKey === first.event.taskKey) === index;
        return (
          <details className="workspace-flow" key={key} data-state={last.status}>
            <summary ref={firstForTask ? rememberFocus(first.event.taskKey) : undefined}>
              <StepIcon status={last.status} />
              <span className="workspace-flow-title">{task?.title || tr('removedTask')}</span>
              <span className="workspace-flow-result">{stateText(last)}</span>
              <ChevronDown className="workspace-flow-toggle" size={16} aria-hidden="true" />
              <span className="workspace-flow-context">
                {operation(first.event)} · {tr('flowSteps', { count: steps.length })} · {date(last.time)}
                {!first.current && ' · ' + tr('stale')}
              </span>
            </summary>
            <ol className="workspace-flow-steps">
              {steps.map(({ event, index: eventIndex, current }, stepIndex) => (
                <li key={eventIndex} data-state={event.status}>
                  <span className="workspace-step-mark"><StepIcon status={event.status} /></span>
                  {stepIndex < steps.length - 1 && <ArrowDown className="workspace-step-link" size={12} aria-hidden="true" />}
                  <span className="workspace-step-copy">{operation(event)}<strong>{stateText(event)}</strong></span>
                  <time dateTime={event.time}>{date(event.time)}</time>
                  {!current && <span>{tr('stale')}</span>}
                </li>
              ))}
            </ol>
          </details>
        );
      })}
    </div>
  );
}
