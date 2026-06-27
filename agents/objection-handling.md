# Agent: objection-handling

**Stage B · per call.** Catalog every customer objection/concern, classify it by
family (quality / risk / fit / price), capture how the rep responded, and judge
whether the response resolved, deflected, or lost ground.

> Requires `speaker_attribution`. Read `docs/analysis_rules.md` and the objection
> taxonomy in `docs/interpretation.md`. Cite by turn index. Emit ONLY the schema.

## Inputs
```bash
python -m skills.store_io.context_loader context '{"call_id":"<CALL_ID>"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"speaker_attribution"}'
python -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"customer_voice_extraction"}'
```

## Method
For each objection the customer raises:
- `family ∈ {quality, risk, fit, price, other}` (see `docs/interpretation.md` for
  seed examples — quality = "obviously AI / domain reputation / we tried a vendor";
  risk = compliance / "replaces my SDRs" / not-ready; fit = messy CRM / too small;
  price = sticker shock / ROI doubt / paying for things separately).
- `label`: a short canonical name for the objection.
- `raised_turn`: turn index where the customer raised it.
- `handled`: did the rep address it at all?
- `technique ∈ {acknowledge, reframe, evidence, deflect, ignore}`.
- `handling_quality` 0–3 (0 = ignored/made worse, 3 = cleanly resolved with the
  buyer satisfied).
- `response_summary`: one line on how the rep responded.

`overall_handling` 0–100 across all objections on the call. If no objections,
`objections: []`, `n_objections: 0`, `overall_handling: null`.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "objections": [
    {"family": "price", "label": "monthly fee sticker shock", "raised_turn": 88,
     "handled": true, "technique": "reframe", "handling_quality": 2,
     "response_summary": "reframed against cost of an SDR hire + bundled infra"}
  ],
  "n_objections": 1,
  "overall_handling": 70,
  "notes": "optional"
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/oh.json   # {"call_id","agent":"objection_handling","result":{...}}
```
