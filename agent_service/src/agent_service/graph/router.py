"""Semantic intent router: embeds the question, scores it against each
intent's cluster centroids, always picks the highest-scoring intent (plain
argmax, no threshold). Ported from notebook cells 30/32/34/36 (current,
fixed version).

Refusal (unsafe or off-topic) is NOT this module's job -- it's handled
entirely by graph/guardrail.py, which runs before this router and
short-circuits the graph, so nothing off-topic ever reaches score_all_routes.
See CLAUDE.md's resolved-bug note for why the router no longer has its own
threshold-based refusal path.

The KMeans centroids are NOT computed here -- they're a build-time artifact
(scripts/calibrate_router.py) loaded from the committed
calibration/router_calibration.json, per CLAUDE.md's routing methodology.
"""

import json
import re
from pathlib import Path
from typing import Optional

import numpy as np
import truststore

truststore.inject_into_ssl()

from semantic_router.encoders import HuggingFaceEncoder

from agent_service.graph.intents import ROUTE_UTTERANCES, INTENT_ROUTES

CALIBRATION_PATH = Path(__file__).resolve().parent.parent / "calibration" / "router_calibration.json"

encoder = HuggingFaceEncoder(score_threshold=0.0)

with open(CALIBRATION_PATH) as f:
    _calibration = json.load(f)

INTENT_CLUSTER_VECTORS: dict[str, np.ndarray] = {
    intent: np.array(vectors) for intent, vectors in _calibration["cluster_vectors"].items()
}


def score_all_routes(text: str) -> dict:
    """Query-time scoring: embed the question once, then compare it against
    each intent's stored cluster centroids. Max similarity across a route's
    centroids is used, not mean, so a question only needs to be close to ONE
    sub-meaning of an intent, not every sub-meaning blended together."""
    vector = np.array(encoder([text])[0])
    vector = vector / np.linalg.norm(vector)
    scores = {}
    for intent, centers in INTENT_CLUSTER_VECTORS.items():
        centers_norm = centers / np.linalg.norm(centers, axis=1, keepdims=True)
        similarities = centers_norm @ vector
        scores[intent] = float(np.max(similarities))
    return scores


def predict_intent(scores: dict) -> str:
    """Always returns the single highest-scoring intent -- refusal is the
    guardrail's job, not this router's (see module docstring)."""
    return max(scores, key=scores.get)


_COMMON_WORDS = {
    "WHAT", "WHY", "HOW", "IS", "MY", "THE", "A", "FOR", "OF", "DID", "WEEK",
    "RECENTLY", "AM", "I", "TO", "AND", "S", "THIS",
}


def extract_target_symbol(question: str, known_symbols: list[str]) -> Optional[str]:
    """Matches against the requesting user's actual portfolio symbols first
    (the "known universe" -- see market_node's not_found handling), then
    falls back to any distinctive all-caps token for out-of-universe
    reliability cases (ZZZZ, FAKECO, BTCUSD, XCORP)."""
    tokens = re.findall(r"[A-Za-z]+", question)
    upper_tokens = [t.upper() for t in tokens]

    for symbol in known_symbols:
        if symbol in upper_tokens:
            return symbol

    for token in tokens:
        if token.isupper() and len(token) >= 3 and token.upper() not in _COMMON_WORDS:
            return token

    return None
