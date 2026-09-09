Hybrid blending is monotonic: ML can raise but never lower a heuristic score (safety property).
Explanations run through a timed LLM provider gateway (OpenRouter 100 s -> Groq 60 s -> local rule-based template; cache TTL 3600 s, max 256 entries) so analysis latency is bounded even when a provider degrades.
The frontend uses a strict black/white/red monochrome theme: page #050505, panels #0a0a0a, cards #101010, red-600 accent; severity ramp #e4e4e7 / #71717a / #f87171 / #dc2626 / #ef4444 (centralised in frontend/src/theme.ts).
