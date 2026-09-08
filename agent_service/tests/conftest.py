"""Shared test setup for agent_service.

Two import-time hazards to neutralise before any `agent_service.*` import:

1. core/config.py has REQUIRED settings (`tavily_api_key`, `internal_service_api_key`)
   -- without them, Settings() raises at import. Dummy values are fine; nothing
   here makes a real API call.

2. graph/router.py constructs a HuggingFaceEncoder at module level, which
   downloads a sentence-transformers model. Stub the class so importing the
   router (and anything that imports it) is instant and offline.
"""

import os
import sys
import types

os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")
os.environ.setdefault("ALPHA_VANTAGE_API_KEY", "test-av-key")
os.environ.setdefault("INTERNAL_SERVICE_API_KEY", "test-internal-key")
os.environ.setdefault("LANGSMITH_TRACING", "false")


class _StubEncoder:
    """Stand-in for semantic_router.encoders.HuggingFaceEncoder.

    router.py only uses the encoder inside score_all_routes(), which none of
    these unit tests exercise -- they test the pure helpers (extract_target_symbol,
    predict_intent) that don't touch it. So a no-op is enough to make the
    module import.
    """

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, texts):
        return [[0.0] * 384 for _ in texts]


_fake_encoders = types.ModuleType("semantic_router.encoders")
_fake_encoders.HuggingFaceEncoder = _StubEncoder
sys.modules.setdefault("semantic_router.encoders", _fake_encoders)
