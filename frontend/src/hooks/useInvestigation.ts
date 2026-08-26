import { useCallback, useState } from "react";
import * as coreClient from "../api/coreClient";
import { ApiError, InvestigationResult } from "../api/types";

export function useInvestigation() {
  const [result, setResult] = useState<InvestigationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async (question: string) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const investigation = await coreClient.investigate(question);
      setResult(investigation);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong running the investigation.");
    } finally {
      setLoading(false);
    }
  }, []);

  return { result, loading, error, submit };
}
