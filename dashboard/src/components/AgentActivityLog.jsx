/**
 * Timeline of agent_activity events. Color dot by agent; spinner for started, check for completed.
 */
const AGENT_COLORS = {
  order_intake: 'bg-blue-500',
  inventory: 'bg-green-500',
  procurement: 'bg-purple-500',
  customer_intel: 'bg-orange-500',
  orchestrator: 'bg-gray-500',
};

const AGENT_LABELS = {
  order_intake: 'Order Intake',
  inventory: 'Inventory',
  procurement: 'Procurement',
  customer_intel: 'Customer Intel',
  orchestrator: 'Orchestrator',
};

export default function AgentActivityLog({ events }) {
  return (
    <section className="bg-white rounded-lg border border-gray-200 p-4">
      <h2 className="text-lg font-semibold mb-3">Agent Activity Log</h2>
      {events.length === 0 ? (
        <p className="text-gray-500 text-sm">No activity yet. Events appear here as agents run.</p>
      ) : (
        <ul className="space-y-2 max-h-80 overflow-y-auto">
          {events.map((ev, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span
                className={`mt-1.5 w-2.5 h-2.5 rounded-full shrink-0 ${
                  AGENT_COLORS[ev.agent_name] || 'bg-gray-400'
                }`}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium">{AGENT_LABELS[ev.agent_name] || ev.agent_name}</span>
                  {ev.status === 'started' ? (
                    <span className="inline-block w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                  ) : (
                    <span className="text-green-600">✓</span>
                  )}
                  {ev.duration_ms != null && ev.status === 'completed' && (
                    <span className="text-gray-500">{ev.duration_ms}ms</span>
                  )}
                </div>
                {ev.summary && <p className="text-gray-600 mt-0.5">{ev.summary}</p>}
                {ev.timestamp && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
