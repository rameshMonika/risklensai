import { FormEvent, useState } from "react";

interface InvestigationInputProps {
  loading: boolean;
  onSubmit: (question: string) => void;
}

const SAMPLE_QUESTIONS = [
  "What are my holdings?",
  "How concentrated am I?",
  "What's NVDA's 30-day volatility?",
  "Why did NVDA fall this week?",
  "Investigate my portfolio risk",
];

export function InvestigationInput({ loading, onSubmit }: InvestigationInputProps) {
  const [question, setQuestion] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || loading) return;
    onSubmit(question.trim());
  }

  return (
    <section className="panel">
      <h2>Ask about your portfolio risk</h2>
      <form className="investigation-form" onSubmit={handleSubmit}>
        <input
          placeholder="e.g. Why did NVDA fall this week?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Investigating..." : "Ask"}
        </button>
      </form>
      <div className="sample-questions">
        {SAMPLE_QUESTIONS.map((sample) => (
          <button
            key={sample}
            type="button"
            className="link-button"
            disabled={loading}
            onClick={() => onSubmit(sample)}
          >
            {sample}
          </button>
        ))}
      </div>
    </section>
  );
}
