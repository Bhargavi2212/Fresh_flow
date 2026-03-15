const STEPS = [
  { key: 'order_intake', label: 'Parsing your order...' },
  { key: 'inventory', label: 'Checking inventory...' },
  { key: 'procurement', label: 'Securing stock...' },
  { key: 'customer_intel', label: 'Reviewing your account...' },
  { key: 'order_confirmed', label: 'Order confirmed!' },
];

function stepTrigger(ev, step) {
  if (step.key === 'order_confirmed') return ev.type === 'order_confirmed';
  return ev.type === 'agent_activity' && ev.agent_name === step.key;
}

function stepStatus(events, step, currentStepIndex) {
  const started = events.find((ev) => stepTrigger(ev, step) && ev.status === 'started');
  const completed = events.find(
    (ev) =>
      (step.key === 'order_confirmed' && ev.type === 'order_confirmed') ||
      (ev.type === 'agent_activity' && ev.agent_name === step.key && ev.status === 'completed')
  );
  const failed = events.find(
    (ev) => ev.type === 'agent_activity' && ev.agent_name === step.key && ev.status === 'failed'
  );
  if (failed) return 'failed';
  if (completed) return 'complete';
  if (started) return 'in_progress';
  return 'pending';
}

export default function OrderProgress({ events, status }) {
  const hasProcurement = events.some((e) => e.type === 'agent_activity' && e.agent_name === 'procurement');
  const stepsToShow = hasProcurement ? STEPS : STEPS.filter((s) => s.key !== 'procurement');

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Order Status</h3>
      <ul className="space-y-2">
        {stepsToShow.map((step, idx) => {
          const stepStatusVal = stepStatus(events, step, idx);
          return (
            <li key={step.key} className="flex items-center gap-3 text-sm">
              {stepStatusVal === 'pending' && (
                <span className="text-gray-400" aria-hidden>○</span>
              )}
              {stepStatusVal === 'in_progress' && (
                <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-teal-500 border-t-transparent" />
              )}
              {stepStatusVal === 'complete' && (
                <span className="text-green-600" aria-hidden>✅</span>
              )}
              {stepStatusVal === 'failed' && (
                <span className="text-red-600" aria-hidden>❌</span>
              )}
              <span className={stepStatusVal === 'complete' ? 'text-green-700' : stepStatusVal === 'failed' ? 'text-red-700' : 'text-gray-700'}>
                {step.label}
              </span>
              {stepStatusVal === 'complete' && (() => {
                const ev = events.find(
                  (e) =>
                    (step.key === 'order_confirmed' && e.type === 'order_confirmed') ||
                    (e.type === 'agent_activity' && e.agent_name === step.key && e.status === 'completed')
                );
                const ms = ev?.duration_ms;
                return ms != null ? <span className="text-gray-500 ml-1">({ms}ms)</span> : null;
              })()}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
