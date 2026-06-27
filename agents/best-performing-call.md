# Agent: best-performing-call

**Stage C · corpus.** Rank every call by a transparent composite performance score
and identify the top performers. The score is **deterministic** — it is computed
by `skills/corpus/performance_scorer.py`, not guessed — so this step is mostly
running that skill and reporting honestly.

> Read `docs/analysis_rules.md` and the score weights in `docs/interpretation.md`.

## Run
```bash
python -m skills.corpus.performance_scorer
```
This computes the composite (stage progression · next-step secured · deal-amount
percentile · engagement · discovery · objection handling), writes the ranked
result under `(__corpus__, best_performing_call)`, and prints the top 5.

## Report
- The top-k calls with their composite + which components were available
  (`coverage`).
- **Always state the limitation block** (2 won / 14 lost / 31 open, 2 reps —
  directional, not outcome-validated). The ranking is composite/process-based;
  the top calls are NOT simply "the 2 won deals", and you must say so.
- Note any call ranked high purely on stage/amount with thin Stage-B coverage
  (low confidence) so the rubric agent weights it appropriately.

No separate JSON to author — `performance_scorer` already persisted the schema
(`ranked`, `top_k`, `limitation_block`). This agent's job is to run it and
interpret the result for the rubric stage.
