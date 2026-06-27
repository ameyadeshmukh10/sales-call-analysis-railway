# Agent: pricing-script

**Stage D · corpus → rep-facing script.** Produce a **word-for-word talk track** a
rep can say to explain EverWorker's pricing & packaging correctly — using the
CURRENT all-in tiers and directly replacing the dead per-worker model the corpus
shows reps still quote (the #1 finding). This is the fix to that problem, made
sayable.

> **GROUND TRUTH — read `docs/product_truth.md` first; it is authoritative** (flat
> all-inclusive pricing; models done-for-you/private, never "bring your own"; NEVER
> name an infrastructure/model provider). Also read `docs/analysis_rules.md`. Emit
> ONLY the schema below AND write
> the versioned deliverable. Carry the limitation block.

## Inputs
```bash
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"__corpus__","agent":"pricing_packaging_insights"}'
# winning-call phrasing to borrow (positive-reaction calls):
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"pricing_packaging_reaction"}'
python3 -W ignore -m skills.store_io.results_io read '{"call_id":"<CALL_ID>","agent":"rep_talk_extraction"}'
```

## The truth the script must encode (from docs/product_truth.md — authoritative)
One predictable, all-in **fixed monthly cost per tier — buy EverWorker, procure
nothing else**: **Starter $3.5k / Scale $5.5k (most popular) / Advanced $7k**, 3-month
opt-out, live in ~5 weeks, forward-deployed GTM AI engineer included. **Included in
the flat rate at every tier:** LLM consumption (no token bill) · **model-endpoint
procurement done-for-you by EverWorker (private, no-train/no-retain, best-in-class
OpenAI+Anthropic mix — the customer does NOT bring/use their own endpoints)** · agent
architecture scoped to the customer's GTM/signal plays · fully-managed email +
LinkedIn infrastructure, sending capacity, deliverability, and **our built-in
sequencers** · CRM integration. **NEVER name a provider** (no Email Bison / HeyReach /
ScaledMail / Prospeo / PDL) — say "our managed infrastructure" / "our built-in
sequencer." Tiers differ by signal/enrichment volume + advanced capabilities.
**There is NO per-worker price, NO $20k–$60k anchor, NO 4-phase add-on sequence,
and Email Bison/HeyReach/data/LLM are NEVER named or priced separately.**

## Method
Write a talk track with short bracketed stage directions (`[if the buyer asks what's
included]`, `[if they anchor on a competitor's credit pricing]`). Cover: the
one-line frame ("one fixed monthly cost, everything included, nothing to procure"),
the three tiers and what separates them (volume + advanced signals, not
infrastructure), the bundled-everything list said plainly, the cost-of-an-SDR-hire
value anchor, and rebuttals to the objections the corpus surfaces (price sticker
shock, "is the data/LLM extra?", procurement relief). Where a winning call used
good language, ground a line in it (cite call_id). **Never** reproduce the dead
per-worker numbers except in an explicit "do NOT say this" coach note.

## Output schema (emit ONLY this JSON), then write the deliverable
```json
{
  "schema_version": "1.0",
  "title": "Pricing & Packaging — recommended talk track",
  "sections": [
    {"heading": "The one-line frame", "talk_track": "“...verbatim...”",
     "grounded_in_calls": ["<id>"], "notes": "[stage direction or coach note]"}
  ],
  "do_not_say": ["per-worker $25k / $60k bundle", "$20k phase 1", "Bison is $599 extra"],
  "limitation_block": "<verbatim from analysis_rules.md>"
}
```

## Persist + version
```bash
python3 -W ignore -m skills.store_io.results_io write < /tmp/pscript.json   # {"call_id":"__corpus__","agent":"pricing_script","result":{...}}
python3 -W ignore -m skills.corpus.outputs_versioner write < /tmp/pscript_out.json   # {"deliverable":"pricing_script","md":"<full readable talk track>","data":{...same result...}}
python3 -W ignore -m skills.corpus.outputs_differ '{"deliverable":"pricing_script","to_v":<N>}'
```
The `md` is the full, readable, copy-pasteable talk track (assemble the sections
with their headings + stage directions). Prepend the differ changelog to `vN.md`.
