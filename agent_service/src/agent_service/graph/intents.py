"""Intent definitions shared by graph/router.py (query-time scoring) and
scripts/calibrate_router.py (build-time centroid fitting) -- kept separate
from router.py so the calibration script doesn't have to import the half of
router.py that loads the (not-yet-existing, on a first run) calibration file.
"""

ROUTE_UTTERANCES = {
    "holdings": [
        "What stocks do I currently own?",
        "Can you list everything in my portfolio?",
        "What positions am I holding right now?",
        "Give me an overview of what I own.",
        "Which companies am I invested in?",
    ],
    "concentration": [
        "How concentrated is my portfolio?",
        "Which holding dominates my portfolio?",
        "Am I overexposed to one company?",
        "Is too much of my money in a single stock?",
        "What is my biggest holding by weight?",
        "Which position of mine is the largest?",
        "What is my top holding by size?",
    ],
    "symbol_risk": [
        "How volatile has this stock been lately?",
        "What is the risk level of this particular holding?",
        "How much has this stock dropped from its peak?",
        "Tell me the volatility number for this ticker.",
        "What is the historical price swing for this stock?",
        "What's AMZN's volatility?",
        "How volatile is META right now?",
    ],
    "news_reason": [
        "What caused this stock's price movement?",
        "Explain the recent news behind this company's stock swing.",
        "What is the story behind why this stock moved?",
        "What happened in the news that affected this stock?",
        "Why did this company's share price change recently?",
        "Why did this stock fall this week?",
        "Why did this stock rise this week?",
        "Why did AMZN fall this week?",
        "Why did META drop this week?",
    ],
    "full_investigation": [
        "Can you do a full risk analysis of my entire portfolio?",
        "I want a comprehensive review of my portfolio's risk.",
        "Please investigate everything going on with my investments.",
        "Give me a deep dive into my portfolio's overall risk profile.",
        "Run a complete risk assessment across all my holdings.",
    ],
}

INTENT_ROUTES = {
    "holdings": ["portfolio", "answer"],
    "concentration": ["portfolio", "market", "risk", "answer"],
    "symbol_risk": ["market", "risk", "answer"],
    "news_reason": ["market", "news", "report"],
    "full_investigation": ["portfolio", "market", "risk", "news", "report"],
}
