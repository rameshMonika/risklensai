import { useEffect, useRef, useState } from "react";
import { searchSymbols } from "../api/coreClient";
import { SymbolSearchResult } from "../api/types";

interface SymbolComboboxProps {
  value: string;
  onChange: (symbol: string) => void;
  id?: string;
}

const DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

export function SymbolCombobox({ value, onChange, id }: SymbolComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<SymbolSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    const query = value.trim();
    if (query.length < MIN_QUERY_LENGTH) {
      setSuggestions([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const currentRequest = ++requestId.current;
    const timer = setTimeout(async () => {
      try {
        const results = await searchSymbols(query);
        if (currentRequest === requestId.current) setSuggestions(results);
      } catch {
        if (currentRequest === requestId.current) setSuggestions([]);
      } finally {
        if (currentRequest === requestId.current) setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [value]);

  function selectOption(symbol: string) {
    onChange(symbol);
    setIsOpen(false);
  }

  const showDropdown = isOpen && value.trim().length >= MIN_QUERY_LENGTH;

  return (
    <div className="symbol-combobox">
      <input
        id={id}
        placeholder="e.g. AAPL or Apple"
        value={value}
        onChange={(e) => {
          onChange(e.target.value.toUpperCase());
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        maxLength={10}
        autoComplete="off"
        required
      />
      {showDropdown && (
        <ul className="symbol-combobox-list">
          {loading ? (
            <li className="symbol-combobox-status">Searching...</li>
          ) : suggestions.length === 0 ? (
            <li className="symbol-combobox-status">No matches — you can still type a custom symbol.</li>
          ) : (
            suggestions.map((option) => (
              <li
                key={option.symbol}
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectOption(option.symbol);
                }}
              >
                <span className="symbol-combobox-symbol">{option.symbol}</span>
                <span className="symbol-combobox-name">{option.name}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
