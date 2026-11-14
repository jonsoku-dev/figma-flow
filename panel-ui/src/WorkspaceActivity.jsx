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

export function CarouselOverview({ items, tr, onOpenTask, onSelectCarousel, onPresentCarousel, notice }) {
  if (!items.length) return null;
  return (
    <Section title={tr('carouselFileTitle')} className="workspace-carousel-overview">
      <p className="workspace-activity-caption">{tr('carouselFileHelp')}</p>
      {notice && <p className="workspace-carousel-notice" role="status">{notice === 'selected' ? tr('carouselSelected') : notice === 'presented' ? tr('carouselPresented') : notice}</p>}
      <ul className="workspace-carousel-list">
        {items.map(({task, event, carousel}) => {
          const current = event?.revision === task.revision && carousel?.status === 'current';
          return <li key={task.key}>
            <div className="workspace-carousel-list-copy">
              <strong>{task.title}</strong>
              <span>{carousel ? `${tr('carousel' + (current ? 'Current' : 'Changed'))} · ${tr('carouselStateCount', {count: carousel.states.length})}` : tr('carouselReadApply')}</span>
              {carousel && <ul className="workspace-carousel-titles" aria-label={tr('carouselStates')}>
                {carousel.states.map((state, index) => <li key={state.state_id}>{index + 1}. {state.title || state.screen_id}</li>)}
              </ul>}
            </div>
            <div className="workspace-carousel-actions">
              {current && <button type="button" className="workspace-carousel-present"
                onClick={() => onPresentCarousel?.(event, carousel)}>{tr('carouselPresent')}</button>}
              {current && <button type="button" className="workspace-carousel-select"
                onClick={() => onSelectCarousel?.(event, carousel)}>{tr('carouselSelectStart')}</button>}
              <button type="button" className="workspace-carousel-open" onClick={() => onOpenTask(task)}>{tr('carouselOpenTask')}</button>
            </div>
          </li>;
        })}
      </ul>
    </Section>
  );
}

export function ExecutionFlows({ flows, tasks, tr, stateText, date, rememberFocus, onSelectCarousel, onPresentCarousel, carouselNotice }) {
  const operation = event => tr(event.operation === 'verification' ? 'verification' :
    event.operation === 'download' ? 'downloadRequested' : 'op.' + event.operation);
  return (
    <div className="workspace-flows">
      {flows.map(({ key, steps }, index) => {
        const first = steps[0], last = steps.at(-1).event;
        const task = tasks.find(item => item.key === first.event.taskKey);
        const firstForTask = flows.findIndex(flow => flow.steps[0].event.taskKey === first.event.taskKey) === index;
        const carouselStep = [...steps].reverse().find(step => step.event.carousel);
        const carouselEvent = carouselStep?.event;
        const carousel = carouselEvent?.carousel;
        const canSelectStart = carousel?.status === 'current' && !!carouselStep.current
          && !!carouselEvent.executionId && !!carousel.flow_start_node_id;
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
            {carousel && <section className="workspace-carousel" aria-label={tr('carouselTitle')}>
              <div className="workspace-carousel-heading">
                <div><h4>{tr('carouselTitle')}</h4><p>{tr('carouselReadback')} · {tr('carousel' + (carousel.status === 'current' ? 'Current' : 'Changed'))}</p><p>{tr('carouselPlaybackBoundary')}</p></div>
                <div className="workspace-carousel-actions">
                  {canSelectStart && <button type="button" className="workspace-carousel-present"
                    aria-label={tr('carouselPresentLabel', {title: task?.title || carousel.frame_key})}
                    onClick={() => onPresentCarousel?.(carouselEvent, carousel)}>{tr('carouselPresent')}</button>}
                  <button type="button" className="workspace-carousel-select" disabled={!canSelectStart}
                    onClick={() => canSelectStart && onSelectCarousel?.(carouselEvent, carousel)}>{tr('carouselSelectStart')}</button>
                </div>
              </div>
              {carouselNotice && <p className="workspace-carousel-notice" role="status">{carouselNotice === 'selected' ? tr('carouselSelected') : carouselNotice}</p>}
              <ol className="workspace-carousel-states" aria-label={tr('carouselStates')}>
                {carousel.states.map((state, stateIndex) => <li key={state.state_id} data-state={state.status}>
                  <span className="workspace-carousel-index">{stateIndex + 1}</span>
                  <span><strong>{state.title || state.screen_id}</strong><small>{state.screen_id}</small></span>
                  <span className="workspace-carousel-state-status">{tr('carousel' + (state.status === 'current' ? 'Current' : 'Changed'))}</span>
                </li>)}
              </ol>
              <ol className="workspace-carousel-edges" aria-label={tr('carouselTransitions')}>
                {carousel.edges.map((edge, edgeIndex) => {
                  const from = carousel.states.find(state => state.state_id === edge.from), to = carousel.states.find(state => state.state_id === edge.to);
                  const fromTitle = from?.title || from?.screen_id || edge.from;
                  return <li key={edge.edge_id || `${edge.from}-${edge.trigger}-${edge.destination_id}-${edgeIndex}`} data-boundary={edge.boundary || undefined}>
                  <span>{fromTitle} → {edge.boundary === 'stay' ? tr('carouselStay') : to?.title || to?.screen_id || tr('carouselUnknownState')}</span>
                  <span>{edge.boundary === 'stay' ? tr('carouselNoNavigation') : tr('carouselTrigger.' + edge.trigger)}{edge.input ? ` · ${tr('carouselTrigger.' + edge.input)}` : ''}{edge.direction ? ` · ${edge.direction}` : ''}{Number.isFinite(edge.timeout) ? ` · ${edge.timeout}s` : ''}</span>
                </li>;})}
              </ol>
            </section>}
          </details>
        );
      })}
    </div>
  );
}
