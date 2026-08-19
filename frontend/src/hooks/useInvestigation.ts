import { useCallback, useState } from "react";
import { InvestigationResult } from "../api/types";

export function useInvestigation() {
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // TODO: wire up to coreClient once the Core service exposes
  // POST /investigations (see CLAUDE.md's Backend architecture).
  const submit = useCallback(async (_question: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setError("Investigations aren't connected to the backend yet.");
    setLoading(false);
  }, []);

  return { result, loading, error, submit };
}
