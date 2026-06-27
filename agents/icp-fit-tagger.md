# Agent: icp-fit-tagger

**Stage B · per call.** Tag the account against ICP using firmographics + the
persona on the call + signals heard. Lets the corpus agents segment cleanly (e.g.
"pricing friction concentrates in sub-50-employee accounts").

> Read `docs/analysis_rules.md` and the persona map in `docs/interpretation.md`.
> Emit ONLY the schema below. (No Stage-A dependency — uses firmographics + light
> transcript signal.)

## Inputs
```bash
python -m skills.store_io.context_loader context '{"call_id":"<CALL_ID>"}'
```
Use `contacts` (job_title → persona), `companies` (industry, num_employees,
annual_revenue, country), and the transcript for fit/anti-fit signals.

## Method
- `persona_family`: normalize the primary contact's title to
  {CRO, VP_Sales, RevOps, DemandGen, BizDev, Founder_CEO, Other} per the map.
- `size_band`: from num_employees → {micro <20, smb 20–199, mid 200–999,
  enterprise 1000+, unknown}.
- `industry`: the company industry (or null).
- `fit_signals`: things that make them a good fit for an outbound-AI-SDR (large
  TAM they can't cover, existing outbound motion, growth/hiring pressure, signal
  richness).
- `anti_fit_signals`: poor-fit cues (tiny TAM, no outbound motion, "not ready",
  unwilling to change process, wrong buyer in the room).
- `icp_tier ∈ {1, 2, "deprioritize"}` with a one-line `rationale`. Tier 1 = strong
  fit across firmographics + need + buyer; deprioritize = clear anti-fit.

## Output schema (emit ONLY this JSON)
```json
{
  "schema_version": "1.0",
  "icp_tier": 1,
  "persona_family": "CRO",
  "industry": "COMPUTER_SOFTWARE",
  "size_band": "mid",
  "fit_signals": ["more in-market accounts than the team can cover"],
  "anti_fit_signals": [],
  "rationale": "CRO buyer, mid-market software, clear capacity gap — strong fit"
}
```

## Persist
```bash
python -m skills.store_io.results_io write < /tmp/icp.json   # {"call_id","agent":"icp_fit_tagger","result":{...}}
```
