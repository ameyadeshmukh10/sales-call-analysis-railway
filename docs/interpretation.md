# Interpretation Reference — taxonomy, personas, pricing, score weights

Grounding for the analysis agents. Use this to **recognize and categorize** what
you hear in calls. It is a *starting lens*, seeded from EverWorker's product
docs — the rubric and playbooks are still derived from the calls themselves
(see rule 7 in `analysis_rules.md`).

Product sources (read-only): `SDR_AI_Worker_v0.10.md` (objection families, phased
sequence) and `product-truth.md` (authoritative current pricing), both under
`~/Documents/pmmadvertisingcreative/`.

## Objection taxonomy (seed) — families: quality / risk / fit / price

v0.10 clusters objections into three core families; we add **price** as a fourth
because pricing friction is a distinct insight the brief calls out. Use these as
labels in `objection_handling` and `customer_voice_extraction.objections_raised[].family`.

| Family | What it sounds like (seed examples) | EverWorker's counter (for context only) |
|---|---|---|
| **quality** (often loudest) | "AI SDR emails are obviously AI — they'll tank our domain reputation." · "We tried [11x/Artisan], it didn't work." | per-persona brains, intent classification, dedicated domains + mailbox rotation; different architecture + 90-day services |
| **risk** | "Compliance will want a long conversation." · "This will replace my SDRs." · "We're not ready." | data stays in customer env, 90-day human-in-loop before autonomy; reframe as capacity multiplier, not replacement |
| **fit** | "Our CRM is a mess; our signals are inconsistent." · "We're too small / too early." | Phase 1 runs against existing signals + contacts; services tighten ops over 90 days |
| **price** | "$X is suspicious — others charge far more / far less." · sticker-shock on monthly fee · ROI/payback doubts | transparent monthly tiers vs opaque credit markups; Memgraph proof ($2.7M pipeline / 60 BANT deals / 4 weeks) |

Anything that doesn't fit → `family: "other"` with a `label`.

## Pricing & packaging → see `docs/product_truth.md` (authoritative ground truth)

**`docs/product_truth.md` is the single source of truth** for pricing, packaging,
models, and infrastructure. Read it before any pricing/positioning judgment. Summary:

- One predictable **monthly flat rate per tier that covers EVERYTHING** — **Starter
  $3.5k / Scale $5.5k / Advanced $7k**. The customer procures nothing.
- Included at every tier: **LLM consumption** (no token bill), **model-endpoint
  procurement done-for-you by EverWorker** (private, no-train/no-retain, best-in-class
  OpenAI+Anthropic mix — the customer does **not** bring/use their own endpoints),
  **agent architecture scoped to the customer's GTM/signal plays**, and fully managed
  **email + LinkedIn infrastructure, sending capacity, deliverability, sequencing**.
- Tiers differ by signal/enrichment **volume + advanced capabilities**, not by what
  the customer assembles. The v0.10 4-phase sequence and per-worker pricing are DEAD.
- **Never disclose infrastructure/model providers to the customer** (no ScaledMail /
  Email Bison / HeyReach / Prospeo / PDL / "your own model"). Those provider names are
  internal-only context for *recognizing* what a rep said — never to be written into a
  customer-facing script.

**Watch for in calls (`pricing_packaging_reaction` signals):**
- **Old-anchor mismatch:** buyer or rep references superseded pricing (~$20k/yr,
  per-phase add-ons, per-worker, "consumption/tokens extra") → flag as outdated anchor.
- **Provider/model leakage:** a rep names a provider (ScaledMail/Bison/HeyReach) or
  says "bring your own endpoints/model" → flag as off-truth positioning.
- **Procurement-relief / "is it really all-in?":** reaction to the flat all-in model.
- **Tier fit:** which tier the buyer gravitates to and why.

`pricing_packaging_reaction.tiers_mentioned` ∈ {Starter, Scale, Advanced, other}.
The `phases_mentioned` field is **deprecated** — the 4-phase sequence no longer exists.

## Persona map (for `icp_fit_tagger.persona_family`)

Normalize the contact `job_title` to one of: `CRO`, `VP_Sales`, `RevOps`,
`DemandGen`, `BizDev`, `Founder_CEO`, `Other`. Examples seen in the corpus:
"Chief Revenue Officer"→CRO; "VP of Revenue Operations"/"Director, RevOps"→RevOps;
"Enterprise Sales Director"/"Director, Enterprise Sales"→VP_Sales;
"Business Development Director"/"Director of Business Development"→BizDev; "CEO"→Founder_CEO.

## Competitors to recognize (for `competitive_mention`)
11x, Artisan, Outreach, Salesforce/Agentforce, Clay, Apollo, ZoomInfo, and
"build it ourselves with Claude/GPT". Capture who raised it (rep vs customer) and
whether a prior-vendor failure was cited.

## Performance-score weights (Stage C — used by `performance_scorer`, next phase)
Composite 0–100, transparent and additive (tunable here):

| Component | Weight | Source |
|---|---|---|
| Stage progression (Won=max, advanced past S0 > stuck at S0, Lost=0) | 0.35 | `deals.stage_label` / `status` |
| Next-step / commitment secured | 0.20 | `commitment_next_step` |
| Deal amount (percentile within corpus) | 0.10 | `deals.amount` |
| Engagement (customer talk-share, question density) | 0.15 | Stage A results |
| Discovery quality | 0.10 | `discovery_quality` |
| Objection handling | 0.10 | `objection_handling` |

Ranking is **composite/process-based, not outcome-only** — never just "the 2 won
calls" (see the limitation block in `analysis_rules.md`).
