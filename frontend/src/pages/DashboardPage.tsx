import { useAuth } from "../auth/AuthContext";
import { HoldingsPanel } from "../components/HoldingsPanel";
import { InvestigationInput } from "../components/InvestigationInput";
import { InvestigationReport } from "../components/InvestigationReport";
import { useInvestigation } from "../hooks/useInvestigation";
import { usePortfolio } from "../hooks/usePortfolio";

export function DashboardPage() {
  const { user, logout } = useAuth();
  const { holdings, loading: holdingsLoading, addHolding, updateHolding, removeHolding } = usePortfolio();
  const { result, loading: investigationLoading, error, submit } = useInvestigation();

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <div>
          <h1>Portfolio Risk Investigator</h1>
          <p>{user?.name}</p>
        </div>
        <button className="link-button" onClick={logout}>
          Sign out
        </button>
      </header>

      <HoldingsPanel
        holdings={holdings}
        loading={holdingsLoading}
        onAdd={addHolding}
        onUpdate={updateHolding}
        onRemove={removeHolding}
      />

      <InvestigationInput loading={investigationLoading} onSubmit={submit} />

      <InvestigationReport result={result} loading={investigationLoading} error={error} />

      <footer className="page-footer">
        <p>Data is for informational purposes only and not financial advice.</p>
        <p>Past performance does not guarantee future results.</p>
      </footer>
    </div>
  );
}
