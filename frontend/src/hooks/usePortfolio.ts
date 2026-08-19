import { useCallback, useEffect, useState } from "react";
import * as coreClient from "../api/coreClient";
import { Holding } from "../api/types";

export function usePortfolio() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    coreClient.getHoldings().then((data) => {
      setHoldings(data);
      setLoading(false);
    });
  }, []);

  const addHolding = useCallback(async (input: Omit<Holding, "id">) => {
    const holding = await coreClient.addHolding(input);
    setHoldings((current) => [...current, holding]);
  }, []);

  const updateHolding = useCallback(async (id: number, input: Omit<Holding, "id">) => {
    const holding = await coreClient.updateHolding(id, input);
    setHoldings((current) => current.map((h) => (h.id === id ? holding : h)));
  }, []);

  const removeHolding = useCallback(async (id: number) => {
    await coreClient.removeHolding(id);
    setHoldings((current) => current.filter((h) => h.id !== id));
  }, []);

  return { holdings, loading, addHolding, updateHolding, removeHolding };
}
