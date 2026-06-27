"""Single source of truth for every analysis agent: its current prompt version,
the result schema it must emit, and its stage/dependencies.

- `prompt_version` is the LOGIC version. Bump it when you change an agent's
  prompt/rubric in `agents/<name>.md`. The orchestrator's worklist
  (`context_loader.list_pending`) treats a call as "pending" for an agent when
  its latest stored result is missing or was written at an older prompt_version,
  so bumping here triggers a clean recompute on the next run while prior versions
  are retained in `analysis_results` (compounding).
- `required_keys` is the strict-JSON gate enforced by `results_io.write_result`.
- `requires` lists agents that must have a current result for the same call
  before this one runs (dependency gate). Stage A `speaker_attribution` gates
  every Stage B agent.

Only the agents built in the current checkpoint are fully populated; later
stages are listed with `built: False` so the orchestrator and docs stay honest
about what exists.
"""
from __future__ import annotations

STAGE_A = "A"
STAGE_B = "B"
STAGE_C = "C"
STAGE_D = "D"

# Corpus-level results (Stage C/D) are stored against this sentinel call_id.
CORPUS_ID = "__corpus__"

AGENTS: dict[str, dict] = {
    # ---------------- Stage A — per call (BUILT) ----------------
    "speaker_attribution": {
        "stage": STAGE_A,
        "prompt_version": 1,
        "built": True,
        "requires": [],
        "required_keys": [
            "schema_version", "attribution_confidence", "participants",
            "turns", "n_rep_turns", "n_customer_turns",
        ],
    },
    "rep_talk_extraction": {
        "stage": STAGE_A,
        "prompt_version": 1,
        "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": [
            "schema_version", "rep_talk_share", "questions", "pitch_claims",
            "framing_moves", "n_questions",
        ],
    },
    "customer_voice_extraction": {
        "stage": STAGE_A,
        "prompt_version": 1,
        "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": [
            "schema_version", "customer_talk_share", "stated_pains", "goals",
            "objections_raised", "buying_signals", "sentiment_trend",
        ],
    },

    # ---------------- Stage B — per call (BUILT) ----------------
    "discovery_quality": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": ["schema_version", "score", "open_question_ratio",
                          "pains_uncovered", "bant", "strengths", "gaps",
                          "evidence_turns"]},
    "objection_handling": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": ["schema_version", "objections", "n_objections",
                          "overall_handling"]},
    "pricing_packaging_reaction": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": ["schema_version", "pricing_discussed", "tiers_mentioned",
                          "price_objection", "buyer_reaction", "bundling_signals",
                          "evidence_turns"]},
    "call_structure": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": ["schema_version", "phases", "followed_expected_sequence",
                          "time_to_first_discovery_q", "sequence_notes"]},
    "competitive_mention": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": ["schema_version", "competitors", "prior_vendor_failure_cited",
                          "n_mentions"]},
    "commitment_next_step": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": ["speaker_attribution"],
        "required_keys": ["schema_version", "next_step_secured", "next_step_type",
                          "who_owns", "strength"]},
    "icp_fit_tagger": {
        "stage": STAGE_B, "prompt_version": 1, "built": True,
        "requires": [],
        "required_keys": ["schema_version", "icp_tier", "persona_family",
                          "size_band", "fit_signals", "anti_fit_signals", "rationale"]},

    # ---------------- Stage C / D — corpus (BUILT) ----------------
    # Corpus-level results are stored under CORPUS_ID.
    "best_performing_call": {
        "stage": STAGE_C, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "ranked", "top_k", "limitation_block"]},
    "rubric_derivation": {
        "stage": STAGE_C, "prompt_version": 1, "built": True, "corpus": True,
        "requires": ["best_performing_call"],
        "required_keys": ["schema_version", "rubric", "anti_patterns",
                          "limitation_block"]},
    "pricing_packaging_insights": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "findings", "recommendations",
                          "limitation_block", "corpus_stats"]},
    "discovery_playbook": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "findings", "recommendations",
                          "limitation_block", "corpus_stats"]},
    "sales_call_sequence_script": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "findings", "recommendations",
                          "limitation_block", "corpus_stats"]},

    # ---------------- Recommended rep-facing scripts (Stage D, corpus) ----------------
    # Word-for-word talk tracks derived from the analytical deliverables. Schema is
    # script-shaped (sections of talk_track), not findings.
    "pricing_script": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "title", "sections", "limitation_block"]},
    "discovery_script": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "title", "sections", "limitation_block"]},
    "sequence_script": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "title", "sections", "limitation_block"]},

    # ---------------- Objection intelligence (Stage D, corpus) ----------------
    "objection_analysis": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "families", "findings",
                          "recommendations", "limitation_block", "corpus_stats"]},
    "objection_script": {
        "stage": STAGE_D, "prompt_version": 1, "built": True, "corpus": True,
        "requires": [],
        "required_keys": ["schema_version", "title", "sections", "limitation_block"]},
}


def prompt_version(agent: str) -> int:
    return AGENTS[agent]["prompt_version"]


def required_keys(agent: str) -> list[str]:
    return AGENTS[agent].get("required_keys", [])


def requires(agent: str) -> list[str]:
    return AGENTS[agent].get("requires", [])


def is_known(agent: str) -> bool:
    return agent in AGENTS
