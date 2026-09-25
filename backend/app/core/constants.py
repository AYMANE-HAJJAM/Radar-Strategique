"""Cross-layer shared constants (no Telegram / Flask imports)."""

PAGE_SIZE = 5
MAX_PAGE_INDEX = 10000
CALLBACK_DEBOUNCE_SECONDS = 1.0
CALLBACK_DEBOUNCE_CACHE_LIMIT = 1000
CALLBACK_DEBOUNCE_PRUNE_SECONDS = 10.0
# Candidate.metadata budget: PMMP detail + business_relevance + feedback + resolution.
# Must fit enriched Radar 1 keeps; in-place collector mutations previously bypassed the old 10k guard.
MAX_CANDIDATE_METADATA_CHARS = 65536
