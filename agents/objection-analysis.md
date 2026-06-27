# Agent: objection-analysis

**Stage D · corpus → deliverable.** Build the objection intelligence: cluster the
corpus's catalogued objections into a **concise named taxonomy** (top ~5–7
sub-types per family), and for each sub-type analyze **how it's handled, how well,
and whether it tends to stall or advance deals**. This powers the Objections
drill-down page.

> **Ground truth: `docs/product_truth.md`** — when writing `recommended_handling`,
> position only what is true there (flat all-in pricing; models done-for-you/private,
> never "bring your own"; never name infra/model providers). Read
> `docs/analysis_rules.md`. Emit ONLY the schema below AND write the versioned
> deliverable. Cite calls. Carry the limitation block.

## Inputs
```bash
python3 -W ignore -m skills.corpus.objection_catalog   # regenerate the catalog
```
Then **Read** `data/results/objection_catalog.json`. It contains, per family:
`n`, `pct`, `resolved_rate`, `technique_dist`, `handling_quality_dist`, and the full
`instances` list — each with `label`, `verbatim` (buyer's words), `technique`,
`handling_quality` (0–3), `handled`, `response_summary`, `call_id`, `company`,
`turn`, **`deal_status`** (won/lost/open/no_deal) and **`composite_score`**. Drill
specific calls if needed via `results_io read '{"call_id":"<id>","agent":"objection_handling"}'`.

## Method
Within each family, group the `instances` by the semantic theme of `label`+`verbatim`
into the **top 5–7 recurring sub-types** (roll genuine one-offs into an "Other" bucket).
For each sub-type compute from its members:
- `n`, `pct_of_family`; 1–3 representative **verbatim** quotes (call_id+turn, the
  buyer's actual words); `example_calls`.
- `techniques_used` (count by technique); `resolved_rate` (members handled & hq≥2).
- `best_handled` (highest-hq member: call_id, turn, why it worked, handling_quality)
  and `worst_handled` (ignore/deflect or hq≤1: what went wrong).
- **`outcome_signal`** — compare the `deal_status`/`composite_score` of calls where
  this sub-type appeared against the corpus: does it lean **stall** or **advance**?
  State it softly with the caveat (2 won / 22 lost / 42 open, 2 reps — directional).
- `recommended_handling` — 1–2 sentences on the best way to handle it (drawn from
  the best_handled examples).

Then a corpus-level `findings[]` (the biggest sub-types / patterns, each with
`support{n_calls,pct,example_calls}`) and `recommendations[]`.

## Output schema (emit ONLY this JSON), then write the deliverable
```json
{
  "schema_version": "1.0",
  "families": [
    {"family": "fit", "n": 125, "resolved_rate": 64.0, "subtypes": [
      {"name": "Build-it-ourselves", "description": "...", "n": 34, "pct_of_family": 27.2,
       "quotes": [{"call_id": "<id>", "turn": 353, "text": "why can I not build this myself"}],
       "example_calls": ["<id>"], "techniques_used": {"reframe": 20, "acknowledge": 10},
       "resolved_rate": 58.0,
       "best_handled": {"call_id": "<id>", "turn": 353, "why": "...", "handling_quality": 3},
       "worst_handled": {"call_id": "<id>", "turn": 120, "why": "...", "handling_quality": 1},
       "outcome_signal": "leans stall — appeared mostly on open/lost calls (caveat: small sample)",
       "recommended_handling": "Reframe on key-person risk + maintenance cost ..."}
    ]}
  ],
  "findings": [
    {"claim": "Build-vs-buy is the single largest objection sub-type (27% of fit)",
     "support": {"n_calls": 30, "pct": 27.2, "example_calls": ["<id>"]}}
  ],
  "recommendations": ["Lead fit objections with the key-person-risk reframe ..."],
  "limitation_block": "<verbatim from analysis_rules.md>",
  "corpus_stats": {"n_calls": 72, "n_objections": 282}
}
```

## Persist + version the deliverable
```bash
python3 -W ignore -m skills.store_io.results_io write < /tmp/objan.json   # {"call_id":"__corpus__","agent":"objection_analysis","result":{...}}
python3 -W ignore -m skills.corpus.outputs_versioner write < /tmp/objan_out.json   # {"deliverable":"objection_analysis","md":"<markdown: family -> sub-type cards>","data":{...same...}}
python3 -W ignore -m skills.corpus.outputs_differ '{"deliverable":"objection_analysis","to_v":<N>}'
```
The `md` renders each family heading → sub-type cards (name, count/pct, a verbatim
quote, resolved-rate, best/worst, outcome lean, recommended handling). Prepend the
differ changelog to `vN.md`.
