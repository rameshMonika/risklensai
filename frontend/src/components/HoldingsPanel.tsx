import { FormEvent, useState } from "react";
import { Holding } from "../api/types";
import { Modal } from "./Modal";

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

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Holdings</h2>
        <button type="button" onClick={openAddModal}>
          + Add holding
        </button>
      </div>

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
              <th />
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => (
              <tr key={holding.id}>
                <td>{holding.symbol}</td>
                <td>{holding.quantity}</td>
                <td>${holding.avg_cost.toFixed(2)}</td>
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
            ))}
          </tbody>
        </table>
      )}

      {editingHolding !== null && (
        <Modal title={editingHolding === "new" ? "Add holding" : `Edit ${editingHolding.symbol}`} onClose={closeModal}>
          <form className="holding-form" onSubmit={handleSubmit}>
            <label htmlFor="holding-symbol">Symbol</label>
            <input
              id="holding-symbol"
              placeholder="e.g. AAPL"
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value })}
              maxLength={10}
              required
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
