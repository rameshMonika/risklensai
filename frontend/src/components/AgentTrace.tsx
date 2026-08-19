interface AgentTraceProps {
  trajectory: string[];
}

export function AgentTrace({ trajectory }: AgentTraceProps) {
  if (trajectory.length === 0) return null;

  return (
    <div className="agent-trace">
      {trajectory.map((agent, index) => (
        <span key={agent} className="agent-trace-step">
          {agent}
          {index < trajectory.length - 1 && <span className="agent-trace-arrow"> → </span>}
        </span>
      ))}
    </div>
  );
}
