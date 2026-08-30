import { FormEvent, useEffect, useState } from "react";
import * as coreClient from "../api/coreClient";
import { Holding } from "../api/types";
import { Modal } from "./Modal";
import { SymbolCombobox } from "./SymbolCombobox";

interface HoldingsPanelProps {
  holdings: Holding[];
  loading: boolean;
  onAdd: (input: Omit<Holding, "id">) => Promise<void>;
  onUpdate: (id: number, input: Omit<Holding, "id">) => Promise<void>;
  onRemove: (id: number) => Promise<void>;
}

interface HoldingFormState {
  symbol: string;
  quantity: string;
  avgCost: string;
}

const EMPTY_FORM: HoldingFormState = { symbol: "", quantity: "", avgCost: "" };

export function HoldingsPanel({ holdings, loading, onAdd, onUpdate, onRemove }: HoldingsPanelProps) {
  // Null when the modal is closed. A Holding when editing an existing row,
  // or the literal "new" when adding one — one modal handles both.
  const [editingHolding, setEditingHolding] = useState<Holding | "new" | null>(null);
  const [form, setForm] = useState<HoldingFormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  // symbol -> current price. Absent (rather than 0) means "not fetched yet
  // or unavailable" so the table can distinguish that from a real $0 price.
  const [currentPrices, setCurrentPrices] = useState<Record<string, number>>({});
  const [quotesLoading, setQuotesLoading] = useState(false);

  useEffect(() => {
    if (holdings.length === 0) return;

    let cancelled = false;
    const symbols = [...new Set(holdings.map((h) => h.symbol))];

    setQuotesLoading(true);
    coreClient
      .getQuotes(symbols)
      .then((quotes) => {
        if (cancelled) return;
        setCurrentPrices(Object.fromEntries(quotes.map((q) => [q.symbol, q.price])));
      })
      .catch((error) => {
        // Fail visibly (console) rather than silently leaving prices blank
        // with no indication anything went wrong.
        console.error("Failed to load current prices:", error);
      })
      .finally(() => {
        if (!cancelled) setQuotesLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // Re-fetch whenever the set of held symbols changes (add/remove/edit),
    // not on every holdings re-render (quantity/avg_cost edits don't need a
    // fresh quote).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holdings.map((h) => h.symbol).join(",")]);

  function openAddModal() {
    setForm(EMPTY_FORM);
    setEditingHolding("new");
  }

  function openEditModal(holding: Holding) {
    setForm({
      symbol: holding.symbol,
      quantity: String(holding.quantity),
      avgCost: String(holding.avg_cost),
    });
    setEditingHolding(holding);
  }

  function closeModal() {
    setEditingHolding(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form.symbol || !form.quantity || !form.avgCost || editingHolding === null) return;

    const input = {
      symbol: form.symbol.toUpperCase(),
      quantity: Number(form.quantity),
      avg_cost: Number(form.avgCost),
    };

    setSubmitting(true);
    try {
      if (editingHolding === "new") {
        await onAdd(input);
      } else {
        await onUpdate(editingHolding.id, input);
      }
      closeModal();
    } finally {
      setSubmitting(false);
    }
  }

  // Only holdings whose current price actually came back -- so the total
  // and its cost comparison are always apples-to-apples, never mixing a
  // real quote for one symbol with a stale/missing one for another.
  const pricedHoldings = holdings.filter((h) => currentPrices[h.symbol] !== undefined);
  const totalCurrentValue = pricedHoldings.reduce((sum, h) => sum + h.quantity * currentPrices[h.symbol], 0);
  const totalCostValue = pricedHoldings.reduce((sum, h) => sum + h.quantity * h.avg_cost, 0);
  const totalDelta = totalCurrentValue - totalCostValue;
  const totalDeltaPercent = totalCostValue > 0 ? (totalDelta / totalCostValue) * 100 : 0;
  const isPartial = pricedHoldings.length > 0 && pricedHoldings.length < holdings.length;

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Holdings</h2>
        <button type="button" onClick={openAddModal}>
          + Add holding
        </button>
      </div>

      {!loading && holdings.length > 0 && (
        <div className="portfolio-summary">
          <div className="portfolio-summary-value">
            <span className="portfolio-summary-label">Total value</span>
            <strong>
              {pricedHoldings.length > 0
                ? `$${totalCurrentValue.toFixed(2)}`
                : quotesLoading
                  ? "Calculating..."
                  : "Unavailable"}
            </strong>
          </div>
          {pricedHoldings.length > 0 && (
            <div className={`portfolio-summary-delta ${totalDelta >= 0 ? "delta-positive" : "delta-negative"}`}>
              {totalDelta >= 0 ? "▲" : "▼"} ${Math.abs(totalDelta).toFixed(2)} (
              {totalDeltaPercent >= 0 ? "+" : ""}
              {totalDeltaPercent.toFixed(2)}%) vs. cost
            </div>
          )}
          {isPartial && (
            <span className="portfolio-summary-note">
              ({pricedHoldings.length} of {holdings.length} symbols priced)
            </span>
          )}
        </div>
      )}

      {loading ? (
        <p>Loading holdings...</p>
      ) : holdings.length === 0 ? (
        <p>No holdings yet — add one above.</p>
      ) : (
        <table className="holdings-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Quantity</th>
              <th>Avg cost</th>
              <th>Current cost</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => {
              const currentPrice = currentPrices[holding.symbol];
              return (
              <tr key={holding.id}>
                <td>{holding.symbol}</td>
                <td>{holding.quantity}</td>
                <td>${holding.avg_cost.toFixed(2)}</td>
                <td>
                  {currentPrice !== undefined
                    ? `$${currentPrice.toFixed(2)}`
                    : quotesLoading
                      ? "Loading..."
                      : "Unavailable"}
                </td>
                <td className="holdings-row-actions">
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Edit ${holding.symbol}`}
                    onClick={() => openEditModal(holding)}
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remove ${holding.symbol}`}
                    onClick={() => onRemove(holding.id)}
                  >
                    🗑
                  </button>
                </td>
              </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {editingHolding !== null && (
        <Modal title={editingHolding === "new" ? "Add holding" : `Edit ${editingHolding.symbol}`} onClose={closeModal}>
          <form className="holding-form" onSubmit={handleSubmit}>
            <label htmlFor="holding-symbol">Symbol</label>
            <SymbolCombobox
              id="holding-symbol"
              value={form.symbol}
              onChange={(symbol) => setForm({ ...form, symbol })}
            />

            <label htmlFor="holding-quantity">Quantity</label>
            <input
              id="holding-quantity"
              type="number"
              min="0"
              step="any"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
              required
            />

            <label htmlFor="holding-avg-cost">Avg cost</label>
            <input
              id="holding-avg-cost"
              type="number"
              min="0"
              step="any"
              value={form.avgCost}
              onChange={(e) => setForm({ ...form, avgCost: e.target.value })}
              required
            />

            <button type="submit" disabled={submitting}>
              {submitting ? "Saving..." : editingHolding === "new" ? "Add holding" : "Save changes"}
            </button>
          </form>
        </Modal>
      )}
    </section>
  );
}
