import {
  faChartLine,
  faChartPie,
  faCircleCheck,
  faCircleInfo,
  faCircleXmark,
  faTriangleExclamation,
  faUpRightFromSquare,
  faUser,
} from "@fortawesome/free-solid-svg-icons";
import type { IconDefinition } from "@fortawesome/free-solid-svg-icons";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { InvestigationResult } from "../api/types";
import { AgentTrace } from "./AgentTrace";

interface InvestigationReportProps {
  result: InvestigationResult | null;
  loading: boolean;
  error: string | null;
}

const STATUS_META: Record<InvestigationResult["status"], { label: string; icon: IconDefinition }> = {
  completed: { label: "Analysis complete", icon: faCircleCheck },
  refused: { label: "Request refused", icon: faCircleXmark },
  not_found: { label: "Data not available", icon: faTriangleExclamation },
};

function topEntry(record: Record<string, number> | undefined): [string, number] | null {
  if (!record) return null;
  const entries = Object.entries(record);
  if (entries.length === 0) return null;
  return entries.reduce((best, current) => (current[1] > best[1] ? current : best));
}

function formatSigned(value: number, decimals: number): string {
  const fixed = value.toFixed(decimals);
  return value >= 0 ? `+${fixed}` : fixed;
}

// Phrase alone, no trailing "with" -- callers append that themselves, since
// the grouped ("X is ... with A and B") and pairwise ("A and B are ... (v)")
// sentence shapes need it in different places.
function describeCorrelation(r: number): string {
  const magnitude = Math.abs(r);
  if (magnitude < 0.05) return "essentially uncorrelated";
  if (magnitude < 0.3) return r >= 0 ? "weakly positively correlated" : "weakly negatively correlated";
  if (magnitude < 0.7) return r >= 0 ? "moderately positively correlated" : "moderately negatively correlated";
  return r >= 0 ? "highly positively correlated" : "highly negatively correlated";
}

function joinWithAnd(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? "";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

// One sentence covering every pair in the matrix: the anchor symbol (the
// primary risk driver, when there is one) gets its relationships to every
// other holding grouped into one clause, then any remaining pair not
// involving the anchor gets its own clause. Scales to whatever holding count
// the portfolio has (MVP caps at ~5-10 -- see CLAUDE.md), not just 3.
function buildCorrelationSummary(
  correlationMatrix: Record<string, Record<string, number>>,
  anchorSymbol: string | null,
): string {
  const symbols = Object.keys(correlationMatrix);
  const pairKey = (a: string, b: string) => [a, b].sort().join("|");
  const donePairs = new Set<string>();
  const clauses: string[] = [];

  if (anchorSymbol && correlationMatrix[anchorSymbol]) {
    const others = symbols.filter((s) => s !== anchorSymbol);
    if (others.length > 0) {
      const worst = others.reduce((a, b) =>
        Math.abs(correlationMatrix[anchorSymbol][b]) > Math.abs(correlationMatrix[anchorSymbol][a]) ? b : a,
      );
      const descriptor = describeCorrelation(correlationMatrix[anchorSymbol][worst]);
      const parts = others.map((s) => `${s} (${correlationMatrix[anchorSymbol][s].toFixed(3)})`);
      clauses.push(`${anchorSymbol} is ${descriptor} with ${joinWithAnd(parts)}`);
      others.forEach((s) => donePairs.add(pairKey(anchorSymbol, s)));
    }
  }

  for (let i = 0; i < symbols.length; i++) {
    for (let j = i + 1; j < symbols.length; j++) {
      const [a, b] = [symbols[i], symbols[j]];
      if (donePairs.has(pairKey(a, b))) continue;
      donePairs.add(pairKey(a, b));
      const value = correlationMatrix[a][b];
      clauses.push(`${a} and ${b} are ${describeCorrelation(value)} (${value.toFixed(3)})`);
    }
  }

  return clauses.length > 0 ? `${clauses.join("; ")}.` : "";
}

// The Report Agent's prompt isn't changed by this UI -- it still only
// guarantees a literal "Limitations" heading, not a separate "Interpretation"
// one. So everything before that heading (quantitative summary + news
// narrative + interpretation, all as one prose block) is treated as the
// "interpretation" half here, rather than a clean single paragraph.
function splitReport(markdown: string): { interpretation: string; limitations: string | null } {
  const match = markdown.match(/#{0,2}\s*Limitations\s*\n?/i);
  if (!match || match.index === undefined) {
    return { interpretation: markdown.trim(), limitations: null };
  }
  const interpretation = markdown
    .slice(0, match.index)
    .replace(/#{0,2}\s*Interpretation\s*\n?/i, "")
    .trim();
  const limitations = markdown.slice(match.index + match[0].length).trim();
  return { interpretation: interpretation || markdown.trim(), limitations: limitations || null };
}

// The model tends to head its own quantitative-summary paragraph "Quantitative
// Risk Summary" before "News Narrative", duplicating the deterministic cards
// already rendered elsewhere on this page. Drop everything before "News
// Narrative" (keeping that heading itself and everything after it); if the
// model didn't use it this time, fail open and keep the full text rather
// than lose content.
function dropQuantSummaryHeading(text: string): string {
  const match = text.match(/#{0,3}\s*\*{0,2}News Narrative\*{0,2}\s*\n?/i);
  if (!match || match.index === undefined) return text;
  return text.slice(match.index).trim();
}

// Tavily doesn't return a publisher name, only a URL -- derive a readable
// source label from the hostname, with known outlets mapped to their proper
// display name and a titleized fallback for anything else.
const KNOWN_SOURCE_LABELS: Record<string, string> = {
  "fool.com": "The Motley Fool",
  "investors.com": "Investor's Business Daily",
  "barrons.com": "Barron's",
  "investopedia.com": "Investopedia",
  "reuters.com": "Reuters",
  "bloomberg.com": "Bloomberg",
  "cnbc.com": "CNBC",
  "wsj.com": "The Wall Street Journal",
  "marketwatch.com": "MarketWatch",
  "seekingalpha.com": "Seeking Alpha",
  "finance.yahoo.com": "Yahoo Finance",
};

function deriveSourceLabel(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (KNOWN_SOURCE_LABELS[host]) return KNOWN_SOURCE_LABELS[host];
    const name = host.split(".")[0];
    return name.charAt(0).toUpperCase() + name.slice(1);
  } catch {
    return "Source";
  }
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

  const statusMeta = STATUS_META[result.status];

  const lossContribution = result.risk_results.loss_contribution;
  const sectorExposure = result.risk_results.sector_exposure;
  const isFullInvestigation = Boolean(result.concentration && lossContribution && sectorExposure);

  const primaryDriver = topEntry(lossContribution);
  const topSector = topEntry(sectorExposure);

  const correlationSummary = result.correlation_matrix
    ? buildCorrelationSummary(result.correlation_matrix, primaryDriver?.[0] ?? null)
    : "";

  const { interpretation: rawInterpretation, limitations } = splitReport(result.answer);
  const interpretation = dropQuantSummaryHeading(rawInterpretation);
  // Only Report-style answers (News/full-investigation routes) are
  // guaranteed a "Limitations" heading -- a plain Answer Agent sentence
  // never has one, so that's the signal to keep showing it as the original
  // single blue callout instead of splitting it into two boxes.
  const isReportStyle = limitations !== null;

  return (
    <section className="panel">
      <h2>Result</h2>
      <AgentTrace trajectory={result.trajectory} />

      <div className={`status-badge status-${result.status}`}>
        <span className="status-icon">
          <FontAwesomeIcon icon={statusMeta.icon} />
        </span>
        {statusMeta.label}
      </div>

      {!isReportStyle && (
        <div className="answer-callout">
          <span className="answer-callout-icon">
            <FontAwesomeIcon icon={faCircleInfo} />
          </span>
          <div className="investigation-answer">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.answer}</ReactMarkdown>
          </div>
        </div>
      )}

      {isFullInvestigation && (
        <div className="result-section">
          <h3>Key findings</h3>
          <div className="key-findings-grid">
            {result.concentration && (
              <div className="key-finding-card">
                <span className="key-finding-icon">
                  <FontAwesomeIcon icon={faUser} />
                </span>
                <div>
                  <div className="key-finding-label">Largest holding</div>
                  <div className="key-finding-value">
                    {result.concentration.largest_holding_symbol},{" "}
                    {(result.concentration.largest_holding_weight * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            )}
            {primaryDriver && (
              <div className="key-finding-card">
                <span className="key-finding-icon">
                  <FontAwesomeIcon icon={faChartLine} />
                </span>
                <div>
                  <div className="key-finding-label">Primary risk driver</div>
                  <div className="key-finding-value">
                    {primaryDriver[0]} loss contribution, {(primaryDriver[1] * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            )}
            {topSector && (
              <div className="key-finding-card">
                <span className="key-finding-icon">
                  <FontAwesomeIcon icon={faChartPie} />
                </span>
                <div>
                  <div className="key-finding-label">Sector exposure</div>
                  <div className="key-finding-value">
                    {topSector[0]}, {(topSector[1] * 100).toFixed(1)}%
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {result.concentration && (
        <div className="result-section">
          <h3>Concentration</h3>
          <div className="concentration-table">
            <div className="concentration-row concentration-header">
              <span>Symbol</span>
              <span />
              <span className="concentration-pct">Allocation</span>
            </div>
            {Object.entries(result.concentration.weights).map(([symbol, weight]) => (
              <div className="concentration-row" key={symbol}>
                <span className="concentration-symbol">{symbol}</span>
                <div className="concentration-bar-track">
                  <div
                    className={
                      "concentration-bar-fill" +
                      (symbol === result.concentration!.largest_holding_symbol ? " is-largest" : "")
                    }
                    style={{ width: `${Math.min(weight * 100, 100)}%` }}
                  />
                </div>
                <span className="concentration-pct">{(weight * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {isFullInvestigation && (
        <div className="result-section">
          <h3>Quantitative risk summary</h3>
          <div className="metrics-grid">
            {result.risk_results.volatility && (
              <div className="metric-card">
                <div className="metric-card-header">
                  <strong>Volatility</strong>
                  <span className="metric-subtitle">(annualized)</span>
                </div>
                <p className="metric-card-line">
                  {Object.entries(result.risk_results.volatility)
                    .map(([symbol, value]) => `${symbol} ${value.toFixed(3)}`)
                    .join(", ")}
                </p>
              </div>
            )}

            {result.risk_results.max_drawdown && (
              <div className="metric-card">
                <div className="metric-card-header">
                  <strong>Max drawdown</strong>
                  <span className="metric-subtitle">(historical)</span>
                </div>
                <p className="metric-card-line">
                  {Object.entries(result.risk_results.max_drawdown)
                    .map(([symbol, value]) => `${symbol} ${(value * 100).toFixed(1)}%`)
                    .join(", ")}
                </p>
              </div>
            )}

            {result.concentration && (
              <div className="metric-card">
                <div className="metric-card-header">
                  <strong>Concentration</strong>
                </div>
                <p className="metric-card-line">
                  Largest holding {result.concentration.largest_holding_symbol}{" "}
                  {(result.concentration.largest_holding_weight * 100).toFixed(1)}% of portfolio weight.
                </p>
              </div>
            )}

            {sectorExposure && (
              <div className="metric-card">
                <div className="metric-card-header">
                  <strong>Sector exposure</strong>
                </div>
                <p className="metric-card-line">
                  {Object.entries(sectorExposure)
                    .sort(([, a], [, b]) => b - a)
                    .map(([sector, value]) => `${sector} ${(value * 100).toFixed(1)}%`)
                    .join(", ")}
                </p>
              </div>
            )}

            {correlationSummary && (
              <div className="metric-card">
                <div className="metric-card-header">
                  <strong>Correlation matrix</strong>
                </div>
                <p className="metric-card-line">{correlationSummary}</p>
              </div>
            )}

            {lossContribution && (
              <div className="metric-card">
                <div className="metric-card-header">
                  <strong>Loss contribution</strong>
                  <span className="metric-subtitle">(relative)</span>
                </div>
                <p className="metric-card-line">
                  {Object.entries(lossContribution)
                    .sort(([, a], [, b]) => b - a)
                    .map(([symbol, value]) => `${symbol} ${formatSigned(value, 3)}`)
                    .join(", ")}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {result.evidence.length > 0 && (
        <div className="result-section">
          <h3>News-based narrative</h3>
          <div className="news-narrative-list">
            {result.evidence.map((item) => (
              <div className="news-narrative-row" key={item.source_url}>
                <span className="news-source-pill">{deriveSourceLabel(item.source_url)}</span>
                <div>
                  <a
                    className="news-narrative-title"
                    href={item.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    &ldquo;{item.title}&rdquo;
                    <FontAwesomeIcon icon={faUpRightFromSquare} className="news-narrative-link-icon" />
                  </a>
                  {item.evidence_text && <div className="news-narrative-snippet">{item.evidence_text}</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {isReportStyle && (
        <div className="result-section callout callout-interpretation">
          <h3>Interpretation</h3>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{interpretation}</ReactMarkdown>
        </div>
      )}

      {isReportStyle && limitations && (
        <div className="result-section callout callout-limitations">
          <h3>Limitations</h3>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{limitations}</ReactMarkdown>
        </div>
      )}

    </section>
  );
}
