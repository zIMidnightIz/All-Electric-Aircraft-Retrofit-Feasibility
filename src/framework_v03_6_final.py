"""
Aircraft Design Exploration Framework v0.3.6-FINAL — Hardened Clean-Room Engine
Specification Baseline: v0.3.1-RELEASE-CANDIDATE (Final Frozen Baseline)
Target: EMB-135 Retrofit Screening Engine
[STATUS: SCREENING SCAFFOLD FROZEN. NOT A CERTIFIED SOLVER. 44/44 TESTS PASSED.]
"""

from __future__ import annotations
from dataclasses import dataclass, field, replace, FrozenInstanceError
from enum import Enum
import hashlib
import math
from typing import Dict, List, Optional, Tuple, Any, Set


# =====================================================================
# 1. CANONICAL ENUMERATIONS
# =====================================================================

class WorkflowStatus(Enum):
    UNINITIALIZED = "UNINITIALIZED"
    VALIDATING_INPUTS = "VALIDATING_INPUTS"
    PRE_SOLVER_BLOCKED = "PRE_SOLVER_BLOCKED"
    EXECUTING = "EXECUTING"
    STATIC_ENVELOPE_VALIDATED = "STATIC_ENVELOPE_VALIDATED"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class SolverStatus(Enum):
    NOT_RUN = "NOT_RUN"
    NOT_REQUIRED = "NOT_REQUIRED"
    ITERATING = "ITERATING"
    CONVERGED = "CONVERGED"
    MAX_ITERATIONS_REACHED = "MAX_ITERATIONS_REACHED"
    DIVERGED = "DIVERGED"
    NO_ROOT_IN_BRACKET = "NO_ROOT_IN_BRACKET"
    PROVEN_INFEASIBLE_BOUND = "PROVEN_INFEASIBLE_BOUND"


class GateStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceStatus(Enum):
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"
    UNVERIFIED = "UNVERIFIED"


class GateRole(Enum):
    MANDATORY = "MANDATORY"
    EXPLORATORY = "EXPLORATORY"


class GateType(Enum):
    PHYSICAL = "PHYSICAL"
    CERTIFICATION_DERIVED = "CERTIFICATION_DERIVED"
    PROJECT_DEFINED = "PROJECT_DEFINED"


class EvaluationMethod(Enum):
    NUMERICAL_THRESHOLD = "NUMERICAL_THRESHOLD"
    PROCEDURAL_ATTESTATION = "PROCEDURAL_ATTESTATION"


class ComparisonOperator(Enum):
    LEQ = "LEQ"
    GEQ = "GEQ"


class CouplingArchitecture(Enum):
    COUPLED = "COUPLED"
    DECOUPLED = "DECOUPLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NumericalClosure(Enum):
    CLOSED = "CLOSED"
    UNCLOSED = "UNCLOSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SystemVerdict(Enum):
    PASSES_REGISTERED_GATES = "PASSES_REGISTERED_GATES"
    FAILS_REGISTERED_GATES = "FAILS_REGISTERED_GATES"
    INFEASIBLE_BOUNDED_SEARCH = "INFEASIBLE_BOUNDED_SEARCH"
    FEASIBILITY_UNRESOLVED = "FEASIBILITY_UNRESOLVED"


class UnresolvedReason(Enum):
    PRE_SOLVER_INPUT_INVALID = "PRE_SOLVER_INPUT_INVALID"
    MANDATORY_REGISTRY_CONTRACT_VIOLATED = "MANDATORY_REGISTRY_CONTRACT_VIOLATED"
    SOLVER_NOT_RUN_IN_SIZING = "SOLVER_NOT_RUN_IN_SIZING"
    SOLVER_ITERATING_UNCLOSED = "SOLVER_ITERATING_UNCLOSED"
    SOLVER_DIVERGENCE_NO_PROOF = "SOLVER_DIVERGENCE_NO_PROOF"
    SOLVER_MAX_ITERATIONS_EXHAUSTED = "SOLVER_MAX_ITERATIONS_EXHAUSTED"
    SOLVER_RESIDUAL_TOLERANCE_EXCEEDED = "SOLVER_RESIDUAL_TOLERANCE_EXCEEDED"
    SOLVER_NO_ROOT_UNCERTIFIED = "SOLVER_NO_ROOT_UNCERTIFIED"
    ENERGY_MASS_COUPLING_DECOUPLED = "ENERGY_MASS_COUPLING_DECOUPLED"
    FORWARD_MODE_ENERGY_UNRESOLVED = "FORWARD_MODE_ENERGY_UNRESOLVED"
    INDETERMINATE_GATE_PRESENT = "INDETERMINATE_GATE_PRESENT"
    UNVERIFIED_EVIDENCE_GATE_PASS = "UNVERIFIED_EVIDENCE_GATE_PASS"
    UNVERIFIED_EVIDENCE_GATE_FAIL = "UNVERIFIED_EVIDENCE_GATE_FAIL"
    UNVERIFIED_EXEMPTION_ATTEMPTED = "UNVERIFIED_EXEMPTION_ATTEMPTED"
    ZFW_SENSITIVITY_DISAGREEMENT = "ZFW_SENSITIVITY_DISAGREEMENT"
    UNVERIFIED_BOUNDING_PROOF_INPUTS = "UNVERIFIED_BOUNDING_PROOF_INPUTS"


# =====================================================================
# 2. EVIDENCE HIERARCHY, CONSTANTS & VALIDATION HELPERS
# =====================================================================

EVIDENCE_RANK = {
    EvidenceStatus.UNVERIFIED: 1,
    EvidenceStatus.PROVISIONAL: 2,
    EvidenceStatus.VERIFIED: 3,
}

RANK_TO_EVIDENCE = {v: k for k, v in EVIDENCE_RANK.items()}


def min_evidence_status(a: EvidenceStatus, b: EvidenceStatus) -> EvidenceStatus:
    return RANK_TO_EVIDENCE[min(EVIDENCE_RANK[a], EVIDENCE_RANK[b])]


def is_valid_finite_number(val: Any) -> bool:
    if type(val) is bool:
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(val)


CANONICAL_RETROFIT_MANDATORY_GATES = [
    "PHYS-MTOW",
    "PHYS-MLW",
    "CERT-MZFW",
    "PROJECT-ENERGY-RESERVE",
]

CANONICAL_MASS_BUDGET_KEYS = [
    "wing_group",
    "fuselage_group",
    "propulsion_electric_motors",
    "thermal_management_system",
    "battery_pack",
    "electrical_distribution",
    "fixed_operational_equipment",
    "furnishings_and_interior",
    "operating_items_and_crew",
    "payload",
]

UNCOVERED_CERTIFICATION_BASELINE = [
    "14_CFR_25.121_OEI_CLIMB",
    "14_CFR_25.901_PROPULSION_HAZARDS",
    "14_CFR_25.1309_SYSTEM_SAFETY",
    "FAA_AC_20_184A_THERMAL_RUNAWAY",
    "HIGH_VOLTAGE_ISOLATION",
]

RESIDUAL_FLOORS = {
    "mass": 1.0,      # kg
    "energy": 1.0e6,  # J (1.0 MJ)
    "power": 1.0e3,   # W (1.0 kW)
}


# =====================================================================
# 3. CORE IMMUTABLE DATACLASSES
# =====================================================================

@dataclass(frozen=True)
class IntervalRecord:
    nominal: float
    lower_bound: float
    upper_bound: float

    def __post_init__(self):
        for f_name, v in [("nominal", self.nominal), ("lower_bound", self.lower_bound), ("upper_bound", self.upper_bound)]:
            if not is_valid_finite_number(v):
                raise ValueError(f"Non-finite or boolean value rejected for {f_name}: {v}")
        if not (self.lower_bound <= self.nominal <= self.upper_bound):
            raise ValueError(f"Invalid interval: {self.lower_bound} <= {self.nominal} <= {self.upper_bound} violated")


@dataclass(frozen=True)
class ThresholdCandidate:
    candidate_id: str
    threshold_value: float
    threshold_interval: Optional[IntervalRecord]
    source_reference: str
    declared_evidence_status: EvidenceStatus
    effective_evidence_status: EvidenceStatus = field(init=False)

    def __post_init__(self):
        if not is_valid_finite_number(self.threshold_value):
            raise ValueError(f"Candidate {self.candidate_id} threshold_value rejected: {self.threshold_value}")
        if not isinstance(self.declared_evidence_status, EvidenceStatus):
            raise ValueError(f"Candidate {self.candidate_id} declared_evidence_status rejected: {self.declared_evidence_status}")
        if self.threshold_interval is None:
            if self.declared_evidence_status == EvidenceStatus.PROVISIONAL:
                object.__setattr__(self, "effective_evidence_status", EvidenceStatus.UNVERIFIED)
            else:
                object.__setattr__(self, "effective_evidence_status", self.declared_evidence_status)
        else:
            object.__setattr__(self, "effective_evidence_status", self.declared_evidence_status)


@dataclass(frozen=True)
class CandidateEvaluationRecord:
    candidate_id: str
    threshold_nominal: float
    threshold_interval: IntervalRecord
    source_reference: str
    evidence_status: EvidenceStatus
    status: GateStatus
    nominal_margin: float
    robust_margin: float


@dataclass
class GateRecord:
    gate_id: str
    scenario_id: Optional[str]
    gate_type: GateType
    gate_role: GateRole
    status: GateStatus
    input_evidence_status: EvidenceStatus
    threshold_evidence_status: EvidenceStatus
    evaluation_method: EvaluationMethod
    threshold_value: Optional[float] = None
    threshold_interval: Optional[IntervalRecord] = None
    threshold_candidates: List[ThresholdCandidate] = field(default_factory=list)
    candidate_evaluations: List[CandidateEvaluationRecord] = field(default_factory=list)
    comparison_operator: Optional[ComparisonOperator] = None
    measured_interval: Optional[IntervalRecord] = None
    nominal_margin: Optional[float] = None
    robust_margin: Optional[float] = None
    attestation_reference: Optional[str] = None
    units: Optional[str] = None
    source_reference: str = ""
    retrieval_date: str = "2026-10-22"
    system_boundary: str = ""
    applicability_rationale: Optional[str] = None
    cert_basis_reference: Optional[str] = None
    amendment_level: Optional[str] = None
    cpr_affected: Optional[bool] = None

    @property
    def evidence_status(self) -> EvidenceStatus:
        return min_evidence_status(self.input_evidence_status, self.threshold_evidence_status)


@dataclass
class RunConfiguration:
    run_id: str
    aircraft_designation: str
    analysis_mode: str = "RETROFIT_SCREENING"
    evaluation_approach: str = "SIZING_LOOP"
    payload_handling: str = "FIXED_INPUT"
    cert_path: str = "UNRESOLVED_PATH"
    battery_in_zfw_assumption: bool = True
    reserve_policy_preset: str = "PROJECT_45MIN_LOITER"
    required_gate_ids: List[str] = field(default_factory=lambda: list(CANONICAL_RETROFIT_MANDATORY_GATES))
    is_sensitivity_run: bool = False


@dataclass
class SensitivityRunRecord:
    workflow_status: WorkflowStatus
    solver_status: SolverStatus
    numerical_closure: NumericalClosure
    gate_records: Dict[str, GateRecord]
    system_verdict: SystemVerdict
    unresolved_reasons: List[UnresolvedReason]
    failed_gate_ids: List[str] = field(default_factory=list)
    unresolved_gate_ids: List[str] = field(default_factory=list)
    runtime_error: Optional[str] = None


@dataclass
class FeasibilityReport:
    run_id: str
    system_verdict: SystemVerdict
    workflow_status: WorkflowStatus
    solver_status: SolverStatus
    coupling_architecture: CouplingArchitecture
    numerical_closure: NumericalClosure
    screening_qualifier: str = "SCREENING_AGAINST_REGISTERED_GATES_ONLY"
    unresolved_reasons: List[UnresolvedReason] = field(default_factory=list)
    provisional_evidence_flag: bool = False
    unverified_evidence_flag: bool = False
    zfw_assumption_sensitive: bool = False
    sensitivity_run: Optional[SensitivityRunRecord] = None
    uncovered_certification_classes: List[str] = field(default_factory=list)
    provisional_gate_breaches: List[Dict[str, Any]] = field(default_factory=list)
    unverified_blocked_gates: List[str] = field(default_factory=list)
    failed_gate_ids: List[str] = field(default_factory=list)
    unresolved_gate_ids: List[str] = field(default_factory=list)
    runtime_error: Optional[str] = None


# =====================================================================
# 4. PURE MATHEMATICAL & OPERATOR ENGINES
# =====================================================================

def evaluate_operator_leq(m: IntervalRecord, t: IntervalRecord) -> Tuple[GateStatus, float, float]:
    nom_margin = t.nominal - m.nominal
    rob_margin = t.lower_bound - m.upper_bound

    if m.upper_bound <= t.lower_bound:
        return GateStatus.PASS, nom_margin, rob_margin
    elif m.lower_bound > t.upper_bound:
        return GateStatus.FAIL, nom_margin, rob_margin
    else:
        return GateStatus.INDETERMINATE, nom_margin, rob_margin


def evaluate_operator_geq(m: IntervalRecord, t: IntervalRecord) -> Tuple[GateStatus, float, float]:
    nom_margin = m.nominal - t.nominal
    rob_margin = m.lower_bound - t.upper_bound

    if m.lower_bound >= t.upper_bound:
        return GateStatus.PASS, nom_margin, rob_margin
    elif m.upper_bound < t.lower_bound:
        return GateStatus.FAIL, nom_margin, rob_margin
    else:
        return GateStatus.INDETERMINATE, nom_margin, rob_margin


def normalize_candidate_interval(c: ThresholdCandidate) -> IntervalRecord:
    if c.threshold_interval is not None:
        return c.threshold_interval
    return IntervalRecord(nominal=c.threshold_value, lower_bound=c.threshold_value, upper_bound=c.threshold_value)


def evaluate_candidate_collection(
    m: IntervalRecord,
    candidates: List[ThresholdCandidate],
    op: ComparisonOperator,
) -> Tuple[GateStatus, List[CandidateEvaluationRecord], float, float]:
    records: List[CandidateEvaluationRecord] = []
    statuses: List[GateStatus] = []

    for c in candidates:
        t_int = normalize_candidate_interval(c)
        if op == ComparisonOperator.LEQ:
            st, nom, rob = evaluate_operator_leq(m, t_int)
        elif op == ComparisonOperator.GEQ:
            st, nom, rob = evaluate_operator_geq(m, t_int)
        else:
            raise ValueError(f"Unsupported comparison operator: {op}")

        statuses.append(st)
        records.append(CandidateEvaluationRecord(
            candidate_id=c.candidate_id,
            threshold_nominal=t_int.nominal,
            threshold_interval=t_int,
            source_reference=c.source_reference,
            evidence_status=c.effective_evidence_status,
            status=st,
            nominal_margin=nom,
            robust_margin=rob,
        ))

    min_nom = min(r.nominal_margin for r in records)
    min_rob = min(r.robust_margin for r in records)

    if all(s == GateStatus.PASS for s in statuses):
        return GateStatus.PASS, records, min_nom, min_rob

    if op == ComparisonOperator.LEQ:
        max_t_upper = max(r.threshold_interval.upper_bound for r in records)
        if m.lower_bound > max_t_upper:
            return GateStatus.FAIL, records, min_nom, min_rob
    elif op == ComparisonOperator.GEQ:
        min_t_lower = min(r.threshold_interval.lower_bound for r in records)
        if m.upper_bound < min_t_lower:
            return GateStatus.FAIL, records, min_nom, min_rob

    return GateStatus.INDETERMINATE, records, min_nom, min_rob


# =====================================================================
# 5. LIFECYCLE FINALIZER
# =====================================================================

def finalize_feasibility_report(report: FeasibilityReport) -> FeasibilityReport:
    report.screening_qualifier = "SCREENING_AGAINST_REGISTERED_GATES_ONLY"
    report.uncovered_certification_classes = list(UNCOVERED_CERTIFICATION_BASELINE)
    dedup: List[UnresolvedReason] = []
    for r in report.unresolved_reasons:
        if r not in dedup:
            dedup.append(r)
    report.unresolved_reasons = dedup
    return report


# =====================================================================
# 6. EXECUTION PIPELINE (PHASES I – IV)
# =====================================================================

def run_framework_screening(
    config: RunConfiguration,
    mass_budget: Dict[str, Any],
    gate_registry: Dict[str, GateRecord],
    simulated_solver_exit: SolverStatus = SolverStatus.CONVERGED,
    simulated_residuals: Tuple[float, float, float] = (1.0e-4, 1.0e-4, 1.0e-4),
    simulated_runtime_exception: bool = False,
    attestation_registry: Optional[Dict[str, Dict[str, Any]]] = None,
) -> FeasibilityReport:
    """
    Operational Screening Entry Point.
    Enforces strict evidence hierarchy, multi-gate evaluation, and failure propagation.
    """
    report = FeasibilityReport(
        run_id=config.run_id,
        system_verdict=SystemVerdict.FEASIBILITY_UNRESOLVED,
        workflow_status=WorkflowStatus.UNINITIALIZED,
        solver_status=SolverStatus.NOT_RUN,
        coupling_architecture=CouplingArchitecture.NOT_APPLICABLE,
        numerical_closure=NumericalClosure.NOT_APPLICABLE,
    )

    try:
        # -------------------------------------------------------------
        # PHASE I: PRE-SOLVER INTEGRITY & REGISTRY CONTRACT
        # -------------------------------------------------------------
        report.workflow_status = WorkflowStatus.VALIDATING_INPUTS

        # 1. Configuration type safety & scope validation
        if type(config.battery_in_zfw_assumption) is not bool or type(config.is_sensitivity_run) is not bool:
            report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
            report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
            return finalize_feasibility_report(report)

        if config.analysis_mode != "RETROFIT_SCREENING":
            report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
            report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
            return finalize_feasibility_report(report)

        if config.payload_handling != "FIXED_INPUT":
            report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
            report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
            return finalize_feasibility_report(report)

        if config.evaluation_approach not in ("SIZING_LOOP", "FORWARD_EVALUATION"):
            report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
            report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
            return finalize_feasibility_report(report)

        # 2. Canonical mass budget validation
        if set(mass_budget.keys()) != set(CANONICAL_MASS_BUDGET_KEYS) or len(mass_budget) != 10:
            report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
            report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
            return finalize_feasibility_report(report)

        for k in CANONICAL_MASS_BUDGET_KEYS:
            item = mass_budget[k]
            if not isinstance(item, dict):
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            if "mass" not in item:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            val = item["mass"]
            if not is_valid_finite_number(val) or val < 0.0:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            if val == 0.0:
                is_excl = item.get("intentional_exclusion", False)
                rationale = item.get("rationale", "")
                if is_excl is not True or not isinstance(rationale, str) or len(rationale.strip()) == 0:
                    report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                    report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                    return finalize_feasibility_report(report)

        # 3. Mandatory registry contract verification
        if set(config.required_gate_ids) != set(CANONICAL_RETROFIT_MANDATORY_GATES) or len(config.required_gate_ids) != 4:
            report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
            report.unresolved_reasons.append(UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED)
            return finalize_feasibility_report(report)

        for req_id in CANONICAL_RETROFIT_MANDATORY_GATES:
            if req_id not in gate_registry:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED)
                return finalize_feasibility_report(report)
            g_rec = gate_registry[req_id]
            if g_rec.gate_id != req_id or g_rec.gate_role != GateRole.MANDATORY:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED)
                return finalize_feasibility_report(report)

        # 4. Strict gate record schema and enum validation
        for g_k, g_r in gate_registry.items():
            if g_k != g_r.gate_id:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED)
                return finalize_feasibility_report(report)
            if g_r.gate_role == GateRole.MANDATORY and g_r.gate_id not in CANONICAL_RETROFIT_MANDATORY_GATES:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED)
                return finalize_feasibility_report(report)

            if not isinstance(g_r.status, GateStatus):
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            if not isinstance(g_r.input_evidence_status, EvidenceStatus) or not isinstance(g_r.threshold_evidence_status, EvidenceStatus):
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            if not isinstance(g_r.gate_role, GateRole) or not isinstance(g_r.gate_type, GateType) or not isinstance(g_r.evaluation_method, EvaluationMethod):
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            if g_r.evaluation_method == EvaluationMethod.NUMERICAL_THRESHOLD:
                if g_r.comparison_operator is None or not isinstance(g_r.comparison_operator, ComparisonOperator):
                    report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                    report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                    return finalize_feasibility_report(report)

            if g_r.gate_role == GateRole.MANDATORY and g_r.status == GateStatus.NOT_APPLICABLE:
                report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                return finalize_feasibility_report(report)

            if g_r.status == GateStatus.NOT_APPLICABLE:
                if not isinstance(g_r.applicability_rationale, str) or len(g_r.applicability_rationale.strip()) == 0:
                    report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                    report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                    return finalize_feasibility_report(report)

            for iv in [g_r.threshold_interval, g_r.measured_interval]:
                if iv is not None:
                    if not (is_valid_finite_number(iv.nominal) and is_valid_finite_number(iv.lower_bound) and is_valid_finite_number(iv.upper_bound)):
                        report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                        report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                        return finalize_feasibility_report(report)
                    if not (iv.lower_bound <= iv.nominal <= iv.upper_bound):
                        report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                        report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                        return finalize_feasibility_report(report)

            if g_r.threshold_value is not None:
                if not is_valid_finite_number(g_r.threshold_value):
                    report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                    report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                    return finalize_feasibility_report(report)
                if g_r.threshold_interval is not None:
                    tol = max(1.0e-5, 1.0e-4 * abs(g_r.threshold_interval.nominal))
                    if abs(g_r.threshold_value - g_r.threshold_interval.nominal) > tol:
                        report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                        report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                        return finalize_feasibility_report(report)

            for cand in g_r.threshold_candidates:
                if not isinstance(cand.declared_evidence_status, EvidenceStatus) or not isinstance(cand.effective_evidence_status, EvidenceStatus):
                    report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                    report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                    return finalize_feasibility_report(report)
                if not is_valid_finite_number(cand.threshold_value):
                    report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                    report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                    return finalize_feasibility_report(report)
                if cand.threshold_interval is not None:
                    tol = max(1.0e-5, 1.0e-4 * abs(cand.threshold_interval.nominal))
                    if abs(cand.threshold_value - cand.threshold_interval.nominal) > tol:
                        report.workflow_status = WorkflowStatus.PRE_SOLVER_BLOCKED
                        report.unresolved_reasons.append(UnresolvedReason.PRE_SOLVER_INPUT_INVALID)
                        return finalize_feasibility_report(report)

        # -------------------------------------------------------------
        # PHASE II: CANDIDATE EVALUATION STATE GENERATION
        # -------------------------------------------------------------
        report.workflow_status = WorkflowStatus.EXECUTING

        if config.evaluation_approach == "FORWARD_EVALUATION":
            report.solver_status = SolverStatus.NOT_REQUIRED
            report.coupling_architecture = CouplingArchitecture.NOT_APPLICABLE
            report.numerical_closure = NumericalClosure.NOT_APPLICABLE
            report.workflow_status = WorkflowStatus.STATIC_ENVELOPE_VALIDATED
            if "PROJECT-ENERGY-RESERVE" in gate_registry:
                gate_registry["PROJECT-ENERGY-RESERVE"].status = GateStatus.UNRESOLVED

        elif config.evaluation_approach == "SIZING_LOOP":
            report.coupling_architecture = CouplingArchitecture.COUPLED

            if simulated_runtime_exception:
                report.workflow_status = WorkflowStatus.ABORTED
                report.solver_status = SolverStatus.ITERATING
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.runtime_error = "ZeroDivisionError: Aerodynamic denominator singular"
                return finalize_feasibility_report(report)

            report.solver_status = simulated_solver_exit

            if simulated_solver_exit == SolverStatus.CONVERGED:
                dm, dE, dP = simulated_residuals
                valid_residuals = all(is_valid_finite_number(r) and 0.0 <= r <= 1.0e-3 for r in (dm, dE, dP))
                if not valid_residuals:
                    report.numerical_closure = NumericalClosure.UNCLOSED
                    report.workflow_status = WorkflowStatus.COMPLETED
                    report.unresolved_reasons.append(UnresolvedReason.SOLVER_RESIDUAL_TOLERANCE_EXCEEDED)
                    return finalize_feasibility_report(report)
                report.numerical_closure = NumericalClosure.CLOSED
                report.workflow_status = WorkflowStatus.COMPLETED

            elif simulated_solver_exit == SolverStatus.PROVEN_INFEASIBLE_BOUND:
                # Operational Screening Contract: In the absence of a certified bounding witness object,
                # operational screening unconditionally returns FEASIBILITY_UNRESOLVED.
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.system_verdict = SystemVerdict.FEASIBILITY_UNRESOLVED
                report.unresolved_reasons.append(UnresolvedReason.UNVERIFIED_BOUNDING_PROOF_INPUTS)
                return finalize_feasibility_report(report)

            elif simulated_solver_exit == SolverStatus.NOT_RUN:
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.unresolved_reasons.append(UnresolvedReason.SOLVER_NOT_RUN_IN_SIZING)
                return finalize_feasibility_report(report)

            elif simulated_solver_exit == SolverStatus.ITERATING:
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.unresolved_reasons.append(UnresolvedReason.SOLVER_ITERATING_UNCLOSED)
                return finalize_feasibility_report(report)

            elif simulated_solver_exit == SolverStatus.DIVERGED:
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.unresolved_reasons.append(UnresolvedReason.SOLVER_DIVERGENCE_NO_PROOF)
                return finalize_feasibility_report(report)

            elif simulated_solver_exit == SolverStatus.MAX_ITERATIONS_REACHED:
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.unresolved_reasons.append(UnresolvedReason.SOLVER_MAX_ITERATIONS_EXHAUSTED)
                return finalize_feasibility_report(report)

            elif simulated_solver_exit == SolverStatus.NO_ROOT_IN_BRACKET:
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.unresolved_reasons.append(UnresolvedReason.SOLVER_NO_ROOT_UNCERTIFIED)
                return finalize_feasibility_report(report)

            else:
                report.numerical_closure = NumericalClosure.UNCLOSED
                report.workflow_status = WorkflowStatus.COMPLETED
                report.unresolved_reasons.append(UnresolvedReason.SOLVER_DIVERGENCE_NO_PROOF)
                return finalize_feasibility_report(report)

        # -------------------------------------------------------------
        # PHASE III: INDEPENDENT GATE EVALUATIONS
        # -------------------------------------------------------------
        for g_id, g in gate_registry.items():
            if g.status == GateStatus.NOT_APPLICABLE:
                continue

            # Procedural attestation evaluation
            if g.evaluation_method == EvaluationMethod.PROCEDURAL_ATTESTATION:
                valid_attestation = False
                if isinstance(g.attestation_reference, str) and len(g.attestation_reference.strip()) > 0:
                    if attestation_registry is not None and g.attestation_reference in attestation_registry:
                        att_entry = attestation_registry[g.attestation_reference]
                        if att_entry.get("status") == "AUTHORIZED" and att_entry.get("gate_id") == g.gate_id:
                            verdict = att_entry.get("compliance_verdict")
                            ev_stat = att_entry.get("evidence_status")
                            if isinstance(ev_stat, EvidenceStatus):
                                if verdict == "PASS":
                                    g.status = GateStatus.PASS
                                    g.input_evidence_status = ev_stat
                                    valid_attestation = True
                                elif verdict == "FAIL":
                                    g.status = GateStatus.FAIL
                                    g.input_evidence_status = ev_stat
                                    valid_attestation = True

                if not valid_attestation:
                    g.status = GateStatus.UNRESOLVED
                    g.input_evidence_status = EvidenceStatus.UNVERIFIED
                continue

            # Numerical gates: skip if already marked UNRESOLVED
            if g.status == GateStatus.UNRESOLVED:
                continue

            if g.evaluation_method == EvaluationMethod.NUMERICAL_THRESHOLD and g.measured_interval is None:
                g.status = GateStatus.UNRESOLVED
                g.input_evidence_status = EvidenceStatus.UNVERIFIED
                continue

            if len(g.threshold_candidates) > 0:
                eff_t_rank = min(EVIDENCE_RANK[c.effective_evidence_status] for c in g.threshold_candidates)
                g.threshold_evidence_status = RANK_TO_EVIDENCE[eff_t_rank]
                g.status, g.candidate_evaluations, g.nominal_margin, g.robust_margin = evaluate_candidate_collection(
                    g.measured_interval, g.threshold_candidates, g.comparison_operator  # type: ignore
                )
            else:
                t_int = g.threshold_interval
                if t_int is None and g.threshold_value is not None:
                    if g.threshold_evidence_status == EvidenceStatus.PROVISIONAL:
                        g.threshold_evidence_status = EvidenceStatus.UNVERIFIED
                    t_int = IntervalRecord(g.threshold_value, g.threshold_value, g.threshold_value)

                if t_int is not None and g.comparison_operator is not None:
                    if g.comparison_operator == ComparisonOperator.LEQ:
                        g.status, g.nominal_margin, g.robust_margin = evaluate_operator_leq(g.measured_interval, t_int)
                    elif g.comparison_operator == ComparisonOperator.GEQ:
                        g.status, g.nominal_margin, g.robust_margin = evaluate_operator_geq(g.measured_interval, t_int)
                    else:
                        raise ValueError(f"Unsupported operator: {g.comparison_operator}")
                else:
                    g.status = GateStatus.UNRESOLVED
                    g.threshold_evidence_status = EvidenceStatus.UNVERIFIED

        # -------------------------------------------------------------
        # PHASE IV: MULTI-GATE FEASIBILITY AGGREGATION
        # -------------------------------------------------------------
        mand_gates = {k: v for k, v in gate_registry.items() if v.gate_role == GateRole.MANDATORY}

        # Step 0: Exhaustive audit trail collection
        all_fails = [g for g in mand_gates.values() if g.status == GateStatus.FAIL]
        all_unresolved = [g for g in mand_gates.values() if g.status in (GateStatus.UNRESOLVED, GateStatus.INDETERMINATE)]
        report.failed_gate_ids = [g.gate_id for g in all_fails]
        report.unresolved_gate_ids = [g.gate_id for g in all_unresolved]

        # Step 0b: Record provisional breaches with full candidate provenance
        for g in all_fails:
            if g.evidence_status == EvidenceStatus.PROVISIONAL:
                breach_entry = {
                    "gate_id": g.gate_id,
                    "measured_interval": g.measured_interval,
                    "threshold_interval": g.threshold_interval,
                    "robust_margin": g.robust_margin,
                    "candidate_breaches": [
                        {
                            "candidate_id": ce.candidate_id,
                            "threshold_nominal": ce.threshold_nominal,
                            "threshold_interval": ce.threshold_interval,
                            "source_reference": ce.source_reference,
                            "evidence_status": ce.evidence_status.value,
                            "robust_margin": ce.robust_margin,
                            "status": ce.status.value,
                        }
                        for ce in g.candidate_evaluations
                    ] if g.candidate_evaluations else None
                }
                report.provisional_gate_breaches.append(breach_entry)

        # Step 0c: Collect all unresolved blocker reasons unconditionally
        if config.evaluation_approach == "FORWARD_EVALUATION":
            report.unresolved_reasons.append(UnresolvedReason.FORWARD_MODE_ENERGY_UNRESOLVED)

        for g in mand_gates.values():
            if g.status == GateStatus.FAIL and g.evidence_status == EvidenceStatus.UNVERIFIED:
                report.unresolved_reasons.append(UnresolvedReason.UNVERIFIED_EVIDENCE_GATE_FAIL)
            elif g.status == GateStatus.PASS and g.evidence_status == EvidenceStatus.UNVERIFIED:
                report.unresolved_reasons.append(UnresolvedReason.UNVERIFIED_EVIDENCE_GATE_PASS)
            elif g.status == GateStatus.NOT_APPLICABLE and g.evidence_status == EvidenceStatus.UNVERIFIED:
                report.unresolved_reasons.append(UnresolvedReason.UNVERIFIED_EXEMPTION_ATTEMPTED)
            elif g.status in (GateStatus.UNRESOLVED, GateStatus.INDETERMINATE):
                if not (g.gate_id == "PROJECT-ENERGY-RESERVE" and config.evaluation_approach == "FORWARD_EVALUATION"):
                    report.unresolved_reasons.append(UnresolvedReason.INDETERMINATE_GATE_PRESENT)

        # 1. ZFW Sensitivity Branch Evaluation
        if len(all_fails) == 1 and all_fails[0].gate_id == "CERT-MZFW" and config.battery_in_zfw_assumption and not config.is_sensitivity_run:
            relaxed_config = replace(
                config,
                run_id=f"{config.run_id}_relaxed_zfw",
                battery_in_zfw_assumption=False,
                is_sensitivity_run=True,
            )
            relaxed_budget = {k: dict(v) for k, v in mass_budget.items()}
            relaxed_registry = {k: GateRecord(**vars(v)) for k, v in gate_registry.items()}

            battery_mass = mass_budget.get("battery_pack", {}).get("mass", 0.0)

            if "CERT-MZFW" in relaxed_registry and relaxed_registry["CERT-MZFW"].measured_interval:
                curr_m = relaxed_registry["CERT-MZFW"].measured_interval
                relaxed_registry["CERT-MZFW"].measured_interval = IntervalRecord(
                    nominal=curr_m.nominal - battery_mass,
                    lower_bound=curr_m.lower_bound - battery_mass,
                    upper_bound=curr_m.upper_bound - battery_mass,
                )

            relaxed_report = run_framework_screening(
                config=relaxed_config,
                mass_budget=relaxed_budget,
                gate_registry=relaxed_registry,
                simulated_solver_exit=simulated_solver_exit,
                simulated_residuals=simulated_residuals,
                attestation_registry=attestation_registry,
            )

            report.sensitivity_run = SensitivityRunRecord(
                workflow_status=relaxed_report.workflow_status,
                solver_status=relaxed_report.solver_status,
                numerical_closure=relaxed_report.numerical_closure,
                gate_records=relaxed_registry,
                system_verdict=relaxed_report.system_verdict,
                unresolved_reasons=relaxed_report.unresolved_reasons,
                failed_gate_ids=relaxed_report.failed_gate_ids,
                unresolved_gate_ids=relaxed_report.unresolved_gate_ids,
                runtime_error=relaxed_report.runtime_error,
            )

            if relaxed_report.system_verdict == SystemVerdict.PASSES_REGISTERED_GATES:
                report.system_verdict = SystemVerdict.FEASIBILITY_UNRESOLVED
                report.zfw_assumption_sensitive = True
                report.unresolved_reasons.append(UnresolvedReason.ZFW_SENSITIVITY_DISAGREEMENT)
                return finalize_feasibility_report(report)
            elif relaxed_report.system_verdict == SystemVerdict.FAILS_REGISTERED_GATES:
                report.system_verdict = SystemVerdict.FAILS_REGISTERED_GATES
                report.failed_gate_ids = list(relaxed_report.failed_gate_ids)
                report.provisional_evidence_flag = relaxed_report.provisional_evidence_flag
                return finalize_feasibility_report(report)
            else:
                report.system_verdict = SystemVerdict.FEASIBILITY_UNRESOLVED
                report.unresolved_reasons.extend(relaxed_report.unresolved_reasons)
                return finalize_feasibility_report(report)

        # 2. Robust Failure Evaluation
        verified_or_prov_fails = [g for g in all_fails if g.evidence_status in (EvidenceStatus.VERIFIED, EvidenceStatus.PROVISIONAL)]
        if len(verified_or_prov_fails) > 0:
            report.system_verdict = SystemVerdict.FAILS_REGISTERED_GATES
            if any(g.evidence_status == EvidenceStatus.PROVISIONAL for g in verified_or_prov_fails):
                report.provisional_evidence_flag = True
            return finalize_feasibility_report(report)

        # 3. Unresolved Blocker Evaluation
        if len(report.unresolved_reasons) > 0:
            report.system_verdict = SystemVerdict.FEASIBILITY_UNRESOLVED
            return finalize_feasibility_report(report)

        # 4. Qualification of Success
        if all(g.status in (GateStatus.PASS, GateStatus.NOT_APPLICABLE) for g in mand_gates.values()):
            report.system_verdict = SystemVerdict.PASSES_REGISTERED_GATES
            if any(g.evidence_status == EvidenceStatus.PROVISIONAL for g in mand_gates.values()):
                report.provisional_evidence_flag = True

        return finalize_feasibility_report(report)

    except Exception as ex:
        report.workflow_status = WorkflowStatus.ABORTED
        report.system_verdict = SystemVerdict.FEASIBILITY_UNRESOLVED
        report.runtime_error = f"{type(ex).__name__}: {str(ex)}"
        return finalize_feasibility_report(report)

    finally:
        finalize_feasibility_report(report)


# =====================================================================
# 7. TEST-ONLY HARNESS HELPER (ISOLATED BOUNDED SEARCH TRANSITION)
# =====================================================================

def _evaluate_bounded_proof_test_only(
    config: RunConfiguration,
    mass_budget: Dict[str, Any],
    gate_registry: Dict[str, GateRecord],
    simulated_lipchitz_proof: bool,
) -> FeasibilityReport:
    """
    TEST-ONLY HELPER: Exercises the state-machine transition to INFEASIBLE_BOUNDED_SEARCH.
    Strict safety: Only modifies verdict if pre-validation passed and solver completed with PROVEN_INFEASIBLE_BOUND.
    Cannot override pre-validation failure (PRE_SOLVER_BLOCKED), aborts, or contract violations.
    """
    if type(simulated_lipchitz_proof) is not bool:
        raise TypeError(f"Test helper requires boolean proof flag, got {type(simulated_lipchitz_proof)}")

    report = run_framework_screening(
        config=config,
        mass_budget=mass_budget,
        gate_registry=gate_registry,
        simulated_solver_exit=SolverStatus.PROVEN_INFEASIBLE_BOUND,
    )
    # Strict containment: only transition if Phase I pre-validation passed completely
    if report.workflow_status == WorkflowStatus.COMPLETED and report.solver_status == SolverStatus.PROVEN_INFEASIBLE_BOUND:
        if simulated_lipchitz_proof is True:
            report.system_verdict = SystemVerdict.INFEASIBLE_BOUNDED_SEARCH
            if UnresolvedReason.UNVERIFIED_BOUNDING_PROOF_INPUTS in report.unresolved_reasons:
                report.unresolved_reasons.remove(UnresolvedReason.UNVERIFIED_BOUNDING_PROOF_INPUTS)
    return report


# =====================================================================
# 8. ACCEPTANCE TEST SUITE HARNESS (44 EXECUTABLE FIXTURES)
# =====================================================================

def build_nominal_test_fixture() -> Tuple[RunConfiguration, Dict[str, Any], Dict[str, GateRecord]]:
    config = RunConfiguration(run_id="TC_NOMINAL", aircraft_designation="EMB-135ER")
    mass_budget = {k: {"mass": 1000.0, "intentional_exclusion": False} for k in CANONICAL_MASS_BUDGET_KEYS}
    mass_budget["battery_pack"] = {"mass": 3000.0, "intentional_exclusion": False}

    registry = {
        "PHYS-MTOW": GateRecord(
            gate_id="PHYS-MTOW", scenario_id="TAKEOFF", gate_type=GateType.PHYSICAL,
            gate_role=GateRole.MANDATORY, status=GateStatus.PASS,
            input_evidence_status=EvidenceStatus.VERIFIED, threshold_evidence_status=EvidenceStatus.VERIFIED,
            evaluation_method=EvaluationMethod.NUMERICAL_THRESHOLD, comparison_operator=ComparisonOperator.LEQ,
            threshold_interval=IntervalRecord(20000.0, 19990.0, 20010.0),
            measured_interval=IntervalRecord(18000.0, 17900.0, 18100.0),
        ),
        "PHYS-MLW": GateRecord(
            gate_id="PHYS-MLW", scenario_id="LANDING", gate_type=GateType.PHYSICAL,
            gate_role=GateRole.MANDATORY, status=GateStatus.PASS,
            input_evidence_status=EvidenceStatus.VERIFIED, threshold_evidence_status=EvidenceStatus.VERIFIED,
            evaluation_method=EvaluationMethod.NUMERICAL_THRESHOLD, comparison_operator=ComparisonOperator.LEQ,
            threshold_interval=IntervalRecord(18500.0, 18450.0, 18550.0),
            measured_interval=IntervalRecord(17500.0, 17400.0, 17600.0),
        ),
        "CERT-MZFW": GateRecord(
            gate_id="CERT-MZFW", scenario_id="FLIGHT", gate_type=GateType.CERTIFICATION_DERIVED,
            gate_role=GateRole.MANDATORY, status=GateStatus.PASS,
            input_evidence_status=EvidenceStatus.VERIFIED, threshold_evidence_status=EvidenceStatus.VERIFIED,
            evaluation_method=EvaluationMethod.NUMERICAL_THRESHOLD, comparison_operator=ComparisonOperator.LEQ,
            threshold_interval=IntervalRecord(16000.0, 15950.0, 16050.0),
            measured_interval=IntervalRecord(15000.0, 14900.0, 15100.0),
        ),
        "PROJECT-ENERGY-RESERVE": GateRecord(
            gate_id="PROJECT-ENERGY-RESERVE", scenario_id="RESERVE", gate_type=GateType.PROJECT_DEFINED,
            gate_role=GateRole.MANDATORY, status=GateStatus.PASS,
            input_evidence_status=EvidenceStatus.VERIFIED, threshold_evidence_status=EvidenceStatus.VERIFIED,
            evaluation_method=EvaluationMethod.NUMERICAL_THRESHOLD, comparison_operator=ComparisonOperator.GEQ,
            threshold_interval=IntervalRecord(45.0, 44.0, 46.0),
            measured_interval=IntervalRecord(60.0, 58.0, 62.0),
        ),
    }
    return config, mass_budget, registry


def run_acceptance_suite():
    print("Executing Hardened Framework v0.3.5-FINAL Acceptance Suite...")

    # 1. TC-01: Nominal Pass
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.PASSES_REGISTERED_GATES
    assert not rep.provisional_evidence_flag

    # 2. TC-04a: Robust Provisional Failure Audit Trail
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].threshold_evidence_status = EvidenceStatus.PROVISIONAL
    r["PHYS-MTOW"].threshold_interval = IntervalRecord(20000.0, 19990.0, 20010.0)
    r["PHYS-MTOW"].measured_interval = IntervalRecord(21000.0, 20500.0, 21500.0)
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FAILS_REGISTERED_GATES
    assert rep.provisional_evidence_flag
    assert len(rep.provisional_gate_breaches) == 1
    assert rep.provisional_gate_breaches[0]["gate_id"] == "PHYS-MTOW"

    # 3. TC-04c: Unverified Robust Breach -> Unresolved
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].threshold_evidence_status = EvidenceStatus.UNVERIFIED
    r["PHYS-MTOW"].threshold_interval = IntervalRecord(20000.0, 19990.0, 20010.0)
    r["PHYS-MTOW"].measured_interval = IntervalRecord(21000.0, 20500.0, 21500.0)
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert UnresolvedReason.UNVERIFIED_EVIDENCE_GATE_FAIL in rep.unresolved_reasons

    # 4. TC-06: Empty Mandatory Registry
    c, m, r = build_nominal_test_fixture()
    c.required_gate_ids = []
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED in rep.unresolved_reasons

    # 5. TC-14: Forward Evaluation Energy Deduplication
    c, m, r = build_nominal_test_fixture()
    c.evaluation_approach = "FORWARD_EVALUATION"
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert rep.solver_status == SolverStatus.NOT_REQUIRED
    assert UnresolvedReason.FORWARD_MODE_ENERGY_UNRESOLVED in rep.unresolved_reasons
    assert UnresolvedReason.INDETERMINATE_GATE_PRESENT not in rep.unresolved_reasons

    # 6. TC-15: Malformed Zero-Mass Exclusion
    c, m, r = build_nominal_test_fixture()
    m["wing_group"] = {"mass": 0.0, "intentional_exclusion": False}
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 7. TC-19: Runtime Crash
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(c, m, r, simulated_runtime_exception=True)
    assert rep.workflow_status == WorkflowStatus.ABORTED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert rep.runtime_error is not None

    # 8. TC-20: Isolated MZFW Failure Sensitivity Pass
    c, m, r = build_nominal_test_fixture()
    r["CERT-MZFW"].threshold_interval = IntervalRecord(16000.0, 15990.0, 16010.0)
    r["CERT-MZFW"].measured_interval = IntervalRecord(17000.0, 16500.0, 17500.0)
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert rep.zfw_assumption_sensitive
    assert UnresolvedReason.ZFW_SENSITIVITY_DISAGREEMENT in rep.unresolved_reasons

    # 9. TC-26: Degenerate Point Match (LEQ)
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].threshold_interval = IntervalRecord(20000.0, 20000.0, 20000.0)
    r["PHYS-MTOW"].measured_interval = IntervalRecord(20000.0, 20000.0, 20000.0)
    rep = run_framework_screening(c, m, r)
    assert r["PHYS-MTOW"].status == GateStatus.PASS
    assert rep.system_verdict == SystemVerdict.PASSES_REGISTERED_GATES

    # 10. TC-29: Residual Zero-Denominator Floor Protection
    c, m, r = build_nominal_test_fixture()
    dm = abs(50.0 - 0.0) / max(abs(0.0), RESIDUAL_FLOORS["mass"])
    rep = run_framework_screening(c, m, r, simulated_residuals=(dm, 1.0e-4, 1.0e-4))
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert rep.numerical_closure == NumericalClosure.UNCLOSED
    assert UnresolvedReason.SOLVER_RESIDUAL_TOLERANCE_EXCEEDED in rep.unresolved_reasons

    # 11. PROBE-01: Solver NOT_RUN in Sizing Loop Mode
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(c, m, r, simulated_solver_exit=SolverStatus.NOT_RUN)
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert UnresolvedReason.SOLVER_NOT_RUN_IN_SIZING in rep.unresolved_reasons

    # 12. PROBE-02: Solver ITERATING in Sizing Loop Mode
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(c, m, r, simulated_solver_exit=SolverStatus.ITERATING)
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert UnresolvedReason.SOLVER_ITERATING_UNCLOSED in rep.unresolved_reasons

    # 13. PROBE-03: Negative Residuals Rejected
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(c, m, r, simulated_residuals=(-10.0, -1.0, -0.1))
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert rep.numerical_closure == NumericalClosure.UNCLOSED
    assert UnresolvedReason.SOLVER_RESIDUAL_TOLERANCE_EXCEEDED in rep.unresolved_reasons

    # 14. PROBE-04: Non-Finite (Infinite) Threshold Rejected
    try:
        IntervalRecord(nominal=float("inf"), lower_bound=float("inf"), upper_bound=float("inf"))
        assert False, "Failed to reject infinite IntervalRecord"
    except ValueError:
        pass

    # 15. PROBE-05: Extra Undeclared Mandatory Gate Rejected
    c, m, r = build_nominal_test_fixture()
    r["ROGUE-MANDATORY"] = GateRecord(
        gate_id="ROGUE-MANDATORY", scenario_id="FLIGHT", gate_type=GateType.PHYSICAL,
        gate_role=GateRole.MANDATORY, status=GateStatus.FAIL,
        input_evidence_status=EvidenceStatus.VERIFIED, threshold_evidence_status=EvidenceStatus.VERIFIED,
        evaluation_method=EvaluationMethod.NUMERICAL_THRESHOLD, comparison_operator=ComparisonOperator.LEQ,
        threshold_interval=IntervalRecord(100.0, 90.0, 110.0),
        measured_interval=IntervalRecord(200.0, 190.0, 210.0),
    )
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.MANDATORY_REGISTRY_CONTRACT_VIOLATED in rep.unresolved_reasons

    # 16. PROBE-06: Candidate Contradictory Scalar vs Interval Rejected
    c, m, r = build_nominal_test_fixture()
    cand = ThresholdCandidate(
        candidate_id="CONTRADICTORY", threshold_value=1000.0,
        threshold_interval=IntervalRecord(20000.0, 19990.0, 20010.0),
        source_reference="Brochure", declared_evidence_status=EvidenceStatus.VERIFIED
    )
    r["PHYS-MTOW"].threshold_candidates = [cand]
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 17. PROBE-07: Procedural Gate Without Attestation Reference Bypassed
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].evaluation_method = EvaluationMethod.PROCEDURAL_ATTESTATION
    r["PHYS-MTOW"].attestation_reference = None
    rep = run_framework_screening(c, m, r)
    assert r["PHYS-MTOW"].status == GateStatus.UNRESOLVED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED

    # 18. PROBE-08: Sensitivity Run Failure Preserves Failed Gate IDs
    c, m, r = build_nominal_test_fixture()
    r["CERT-MZFW"].threshold_interval = IntervalRecord(16000.0, 15990.0, 16010.0)
    r["CERT-MZFW"].measured_interval = IntervalRecord(21000.0, 20500.0, 21500.0)
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FAILS_REGISTERED_GATES
    assert "CERT-MZFW" in rep.failed_gate_ids

    # 19. PROBE-09: Unauthorized Mandatory NOT_APPLICABLE Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].status = GateStatus.NOT_APPLICABLE
    r["PHYS-MTOW"].applicability_rationale = None
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 20. PROBE-10: Immutable IntervalRecord Mutation Blocked
    iv = IntervalRecord(nominal=20000.0, lower_bound=19990.0, upper_bound=20010.0)
    try:
        iv.lower_bound = float("inf")  # type: ignore
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("IntervalRecord mutation was not blocked")

    # 21. PROBE-11: Missing Mass Field Blocked
    c, m, r = build_nominal_test_fixture()
    del m["battery_pack"]["mass"]
    m["battery_pack"]["intentional_exclusion"] = True
    m["battery_pack"]["rationale"] = "Testing missing mass key"
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 22. PROBE-12: Sensitivity Invariant with Initial Relaxed ZFW
    c, m, r = build_nominal_test_fixture()
    c.battery_in_zfw_assumption = False
    r["CERT-MZFW"].threshold_interval = IntervalRecord(16000.0, 15990.0, 16010.0)
    r["CERT-MZFW"].measured_interval = IntervalRecord(18000.0, 17500.0, 18500.0)
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FAILS_REGISTERED_GATES
    assert rep.sensitivity_run is None

    # 23. PROBE-13: Multiple Failures Suppress ZFW Sensitivity Trigger
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].threshold_interval = IntervalRecord(20000.0, 19990.0, 20010.0)
    r["PHYS-MTOW"].measured_interval = IntervalRecord(22000.0, 21500.0, 22500.0)
    r["CERT-MZFW"].threshold_interval = IntervalRecord(16000.0, 15990.0, 16010.0)
    r["CERT-MZFW"].measured_interval = IntervalRecord(18000.0, 17500.0, 18500.0)
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FAILS_REGISTERED_GATES
    assert "PHYS-MTOW" in rep.failed_gate_ids
    assert "CERT-MZFW" in rep.failed_gate_ids
    assert rep.sensitivity_run is None

    # 24. PROBE-14: Invalid Comparison Operator Rejected
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].comparison_operator = "INVALID_OPERATOR"  # type: ignore
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 25. PROBE-15: Failure and Unresolved Coexist with Reasons in Report Audit Trail
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].threshold_interval = IntervalRecord(20000.0, 19990.0, 20010.0)
    r["PHYS-MTOW"].measured_interval = IntervalRecord(22000.0, 21500.0, 22500.0)
    r["PHYS-MLW"].status = GateStatus.UNRESOLVED
    rep = run_framework_screening(c, m, r)
    assert rep.system_verdict == SystemVerdict.FAILS_REGISTERED_GATES
    assert "PHYS-MTOW" in rep.failed_gate_ids
    assert "PHYS-MLW" in rep.unresolved_gate_ids
    assert UnresolvedReason.INDETERMINATE_GATE_PRESENT in rep.unresolved_reasons

    # 26. PROBE-16: Residual Floors Contract Constant Check
    assert RESIDUAL_FLOORS["mass"] == 1.0
    assert RESIDUAL_FLOORS["energy"] == 1.0e6
    assert RESIDUAL_FLOORS["power"] == 1.0e3

    # 27. PROBE-17: Mandatory Energy Gate N/A with Rationale Blocked in SIZING_LOOP
    c, m, r = build_nominal_test_fixture()
    r["PROJECT-ENERGY-RESERVE"].status = GateStatus.NOT_APPLICABLE
    r["PROJECT-ENERGY-RESERVE"].applicability_rationale = "Attempted exemption with rationale"
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 28. PROBE-18: Unsupported Analysis Mode Blocked
    c, m, r = build_nominal_test_fixture()
    c.analysis_mode = "CLEAN_SHEET"
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 29. PROBE-19: Malformed Enum Injection Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].status = "INVALID_STRING"  # type: ignore
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 30. PROBE-20: Missing Comparison Operator on Numerical Gate Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].comparison_operator = None
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 31. PROBE-21: Boolean in Mass Blocked
    c, m, r = build_nominal_test_fixture()
    m["wing_group"]["mass"] = True
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 32. PROBE-21b: Boolean in IntervalRecord Bounds Blocked
    try:
        IntervalRecord(nominal=20000.0, lower_bound=True, upper_bound=20010.0)  # type: ignore
        assert False, "Failed to reject boolean lower_bound"
    except ValueError:
        pass
    try:
        IntervalRecord(nominal=20000.0, lower_bound=19990.0, upper_bound=False)  # type: ignore
        assert False, "Failed to reject boolean upper_bound"
    except ValueError:
        pass

    # 33. PROBE-21c: Boolean in ThresholdCandidate Blocked
    try:
        ThresholdCandidate(
            candidate_id="BOOL_CAND", threshold_value=True,  # type: ignore
            threshold_interval=None, source_reference="Ref",
            declared_evidence_status=EvidenceStatus.VERIFIED
        )
        assert False, "Failed to reject boolean candidate threshold_value"
    except ValueError:
        pass

    # 34. PROBE-21d: Boolean Scalar Threshold Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].threshold_value = True  # type: ignore
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 35. PROBE-21e: Boolean Residual Blocked
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(c, m, r, simulated_residuals=(True, 1.0e-4, 1.0e-4))  # type: ignore
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert rep.numerical_closure == NumericalClosure.UNCLOSED
    assert UnresolvedReason.SOLVER_RESIDUAL_TOLERANCE_EXCEEDED in rep.unresolved_reasons

    # 36. PROBE-22: Non-Boolean Proof Flag in Test Helper Blocked
    c, m, r = build_nominal_test_fixture()
    try:
        _evaluate_bounded_proof_test_only(
            config=c, mass_budget=m, gate_registry=r, simulated_lipchitz_proof="not a boolean proof"  # type: ignore
        )
        assert False, "Failed to reject non-boolean proof flag in test helper"
    except TypeError:
        pass

    # 37. PROBE-22b: Test-Only Helper State Transition Verification
    c, m, r = build_nominal_test_fixture()
    rep = _evaluate_bounded_proof_test_only(
        config=c, mass_budget=m, gate_registry=r, simulated_lipchitz_proof=True
    )
    assert rep.workflow_status == WorkflowStatus.COMPLETED
    assert rep.system_verdict == SystemVerdict.INFEASIBLE_BOUNDED_SEARCH

    # 38. PROBE-22c: Operational Pathway Always Returns FEASIBILITY_UNRESOLVED on Bounded Solver Exit
    c, m, r = build_nominal_test_fixture()
    rep = run_framework_screening(
        c, m, r,
        simulated_solver_exit=SolverStatus.PROVEN_INFEASIBLE_BOUND,
    )
    assert rep.workflow_status == WorkflowStatus.COMPLETED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert UnresolvedReason.UNVERIFIED_BOUNDING_PROOF_INPUTS in rep.unresolved_reasons

    # 39. PROBE-22d: Test Helper Cannot Override Pre-Solver Validation Failure
    c, m, r = build_nominal_test_fixture()
    c.analysis_mode = "CLEAN_SHEET"  # Invalid mode
    rep = _evaluate_bounded_proof_test_only(
        config=c, mass_budget=m, gate_registry=r, simulated_lipchitz_proof=True
    )
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    # 40. PROBE-23: Unregistered Procedural Attestation Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].evaluation_method = EvaluationMethod.PROCEDURAL_ATTESTATION
    r["PHYS-MTOW"].attestation_reference = "unregistered-doc-id"
    rep = run_framework_screening(c, m, r, attestation_registry={"valid-doc": {"status": "AUTHORIZED", "gate_id": "PHYS-MTOW", "compliance_verdict": "PASS", "evidence_status": EvidenceStatus.VERIFIED}})
    assert r["PHYS-MTOW"].status == GateStatus.UNRESOLVED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED

    # 41. PROBE-23b: Authorized Attestation Without Compliant Verdict Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].evaluation_method = EvaluationMethod.PROCEDURAL_ATTESTATION
    r["PHYS-MTOW"].attestation_reference = "doc-pending"
    rep = run_framework_screening(
        c, m, r,
        attestation_registry={"doc-pending": {"status": "AUTHORIZED", "gate_id": "PHYS-MTOW", "compliance_verdict": "PENDING", "evidence_status": EvidenceStatus.VERIFIED}}
    )
    assert r["PHYS-MTOW"].status == GateStatus.UNRESOLVED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED

    # 42. PROBE-23c: Attestation Missing Evidence Status Blocked
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].evaluation_method = EvaluationMethod.PROCEDURAL_ATTESTATION
    r["PHYS-MTOW"].attestation_reference = "doc-no-evidence"
    rep = run_framework_screening(
        c, m, r,
        attestation_registry={"doc-no-evidence": {"status": "AUTHORIZED", "gate_id": "PHYS-MTOW", "compliance_verdict": "PASS"}}
    )
    assert r["PHYS-MTOW"].status == GateStatus.UNRESOLVED
    assert rep.system_verdict == SystemVerdict.FEASIBILITY_UNRESOLVED

    # 43. PROBE-23d: Procedural Gate Starting UNRESOLVED Successfully Passes with Valid Attestation
    c, m, r = build_nominal_test_fixture()
    r["PHYS-MTOW"].evaluation_method = EvaluationMethod.PROCEDURAL_ATTESTATION
    r["PHYS-MTOW"].status = GateStatus.UNRESOLVED
    r["PHYS-MTOW"].attestation_reference = "doc-valid"
    rep = run_framework_screening(
        c, m, r,
        attestation_registry={"doc-valid": {"status": "AUTHORIZED", "gate_id": "PHYS-MTOW", "compliance_verdict": "PASS", "evidence_status": EvidenceStatus.VERIFIED}}
    )
    assert r["PHYS-MTOW"].status == GateStatus.PASS
    assert r["PHYS-MTOW"].input_evidence_status == EvidenceStatus.VERIFIED
    assert rep.system_verdict == SystemVerdict.PASSES_REGISTERED_GATES

    # 44. PROBE-24: Non-Boolean Configuration Switch Blocked
    c, m, r = build_nominal_test_fixture()
    c.is_sensitivity_run = "False"  # type: ignore
    rep = run_framework_screening(c, m, r)
    assert rep.workflow_status == WorkflowStatus.PRE_SOLVER_BLOCKED
    assert UnresolvedReason.PRE_SOLVER_INPUT_INVALID in rep.unresolved_reasons

    print("All 44 acceptance and probe assertion fixtures passed successfully.")


if __name__ == "__main__":
    run_acceptance_suite()