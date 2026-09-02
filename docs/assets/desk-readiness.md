# Derivatives desk-readiness brief

Use this before a model, data feed, or risk report moves beyond research.

- Name the model owner and independent reviewer.
- Record instrument scope, assumptions, conventions, and known gaps.
- Pin the code version and input market-data timestamp.
- Reconcile benchmark prices against an independent implementation.
- Test limits, no-arbitrage relationships, round trips, and failure modes.
- Document units for rates, volatility, Greeks, notionals, and PnL.
- Define stale-data thresholds and what happens when a venue is unavailable.
- Keep discounting and forecasting choices explicit.
- Store a reproducible input portfolio with the output report.
- Set approval, monitoring, incident, and rollback responsibilities.

Argentum is for research, teaching, and desk prototyping. This checklist is not
a substitute for a firm's model-risk, market-data, security, or change-control
framework.
