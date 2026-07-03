"""
VERITAS Kernel — Protocol for convergence toward reality.

Principles:
  1. Separation of concerns: LLM observes (facts), rules decide (policy).
  2. Deterministic routing: no policy flows from the LLM.
  3. Self-application: feedback loops measure rule correctness.
  4. Local-first: designed for offline heuristic analysis + future API integration.

Meta-rule: VERITAS applies to itself. All rules are provisional models.
"""

import os
import json
import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import datetime

# ======================================================================
# CONFIG + CORE CLASSES
# ======================================================================

CONFIG = {
    "min_sources_high_stakes": 2,
    "analysis_confidence_threshold": 0.4,  # Below this, extra scrutiny
    "uncertainty_threshold_approfondi": 0.5,  # effective uncertainty → approfondi
    "uncertainty_threshold_direct": 0.3,  # Below this, direct mode OK
    "causal_question_boost": 0.15,  # Add to uncertainty if causal_question + controversy
}


@dataclass
class ObservedFeatures:
    """Pure observations — no policy decisions here.
    Produced by heuristic analysis or LLM (facts only)."""
    truth_apt: bool  # Can this claim have a truth value? (vs. pure opinion/poetry)
    contains_hypothesis: bool = False
    contains_causal_claim: bool = False  # Affirmation: "X causes Y"
    contains_causal_question: bool = False  # Question: "Why does X?"
    contains_quantitative_claim: bool = False
    is_controversial_topic: bool = False
    explicit_depth_request: bool = False
    is_sensitive_topic: bool = False  # Health/security detected
    mentions_current_fact: bool = False  # Dated info (president, CEO, today...)
    analysis_confidence: float = 0.75  # Confidence in *this analysis*
    uncertainty_level: float = 0.5  # Epistemic uncertainty of *the topic*


@dataclass
class Assessment:
    """Deterministic policy decisions computed from ObservedFeatures.
    This is where policy lives — never in the LLM."""
    verification: str  # "none" | "optional" | "required"
    external_sources: str  # "none" | "recommended" | "required"
    sensitivity: str  # "low" | "medium" | "high"
    stakes_level: str  # "low" | "medium" | "high"
    stakes_reason: List[str] = field(default_factory=list)


def assess(f: ObservedFeatures) -> Assessment:
    """Deterministic rule engine. No policy value comes directly from LLM."""
    reasons = []

    # Sensitivity → Stakes hierarchy
    if f.is_sensitive_topic:
        stakes = "high"
        reasons.append("sujet_sensible_sante_securite")
    elif f.is_controversial_topic or f.explicit_depth_request:
        stakes = "high"
        reasons.append("controverse_ou_approfondissement_demande")
    elif f.contains_causal_claim or f.contains_quantitative_claim or f.mentions_current_fact:
        stakes = "medium"
        reasons.append("affirmation_causale_chiffree_ou_fait_date")
    else:
        stakes = "low"

    # Verification: required if sensitive, high-quantitative claim, dated, or low confidence
    verification = "required" if (
        f.is_sensitive_topic
        or f.contains_quantitative_claim
        or f.mentions_current_fact
        or f.analysis_confidence < CONFIG["analysis_confidence_threshold"]
    ) else "optional"

    # External sources: required if sensitive/controversial/dated; recommended if quantitative
    external_sources = "required" if (
        f.is_sensitive_topic or f.is_controversial_topic or f.mentions_current_fact
    ) else ("recommended" if f.contains_quantitative_claim else "none")

    sensitivity = (
        "high" if f.is_sensitive_topic
        else ("medium" if f.is_controversial_topic else "low")
    )

    return Assessment(verification, external_sources, sensitivity, stakes, reasons)


@dataclass
class DecisionContext:
    """Features + Assessment, consumed by kernel.
    Preserves all information needed for routing and logging."""
    truth_apt: bool
    verification: str
    external_sources: str
    sensitivity: str
    stakes_level: str
    stakes_reason: List[str] = field(default_factory=list)
    contains_hypothesis: bool = False
    contains_causal_claim: bool = False
    contains_causal_question: bool = False  # NEW: track but don't conflate with claim
    contains_quantitative_claim: bool = False
    analysis_confidence: float = 0.75
    uncertainty_level: float = 0.5
    is_controversial: bool = False
    explicit_depth_request: bool = False
    is_sensitive_risk: bool = False

    @classmethod
    def from_features(cls, f: ObservedFeatures) -> "DecisionContext":
        a = assess(f)
        return cls(
            truth_apt=f.truth_apt,
            verification=a.verification,
            external_sources=a.external_sources,
            sensitivity=a.sensitivity,
            stakes_level=a.stakes_level,
            stakes_reason=a.stakes_reason,
            contains_hypothesis=f.contains_hypothesis,
            contains_causal_claim=f.contains_causal_claim,
            contains_causal_question=f.contains_causal_question,
            contains_quantitative_claim=f.contains_quantitative_claim,
            analysis_confidence=f.analysis_confidence,
            uncertainty_level=f.uncertainty_level,
            is_controversial=f.is_controversial_topic,
            explicit_depth_request=f.explicit_depth_request,
            is_sensitive_risk=f.is_sensitive_topic,
        )


class ConstraintClass(Enum):
    """Constraint hierarchy: SECURITE > EPISTEMIQUE > OPTIMISATION"""
    SECURITE = 3
    EPISTEMIQUE = 2
    OPTIMISATION = 1


@dataclass
class Constraint:
    name: str
    cls: ConstraintClass
    detail: str


# ======================================================================
# MODE ROUTING: Direct / Standard / Approfondi
# ======================================================================


def compute_effective_uncertainty(ctx: DecisionContext) -> float:
    """Combine topic uncertainty with analyzer confidence.
    High topic uncertainty + low analyzer confidence → boost rigor.
    
    Formula: uncertainty * (1 - confidence) + base_uncertainty
    This gives epistemic discomfort: how much we should scrutinize."""
    base = ctx.uncertainty_level
    confidence_penalty = (1.0 - ctx.analysis_confidence) * 0.5
    
    # Causal question in controversial context adds risk
    if ctx.contains_causal_question and ctx.is_controversial:
        confidence_penalty += CONFIG["causal_question_boost"]
    
    return min(1.0, base + confidence_penalty)


def determine_mode(ctx: DecisionContext) -> str:
    """Route to Direct / Standard / Approfondi based on context.
    
    APPROFONDI (deep analysis):
      - Anything high-stakes (sensitivity or stakes_level)
      - Controversial or explicit depth request
      - High effective uncertainty
      - Contains causal question + controversial (embedded premise risk)
    
    DIRECT (minimal overhead):
      - Low stakes, no hypotheses/claims, low uncertainty, fast confidence
    
    STANDARD (balanced):
      - Everything else
    """
    risk = ctx.is_sensitive_risk or ctx.sensitivity == "high"
    effective_uncertainty = compute_effective_uncertainty(ctx)
    
    # FIX #1: High stakes ALWAYS → approfondi (not just with causal/quantitative)
    if ctx.stakes_level == "high":
        return "approfondi"
    
    if (
        ctx.is_controversial
        or risk
        or ctx.explicit_depth_request
        or effective_uncertainty >= CONFIG["uncertainty_threshold_approfondi"]
        or (ctx.contains_causal_question and ctx.is_controversial)
    ):
        return "approfondi"

    # DIRECT: low overhead for routine, high-confidence facts
    if (
        ctx.stakes_level == "low"
        and not ctx.contains_hypothesis
        and not ctx.contains_causal_claim
        and not ctx.contains_causal_question
        and not ctx.contains_quantitative_claim
        and ctx.verification != "required"
        and effective_uncertainty <= CONFIG["uncertainty_threshold_direct"]
        and ctx.analysis_confidence > 0.7
    ):
        return "direct"

    return "standard"


def kernel_decide(ctx: DecisionContext) -> List[Constraint]:
    """Apply routing rules to generate constraints.
    Constraints encode epistemic rigor levels."""
    constraints = []
    mode = determine_mode(ctx)

    # SECURITE layer: verification is non-negotiable
    if (
        ctx.truth_apt and ctx.verification == "required"
        or ctx.is_sensitive_risk
        or ctx.analysis_confidence < CONFIG["analysis_confidence_threshold"]
    ):
        constraints.append(
            Constraint(
                "verification_obligatoire",
                ConstraintClass.SECURITE,
                "Vérification obligatoire (fait sensible, requis, ou confiance d'analyse faible)"
            )
        )

    # EPISTEMIQUE layer: mode-specific rigor
    if mode == "standard":
        constraints.append(
            Constraint(
                "mode_standard",
                ConstraintClass.EPISTEMIQUE,
                "Séparer su/interprété/inconnu ; envisager 1 alternative ; vérifier si besoin ; confiance explicite"
            )
        )
        if ctx.external_sources in ("recommended", "required") or ctx.contains_quantitative_claim:
            constraints.append(
                Constraint(
                    "sources_min",
                    ConstraintClass.EPISTEMIQUE,
                    "≥1 source pour affirmation datée/chiffrée"
                )
            )

    if mode == "approfondi":
        constraints.append(
            Constraint(
                "mode_d_obligatoire",
                ConstraintClass.EPISTEMIQUE,
                "≥2 modèles explicatifs concurrents, test discriminant, conclusion provisoire"
            )
        )
        constraints.append(
            Constraint(
                "sources_min",
                ConstraintClass.EPISTEMIQUE,
                f"≥{CONFIG['min_sources_high_stakes']} sources indépendantes"
            )
        )

    # FIX #3: consensus_non_preuve only when multiple models consulted
    if mode != "direct":
        constraints.append(
            Constraint(
                "consensus_non_preuve",
                ConstraintClass.EPISTEMIQUE,
                "Convergence inter-modèles ≠ preuve : exige ≥1 source externe indépendante"
            )
        )

    constraints.append(
        Constraint(
            "tracabilite",
            ConstraintClass.EPISTEMIQUE,
            "Traçabilité obligatoire"
        )
    )

    # FIX #4: hypothesis checklist only in approfondi (not standard)
    if ctx.contains_hypothesis and ctx.truth_apt and mode == "approfondi":
        constraints.append(
            Constraint(
                "checklist_hypothese",
                ConstraintClass.EPISTEMIQUE,
                "Art. 9 : checklist 6 étapes (Annexe) avant verdict sur l'hypothèse"
            )
        )

    # OPTIMISATION layer: cost minimization in direct mode
    if mode == "direct":
        constraints.append(
            Constraint(
                "cout_minimal",
                ConstraintClass.OPTIMISATION,
                "Tâche mécanique/faible enjeu : 1 seul modèle, pas de recherche"
            )
        )

    return constraints


def resolve_conflicts(constraints: List[Constraint]) -> List[Constraint]:
    """Resolve conflicts: SECURITE > EPISTEMIQUE > OPTIMISATION.
    If security constraint exists, remove all optimization constraints."""
    names = {c.name for c in constraints}
    if "verification_obligatoire" in names:
        constraints = [c for c in constraints if c.cls != ConstraintClass.OPTIMISATION]
    return sorted(constraints, key=lambda c: c.cls.value, reverse=True)


def build_pipeline(ctx: DecisionContext, constraints: List[Constraint]) -> dict:
    """Build execution pipeline from constraints and context."""
    names = {c.name for c in constraints}
    mode = determine_mode(ctx)

    # Model count by mode
    n_models = {"approfondi": 3, "standard": 2, "direct": 1}[mode]

    # Minimum sources logic
    min_sources = 0
    if "mode_d_obligatoire" in names:
        min_sources = CONFIG["min_sources_high_stakes"]
    elif "sources_min" in names:
        min_sources = 1

    # FIX #3: if multiple models AND no sources yet required, require 1
    if "consensus_non_preuve" in names and min_sources == 0:
        min_sources = 1

    return {
        "mode": mode,
        "context_summary": {
            "stakes": ctx.stakes_level,
            "sensitivity": ctx.sensitivity,
            "analysis_confidence": ctx.analysis_confidence,
            "uncertainty": ctx.uncertainty_level,
            "effective_uncertainty": compute_effective_uncertainty(ctx),
            "risk": ctx.is_sensitive_risk,
        },
        "n_models": n_models,
        "web_search_required": any(
            x in names for x in [
                "verification_obligatoire",
                "sources_min",
                "mode_d_obligatoire",
                "consensus_non_preuve"
            ]
        ),
        "min_independent_sources": min_sources,
        "checklist_hypothese_annexe": "checklist_hypothese" in names,
        "constraints_applied": [f"[{c.cls.name}] {c.name}" for c in constraints],
    }


# ======================================================================
# LOCAL HEURISTIC ANALYZER (Optimized for offline)
# ======================================================================

# Precompiled keyword sets for performance
KEYWORDS_QUANTITATIVE = {
    "combien", "pourcentage", "taux", "chiffre", "statistique",
    "nombre", "ratio", "proportion", "moyenne", "médiane"
}
KEYWORDS_CAUSAL_QUESTION = {"pourquoi", "comment se fait-il", "d'où vient"}
KEYWORDS_CAUSAL_CLAIM = {
    "cause", "entraîne", "provoque", "à cause de", "en raison de",
    "responsable de", "génère", "produit", "déclenche"
}
KEYWORDS_HYPOTHESIS = {
    "si ", "suppose", "hypothèse", "imaginons", "et si", "assumons",
    "considérons", "postulons"
}
KEYWORDS_CONTROVERSIAL = {
    "controvers", "débat", "polémique", "conspiration", "complot",
    "convergence", "épistémolog", "epistemolog", "veritas", "controverse"
}
KEYWORDS_DEPTH = {
    "en profondeur", "approfondi", "détaillé", "analyse complète",
    "compare en détail", "explore", "explique pas à pas", "complet"
}
KEYWORDS_SENSITIVE = {
    "vaccin", "santé", "sécurité", "danger", "médicament", "dose",
    "arme", "explosif", "toxique", "overdose", "suicide", "poison",
    "infection", "épidémie", "maladie"
}
KEYWORDS_CURRENT = {
    "actuel", "aujourd'hui", "récent", "cette année", "maintenant",
    "qui est", "ceo", "président", "dernière version", "en 2026",
    "actuellement", "dernièrement"
}


def local_heuristic_analyzer(prompt: str) -> dict:
    """Fast local analysis — no API calls.
    Produces only observations (ObservedFeatures), never policy."""
    p = prompt.lower()
    words = p.split()

    # Quantitative detection — improved regex to catch single digits, decimals and percentages
    quantitative = (
        bool(re.search(r"\d+([.,]\d+)?%?", p))
        or any(w in p for w in KEYWORDS_QUANTITATIVE)
    )

    # Causal question vs causal claim (CRITICAL distinction)
    ends_with_question = p.strip().endswith("?")
    causal_question = (
        ends_with_question
        and any(w in p for w in KEYWORDS_CAUSAL_QUESTION)
    )
    causal_claim = (
        (not causal_question)
        and any(w in p for w in KEYWORDS_CAUSAL_CLAIM)
    )

    # Other features
    hypothesis = any(w in p for w in KEYWORDS_HYPOTHESIS)
    controversial = any(w in p for w in KEYWORDS_CONTROVERSIAL)
    explicit_depth = any(w in p for w in KEYWORDS_DEPTH)
    sensitive_topic = any(w in p for w in KEYWORDS_SENSITIVE)
    current_fact = any(w in p for w in KEYWORDS_CURRENT)

    # Epistemic uncertainty: adjusted by topic type
    if controversial:
        uncertainty = 0.75
    elif causal_claim or hypothesis:
        uncertainty = 0.60
    elif quantitative or current_fact:
        uncertainty = 0.50
    else:
        uncertainty = 0.25

    # truth_apt: Is this claim-like (vs pure opinion, fiction, etc.)?
    # Heuristic: if it has causal/quantitative/current facts, it's truth-apt
    truth_apt = (
        causal_claim or causal_question or quantitative
        or current_fact or (sensitive_topic and "?" not in p)
    )

    return {
        "truth_apt": truth_apt,
        "contains_hypothesis": hypothesis,
        "contains_causal_claim": causal_claim,
        "contains_causal_question": causal_question,
        "contains_quantitative_claim": quantitative,
        "is_controversial_topic": controversial,
        "explicit_depth_request": explicit_depth,
        "is_sensitive_topic": sensitive_topic,
        "mentions_current_fact": current_fact,
        "analysis_confidence": 0.6,  # Local heuristic is moderately confident
        "uncertainty_level": uncertainty,
    }


# ======================================================================
# OUTCOME LOGGING (Self-application layer)
# ======================================================================


@dataclass
class RoutingOutcome:
    """Record of how a prompt was routed and (optionally) how it performed."""
    timestamp: str
    prompt_hash: str
    prompt_snippet: str  # First 100 chars
    mode_predicted: str
    context: DecisionContext
    constraints: List[str]
    ground_truth_mode: Optional[str] = None  # Set after evaluation
    was_correct: Optional[bool] = None  # True if predicted == actual
    notes: str = ""


class OutcomeLogger:
    """Track routing decisions for self-correction.
    The meta-rule: collect evidence on whether our rules work."""

    def __init__(self, log_file: str = ".veritas_outcomes.jsonl"):
        self.log_file = log_file
        self.outcomes: List[RoutingOutcome] = []

    def log_routing(
        self,
        prompt: str,
        mode: str,
        ctx: DecisionContext,
        constraints: List[Constraint]
    ) -> RoutingOutcome:
        """Record a routing decision."""
        import hashlib
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        snippet = prompt[:100].replace("\n", " ")

        outcome = RoutingOutcome(
            timestamp=datetime.now().isoformat(),
            prompt_hash=prompt_hash,
            prompt_snippet=snippet,
            mode_predicted=mode,
            context=ctx,
            constraints=[c.name for c in constraints],
        )
        self.outcomes.append(outcome)
        self._write_outcome(outcome)
        return outcome

    def mark_correct(self, outcome: RoutingOutcome, actual_mode: str) -> None:
        """After evaluation, mark if our routing was correct."""
        outcome.ground_truth_mode = actual_mode
        outcome.was_correct = (outcome.mode_predicted == actual_mode)
        self._write_outcome(outcome)

    def _write_outcome(self, outcome: RoutingOutcome) -> None:
        """Append outcome to log file (UTF-8 encoded)."""
        # Open with explicit UTF-8 encoding to safely write non-ASCII text
        with open(self.log_file, "a", encoding="utf-8") as f:
            line = json.dumps({
                "timestamp": outcome.timestamp,
                "prompt_hash": outcome.prompt_hash,
                "mode_predicted": outcome.mode_predicted,
                "ground_truth_mode": outcome.ground_truth_mode,
                "was_correct": outcome.was_correct,
                "constraints": outcome.constraints,
                "notes": outcome.notes,
            }, ensure_ascii=False)
            f.write(line + "\n")

    def accuracy_summary(self) -> Optional[Dict]:
        """Compute routing accuracy from logged outcomes."""
        evaluated = [o for o in self.outcomes if o.was_correct is not None]
        if not evaluated:
            return None

        correct = sum(1 for o in evaluated if o.was_correct)
        return {
            "total_evaluated": len(evaluated),
            "correct": correct,
            "accuracy": correct / len(evaluated),
            "modes": {
                mode: {
                    "predicted": sum(1 for o in evaluated if o.mode_predicted == mode),
                    "correct": sum(1 for o in evaluated if o.mode_predicted == mode and o.was_correct),
                }
                for mode in ("direct", "standard", "approfondi")
            },
        }


# ======================================================================
# ANALYZER + RUN
# ======================================================================


class PromptAnalyzerLocal:
    """Pure local analyzer — no API."""

    def __init__(self, log_outcomes: bool = True):
        self.logger = OutcomeLogger() if log_outcomes else None

    def analyze(self, prompt: str) -> DecisionContext:
        """Analyze prompt with local heuristics."""
        data = local_heuristic_analyzer(prompt)
        features = ObservedFeatures(
            truth_apt=data.get("truth_apt", False),
            contains_hypothesis=data.get("contains_hypothesis", False),
            contains_causal_claim=data.get("contains_causal_claim", False),
            contains_causal_question=data.get("contains_causal_question", False),
            contains_quantitative_claim=data.get("contains_quantitative_claim", False),
            is_controversial_topic=data.get("is_controversial_topic", False),
            explicit_depth_request=data.get("explicit_depth_request", False),
            is_sensitive_topic=data.get("is_sensitive_topic", False),
            mentions_current_fact=data.get("mentions_current_fact", False),
            analysis_confidence=data.get("analysis_confidence", 0.6),
            uncertainty_level=data.get("uncertainty_level", 0.5),
        )
        return DecisionContext.from_features(features)


def run(prompt: str, log_outcomes: bool = True) -> dict:
    """Analyze and route a prompt. Return full pipeline spec."""
    analyzer = PromptAnalyzerLocal(log_outcomes=log_outcomes)
    ctx = analyzer.analyze(prompt)
    constraints = resolve_conflicts(kernel_decide(ctx))
    pipeline = build_pipeline(ctx, constraints)

    # Log the routing decision
    if analyzer.logger:
        analyzer.logger.log_routing(prompt, pipeline["mode"], ctx, constraints)

    return pipeline


# ======================================================================
# INTERACTIVE DEMO
# ======================================================================


def pretty_print_pipeline(pipeline: dict) -> None:
    """Pretty-print the pipeline spec."""
    print("\n" + "=" * 70)
    print(f"Mode: {pipeline['mode'].upper()}")
    print("=" * 70)
    print(f"\n📊 Context:")
    for key, value in pipeline["context_summary"].items():
        if isinstance(value, float):
            print(f"   {key:.<25} {value:.2f}")
        else:
            print(f"   {key:.<25} {value}")

    print(f"\n🔍 Pipeline spec:")
    print(f"   Models to consult: {pipeline['n_models']}")
    print(f"   Web search required: {pipeline['web_search_required']}")
    print(f"   Min independent sources: {pipeline['min_independent_sources']}")
    print(f"   Hypothesis checklist: {pipeline['checklist_hypothese_annexe']}")

    print(f"\n⚖️  Constraints ({len(pipeline['constraints_applied'])} applied):")
    for constraint in pipeline["constraints_applied"]:
        print(f"   • {constraint}")
    print()


if __name__ == "__main__":
    # Configure logging for CLI usage
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("veritas")

    logger.info("=" * 70)
    logger.info("VERITAS Kernel — Local Heuristic Mode (Offline)")
    logger.info("=" * 70)
    logger.info("(Pure local analysis — no API calls needed.)")
    logger.info("Type 'quit' or Ctrl+C to exit.\n")

    try:
        while True:
            try:
                prompt = input("Prompt > ").strip()
            except (EOFError, KeyboardInterrupt):
                logger.info("\n[Exit]")
                break

            if prompt.lower() in ("quit", "exit"):
                break

            if prompt:
                pipeline = run(prompt, log_outcomes=True)
                pretty_print_pipeline(pipeline)

    except KeyboardInterrupt:
        logger.info("\n[Interrupted]")
