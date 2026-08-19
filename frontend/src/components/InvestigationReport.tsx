import { InvestigationResult } from "../api/types";
import { AgentTrace } from "./AgentTrace";

interface InvestigationReportProps {
  result: InvestigationResult | null;
  loading: boolean;
  error: string | null;
}

export function InvestigationReport({ result, loading, error }: InvestigationReportProps) {
  if (loading) {
    return (
      <section className="panel">
        <p>Running the investigation...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel">
        <p className="auth-error">{error}</p>
      </section>
    );
  }

  if (!result) {
    return null;
  }

  const hasRiskResults = Object.keys(result.risk_results).length > 0;

  return (
    <section className="panel">
      <h2>Result</h2>
      <AgentTrace trajectory={result.trajectory} />

      <p className="investigation-answer">{result.answer}</p>

      {hasRiskResults && (
        <div className="risk-results">
          <h3>Risk metrics</h3>
          {Object.entries(result.risk_results).map(([metric, bySymbol]) => (
            <div key={metric}>
              <strong>{metric}</strong>
              <ul>
                {Object.entries(bySymbol).map(([symbol, value]) => (
                  <li key={symbol}>
                    {symbol}: {(value * 100).toFixed(1)}%
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {result.evidence.length > 0 && (
        <div className="evidence">
          <h3>Evidence</h3>
          <ul>
            {result.evidence.map((item) => (
              <li key={item.source_url}>
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  {item.title}
                </a>{" "}
                ({item.symbol})
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.limitations && (
        <div className="limitations">
          <h3>Limitations</h3>
          <p>{result.limitations}</p>
        </div>
      )}
    </section>
  );
}
