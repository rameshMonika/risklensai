"""Build-time router calibration -- run manually whenever calibration data
changes (per CLAUDE.md's routing methodology). Ports notebook cell 34
(current, fixed version): fits KMeans centroids per intent, no threshold
search -- refusal is the guardrail's job now, not the router's (see
CLAUDE.md's resolved-bug note).

Usage (from agent_service/):
    uv run python scripts/calibrate_router.py

Writes src/agent_service/calibration/router_calibration.json, which
graph/router.py loads at import time -- not recomputed at request time or
server startup.
"""

import json
from pathlib import Path

import numpy as np
import truststore

truststore.inject_into_ssl()

from semantic_router.encoders import HuggingFaceEncoder
from sklearn.cluster import KMeans

from agent_service.graph.intents import ROUTE_UTTERANCES

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "src" / "agent_service" / "calibration" / "router_calibration.json"

CALIBRATION_UTTERANCES = {
    "holdings": [
        "Tell me what I own.",
        "What's currently in my portfolio?",
        "List my investments.",
        "Show me everything I hold.",
        "What assets am I currently holding?",
        "Summarize my current positions.",
        "What's in my account right now?",
        "Break down what I own.",
    ],
    "concentration": [
        "Do I have too much in one position?",
        "What's my biggest exposure?",
        "Is my portfolio well diversified?",
        "Am I too heavily weighted in a single stock?",
        "How spread out are my investments?",
        "Which single holding makes up the largest share of my portfolio?",
        "Do I have concentration risk?",
        "Is one company too big a chunk of my portfolio?",
        "Which of my positions is the biggest?",
        "What's my largest single holding?",
    ],
    "symbol_risk": [
        "How risky is this holding?",
        "What's the price volatility on this stock?",
        "How far has this stock fallen from its high?",
        "What's XOM's volatility?",
        "How risky is JPM stock?",
        "How much has this stock swung in price recently?",
        "What's this stock's maximum drawdown?",
        "How unstable has this stock's price been?",
        "What's this ticker's 30-day volatility?",
        "How volatile has this stock been over the last 60 days?",
    ],
    "news_reason": [
        "Why is this stock down today?",
        "What news is driving this stock's move?",
        "What's behind this price change?",
        "What happened to cause this drop?",
        "Is there a news story explaining this stock's move?",
        "Why did the price change so much recently?",
        "What's the reason behind this stock's rally?",
        "What event caused this price swing?",
        "Why did this stock drop this week?",
        "Why did this stock climb this week?",
        "Why did XOM fall this week?",
        "Why did JPM drop this week?",
    ],
    "full_investigation": [
        "Analyze my whole portfolio for risk.",
        "Give me a complete risk breakdown.",
        "Do a thorough investigation of my portfolio.",
        "Take a deep look at my overall portfolio risk.",
        "Assess the risk across my entire portfolio.",
        "I want a full picture of my portfolio's risk exposure.",
        "Walk me through everything affecting my portfolio's risk.",
        "Give me the full risk story for my holdings.",
    ],
}
# The "None" bucket is gone: off-topic and prompt-injection refusal is now
# handled entirely by the guardrail (graph/guardrail.py), which runs before
# this router and short-circuits the graph. This router unconditionally
# picks the best-scoring of these 5 real intents -- it never has to decide
# "none of these," so a None-labeled calibration example wouldn't be usable
# here.

CLUSTER_SEED = 42
MAX_CLUSTERS_PER_INTENT = 3


def main() -> None:
    encoder = HuggingFaceEncoder(score_threshold=0.0)

    calibration_X, calibration_y = [], []
    for intent, utterances in CALIBRATION_UTTERANCES.items():
        for utterance in utterances:
            calibration_X.append(utterance)
            calibration_y.append(intent)

    route_names = list(ROUTE_UTTERANCES.keys())

    intent_example_pool = {
        intent: list(dict.fromkeys(ROUTE_UTTERANCES.get(intent, []) + CALIBRATION_UTTERANCES.get(intent, [])))
        for intent in route_names
    }

    intent_cluster_vectors = {}
    for intent, examples in intent_example_pool.items():
        vectors = np.array(encoder(examples))
        n_clusters = min(MAX_CLUSTERS_PER_INTENT, len(examples))
        kmeans = KMeans(n_clusters=n_clusters, random_state=CLUSTER_SEED, n_init="auto")
        kmeans.fit(vectors)
        intent_cluster_vectors[intent] = kmeans.cluster_centers_
        print(f"{intent:20s} {len(examples):2d} examples -> {n_clusters} cluster vectors")

    def score_all_routes(text: str) -> dict:
        vector = np.array(encoder([text])[0])
        vector = vector / np.linalg.norm(vector)
        scores = {}
        for intent, centers in intent_cluster_vectors.items():
            centers_norm = centers / np.linalg.norm(centers, axis=1, keepdims=True)
            similarities = centers_norm @ vector
            scores[intent] = float(np.max(similarities))
        return scores

    calibration_scores = [score_all_routes(text) for text in calibration_X]

    # Diagnostic only, not used by the actual routing decision: how often
    # does the highest-scoring intent match the calibration label? Refusal
    # itself lives entirely in the guardrail, which runs before this router.
    argmax_correct = sum(
        max(calibration_scores[i], key=calibration_scores[i].get) == calibration_y[i]
        for i in range(len(calibration_X))
    )
    print(f"Calibration accuracy (argmax, no thresholds): {argmax_correct / len(calibration_X):.1%}")

    cluster_comparisons_per_query = sum(len(v) for v in intent_cluster_vectors.values())
    raw_utterance_count = sum(len(u) for u in ROUTE_UTTERANCES.values())
    print(f"Comparisons per query: {cluster_comparisons_per_query} cluster centroids (vs {raw_utterance_count} raw utterances if scoring against every example directly)")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump({
            "cluster_vectors": {intent: vectors.tolist() for intent, vectors in intent_cluster_vectors.items()},
        }, f, indent=2)
    print(f"\nWrote calibration artifact to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
