"""
Aircraft Design Framework — Input-Driven All-Electric Design Evaluator
Module: DesignEvaluator.py
Designation: Generic Evaluation Engine for All-Electric Aircraft Configurations
Scaffold Status: Screening Scaffold Frozen (v0.3.5 / v0.3.6 FINAL - Untouched)
Version: v1.3-HARDENED (Type-Safe, Strict Units Contract & Pre-Evaluation Stall Guard)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Set


# =====================================================================
# 1. 核心枚举与单位白名单规范
# =====================================================================

class DataStatus(Enum):
    SOURCED = "SOURCED"        # 提交者声明来源于官方 TCDS、手册或测试报告 (程序不作真伪背书)
    ESTIMATED = "ESTIMATED"    # 基于工程经验公式、统计回归或部件级估算
    ASSUMED = "ASSUMED"        # 暂定工程假设、任务设想或技术指标预测


class EvaluationStatus(Enum):
    FEASIBLE_UNDER_ASSUMPTIONS = "FEASIBLE_UNDER_ASSUMPTIONS"
    INFEASIBLE_UNDER_ASSUMPTIONS = "INFEASIBLE_UNDER_ASSUMPTIONS"
    UNRESOLVED = "UNRESOLVED"
    INPUT_INVALID = "INPUT_INVALID"


class ConstraintCode(Enum):
    MTOW_LIMIT = "MTOW_LIMIT"
    CL_MAX_STALL = "CL_MAX_STALL"
    MOTOR_CONTINUOUS_POWER = "MOTOR_CONTINUOUS_POWER"
    MOTOR_PEAK_POWER = "MOTOR_PEAK_POWER"
    BATTERY_CONTINUOUS_POWER = "BATTERY_CONTINUOUS_POWER"
    BATTERY_PEAK_POWER = "BATTERY_PEAK_POWER"
    MISSION_ENERGY = "MISSION_ENERGY"
    RESERVE_LOITER_ENERGY = "RESERVE_LOITER_ENERGY"


@dataclass(frozen=True)
class InputParam:
    value: Any
    units: str
    status: DataStatus
    source: str = ""
    description: str = ""


# 规范期望单位白名单映射表
CANONICAL_EXPECTED_UNITS: Dict[str, Set[str]] = {
    "base_mass_kg": {"kg"},
    "payload_kg": {"kg"},
    "mtow_kg": {"kg"},
    "wing_area_m2": {"m^2", "m2"},
    "aspect_ratio": {"dimensionless", ""},
    "cd0": {"dimensionless", ""},
    "oswald_e": {"dimensionless", ""},
    "cruise_altitude_m": {"m"},
    "air_density_kg_pm3": {"kg/m^3", "kg/m3"},
    "cruise_speed_mps": {"m/s"},
    "cl_max_clean": {"dimensionless", ""},
    "battery_mass_kg": {"kg"},
    "pack_specific_energy_wh_kg": {"Wh/kg"},
    "usable_dod": {"dimensionless", ""},
    "continuous_discharge_power_limit_w": {"W"},
    "peak_discharge_power_limit_w": {"W"},
    "motor_mass_kg": {"kg"},
    "motor_continuous_rating_w": {"W"},
    "motor_peak_rating_w": {"W"},
    "motor_efficiency": {"dimensionless", ""},
    "propulsive_efficiency": {"dimensionless", ""},
    "inverter_efficiency": {"dimensionless", ""},
    "additional_powertrain_mass_kg": {"kg"},
    "target_range_nm": {"nm"},
    "reserve_loiter_time_s": {"s"},
    "loiter_power_factor": {"dimensionless", ""},
}

# 简化的模型范围与主要未建模效应声明
MODEL_UNMODELED_EFFECTS = [
    "Ground roll, rotation, and dynamic climb-out energy consumption",
    "High-lift device (flaps/slats) low-speed field stall speeds and approach margins",
    "Thermal Management System (TMS) heat dissipation and continuous cooling power penalty",
    "Aeroelastic structural wing twist/bending and high-speed compressibility drag rise",
    "Longitudinal and lateral-directional CG travel tracking across full mission profile",
    "Descent glide profile deceleration and battery charge-recovery dynamics",
]


# =====================================================================
# 2. 候选设计输入数据集 (DesignInput)
# =====================================================================

@dataclass
class DesignInput:
    design_name: str

    # 1. 飞机平台基线与载荷
    base_mass_kg: InputParam                 # 明确定义: 扣除原发动机及燃油系统后的机体空重
    payload_kg: InputParam                   # 商载质量
    mtow_kg: InputParam                      # 最大允许起飞总重

    # 2. 气动与大气参数
    wing_area_m2: InputParam
    aspect_ratio: InputParam
    cd0: InputParam
    oswald_e: InputParam
    cruise_altitude_m: InputParam
    air_density_kg_pm3: InputParam
    cruise_speed_mps: InputParam

    # 3. 电池系统
    battery_mass_kg: InputParam
    pack_specific_energy_wh_kg: InputParam
    usable_dod: InputParam
    continuous_discharge_power_limit_w: InputParam
    peak_discharge_power_limit_w: InputParam

    # 4. 电机与转换系统
    motor_mass_kg: InputParam
    motor_continuous_rating_w: InputParam
    motor_peak_rating_w: InputParam
    motor_efficiency: InputParam
    propulsive_efficiency: InputParam

    # 5. 动态气动失速上限 (若为 None 则失速检查标记为 UNRESOLVED)
    cl_max_clean: Optional[InputParam] = None

    # 6. 辅助动力总成与任务默认参数
    inverter_efficiency: InputParam = field(
        default_factory=lambda: InputParam(1.0, "dimensionless", DataStatus.ASSUMED, "Baseline", "Idealized inverter")
    )
    additional_powertrain_mass_kg: InputParam = field(
        default_factory=lambda: InputParam(0.0, "kg", DataStatus.ASSUMED, "Baseline", "Wiring and cooling overhead")
    )
    target_range_nm: InputParam = field(
        default_factory=lambda: InputParam(500.0, "nm", DataStatus.ASSUMED, "Baseline", "Mission target distance")
    )
    reserve_loiter_time_s: InputParam = field(
        default_factory=lambda: InputParam(2700.0, "s", DataStatus.ASSUMED, "Project Policy", "45-minute holding reserve")
    )
    loiter_power_factor: InputParam = field(
        default_factory=lambda: InputParam(0.60, "dimensionless", DataStatus.ASSUMED, "Polar", "Loiter power fraction")
    )


# =====================================================================
# 3. 评估报告与约束细节
# =====================================================================

@dataclass
class ConstraintViolation:
    code: ConstraintCode
    description: str
    required_value: float
    actual_capacity: float
    units: str
    margin: float  # actual_capacity - required_value (负数代表违约超标)


@dataclass
class EvaluationReport:
    design_name: str
    verdict: EvaluationStatus
    summary_message: str

    # 质量分解 (基于候选机真实输入)
    actual_takeoff_mass_kg: float
    mtow_limit_kg: float
    available_mass_margin_kg: float

    # 巡航工作点 (在实际总重下计算)
    cl_cruise: float
    cd_cruise: float
    lift_to_drag: float
    drag_n: float
    thrust_power_w: float
    shaft_power_w: float
    electric_power_w: float
    peak_electric_power_demand_w: float

    # 能量与电池能力
    usable_battery_energy_j: float
    cruise_energy_j: float
    loiter_reserve_energy_j: float
    total_mission_energy_j: float

    # 航程解耦审计
    energy_limited_range_nm: Optional[float]
    operationally_compliant_range_nm: Optional[float]
    zero_reserve_theoretical_range_nm: float
    range_assessment_note: str

    # 约束、未建模效应与假设审计
    failed_constraints: List[ConstraintViolation] = field(default_factory=list)
    unresolved_assumptions: List[str] = field(default_factory=list)
    unmodeled_effects: List[str] = field(default_factory=lambda: list(MODEL_UNMODELED_EFFECTS))
    input_validation_errors: List[str] = field(default_factory=list)


# =====================================================================
# 4. 评估核心引擎 (MissionEvaluator)
# =====================================================================

class MissionEvaluator:
    """
    通用输入驱动全电动飞机设计评估器
    """
    GRAVITY = 9.80665

    @classmethod
    def _validate_numeric_param(cls, p: InputParam, name: str, v_min: float, v_max: float) -> Optional[str]:
        val = p.value
        if type(val) is bool or not isinstance(val, (int, float)):
            return f"Parameter '{name}' value must be numeric float/int, got {type(val).__name__} ({val})"
        if not math.isfinite(val):
            return f"Parameter '{name}' value must be finite, got {val}"
        if not (v_min <= val <= v_max):
            return f"Parameter '{name}' = {val} {p.units} is outside physical boundary [{v_min}, {v_max}]"
        return None

    @classmethod
    def evaluate(cls, design: Any) -> EvaluationReport:
        # -------------------------------------------------------------
        # 步骤 0: 顶层对象类型防护 (Top-Level Object Guard)
        # -------------------------------------------------------------
        if not isinstance(design, DesignInput):
            return EvaluationReport(
                design_name="INVALID_OBJECT",
                verdict=EvaluationStatus.INPUT_INVALID,
                summary_message=f"Input must be an instance of DesignInput, got {type(design).__name__}.",
                actual_takeoff_mass_kg=0.0, mtow_limit_kg=0.0, available_mass_margin_kg=0.0,
                cl_cruise=0.0, cd_cruise=0.0, lift_to_drag=0.0, drag_n=0.0,
                thrust_power_w=0.0, shaft_power_w=0.0, electric_power_w=0.0, peak_electric_power_demand_w=0.0,
                usable_battery_energy_j=0.0, cruise_energy_j=0.0, loiter_reserve_energy_j=0.0, total_mission_energy_j=0.0,
                energy_limited_range_nm=None, operationally_compliant_range_nm=None, zero_reserve_theoretical_range_nm=0.0,
                range_assessment_note="Evaluation aborted due to invalid top-level object type.",
                input_validation_errors=[f"Expected DesignInput instance, received {type(design).__name__}."],
            )

        # -------------------------------------------------------------
        # 步骤 1: 严格模式、溯源与单位白名单校验
        # -------------------------------------------------------------
        schema_errors: List[str] = []

        if not isinstance(design.design_name, str) or not design.design_name.strip():
            schema_errors.append("Field 'design_name' must be a non-empty string.")

        for f_name, f_val in vars(design).items():
            if f_name == "design_name":
                continue
            if f_name == "cl_max_clean" and f_val is None:
                continue

            if not isinstance(f_val, InputParam):
                schema_errors.append(f"Field '{f_name}' must be an instance of InputParam, got {type(f_val).__name__}.")
                continue

            if not isinstance(f_val.status, DataStatus):
                schema_errors.append(f"Field '{f_name}' status must be a valid DataStatus enum, got {f_val.status}.")

            if not isinstance(f_val.units, str) or not f_val.units.strip():
                schema_errors.append(f"Field '{f_name}' must declare a non-empty 'units' string.")
            elif f_name in CANONICAL_EXPECTED_UNITS:
                expected_set = CANONICAL_EXPECTED_UNITS[f_name]
                if f_val.units not in expected_set:
                    schema_errors.append(
                        f"Field '{f_name}' has incompatible units '{f_val.units}'. Expected one of {sorted(list(expected_set))}."
                    )

            if f_val.status == DataStatus.SOURCED:
                if not isinstance(f_val.source, str) or not f_val.source.strip():
                    schema_errors.append(f"Field '{f_name}' is declared SOURCED but lacks a valid source reference citation.")

        if schema_errors:
            return EvaluationReport(
                design_name=design.design_name,
                verdict=EvaluationStatus.INPUT_INVALID,
                summary_message="Schema, provenance, or units validation failed. Input rejected.",
                actual_takeoff_mass_kg=0.0, mtow_limit_kg=0.0, available_mass_margin_kg=0.0,
                cl_cruise=0.0, cd_cruise=0.0, lift_to_drag=0.0, drag_n=0.0,
                thrust_power_w=0.0, shaft_power_w=0.0, electric_power_w=0.0, peak_electric_power_demand_w=0.0,
                usable_battery_energy_j=0.0, cruise_energy_j=0.0, loiter_reserve_energy_j=0.0, total_mission_energy_j=0.0,
                energy_limited_range_nm=None, operationally_compliant_range_nm=None, zero_reserve_theoretical_range_nm=0.0,
                range_assessment_note="Evaluation aborted due to schema/provenance/unit violations.",
                input_validation_errors=schema_errors,
            )

        # -------------------------------------------------------------
        # 步骤 2: 数值范围与物理边界校验 (包含 cl_max_clean 前置校验)
        # -------------------------------------------------------------
        numeric_checks = [
            (design.base_mass_kg, "base_mass_kg", 100.0, 500000.0),
            (design.payload_kg, "payload_kg", 0.0, 200000.0),
            (design.mtow_kg, "mtow_kg", 200.0, 1000000.0),
            (design.wing_area_m2, "wing_area_m2", 1.0, 2000.0),
            (design.aspect_ratio, "aspect_ratio", 1.0, 40.0),
            (design.cd0, "cd0", 0.001, 0.30),
            (design.oswald_e, "oswald_e", 0.1, 1.0),
            (design.cruise_altitude_m, "cruise_altitude_m", 0.0, 25000.0),
            (design.air_density_kg_pm3, "air_density_kg_pm3", 0.01, 2.0),
            (design.cruise_speed_mps, "cruise_speed_mps", 5.0, 500.0),
            (design.battery_mass_kg, "battery_mass_kg", 0.0, 500000.0),
            (design.pack_specific_energy_wh_kg, "pack_specific_energy_wh_kg", 1.0, 5000.0),
            (design.usable_dod, "usable_dod", 0.05, 1.0),
            (design.continuous_discharge_power_limit_w, "continuous_discharge_power_limit_w", 0.0, 1.0e9),
            (design.peak_discharge_power_limit_w, "peak_discharge_power_limit_w", 0.0, 1.0e9),
            (design.motor_mass_kg, "motor_mass_kg", 0.0, 100000.0),
            (design.motor_continuous_rating_w, "motor_continuous_rating_w", 0.0, 1.0e9),
            (design.motor_peak_rating_w, "motor_peak_rating_w", 0.0, 1.0e9),
            (design.motor_efficiency, "motor_efficiency", 0.1, 1.0),
            (design.propulsive_efficiency, "propulsive_efficiency", 0.1, 1.0),
            (design.inverter_efficiency, "inverter_efficiency", 0.1, 1.0),
            (design.additional_powertrain_mass_kg, "additional_powertrain_mass_kg", 0.0, 100000.0),
            (design.target_range_nm, "target_range_nm", 0.0, 20000.0),
            (design.reserve_loiter_time_s, "reserve_loiter_time_s", 0.0, 86400.0),
            (design.loiter_power_factor, "loiter_power_factor", 0.05, 2.0),
        ]

        val_errors: List[str] = []
        for p_obj, p_name, p_min, p_max in numeric_checks:
            err = cls._validate_numeric_param(p_obj, p_name, p_min, p_max)
            if err:
                val_errors.append(err)

        # 针对可选的 cl_max_clean 进行严格前置数值范围检验 (防穿透)
        if design.cl_max_clean is not None and design.cl_max_clean.value is not None:
            cl_err = cls._validate_numeric_param(design.cl_max_clean, "cl_max_clean", 0.5, 3.0)
            if cl_err:
                val_errors.append(cl_err)

        if val_errors:
            mtow_fallback = (
                float(design.mtow_kg.value)
                if isinstance(design.mtow_kg.value, (int, float)) and type(design.mtow_kg.value) is not bool
                else 0.0
            )
            return EvaluationReport(
                design_name=design.design_name,
                verdict=EvaluationStatus.INPUT_INVALID,
                summary_message="Numeric parameter validation failed.",
                actual_takeoff_mass_kg=0.0, mtow_limit_kg=mtow_fallback, available_mass_margin_kg=0.0,
                cl_cruise=0.0, cd_cruise=0.0, lift_to_drag=0.0, drag_n=0.0,
                thrust_power_w=0.0, shaft_power_w=0.0, electric_power_w=0.0, peak_electric_power_demand_w=0.0,
                usable_battery_energy_j=0.0, cruise_energy_j=0.0, loiter_reserve_energy_j=0.0, total_mission_energy_j=0.0,
                energy_limited_range_nm=None, operationally_compliant_range_nm=None, zero_reserve_theoretical_range_nm=0.0,
                range_assessment_note="Evaluation aborted due to out-of-bounds numeric inputs.",
                input_validation_errors=val_errors,
            )

        # -------------------------------------------------------------
        # 步骤 3: 真实物理质量核算
        # -------------------------------------------------------------
        base_m = float(design.base_mass_kg.value)
        pld_m = float(design.payload_kg.value)
        bat_m = float(design.battery_mass_kg.value)
        mot_m = float(design.motor_mass_kg.value)
        ext_m = float(design.additional_powertrain_mass_kg.value)
        mtow = float(design.mtow_kg.value)

        actual_gross_mass = base_m + pld_m + bat_m + mot_m + ext_m
        mass_margin = mtow - actual_gross_mass

        unresolved_notes: List[str] = []
        for f_name, p_obj in vars(design).items():
            if isinstance(p_obj, InputParam) and p_obj.status == DataStatus.ASSUMED:
                unresolved_notes.append(f"{f_name}: ASSUMED ({p_obj.description or p_obj.source})")

        # -------------------------------------------------------------
        # 步骤 4: 实际总重下的气动力与功率工况
        # -------------------------------------------------------------
        s_area = float(design.wing_area_m2.value)
        ar = float(design.aspect_ratio.value)
        cd0 = float(design.cd0.value)
        oswald_e = float(design.oswald_e.value)
        rho = float(design.air_density_kg_pm3.value)
        v_cruise = float(design.cruise_speed_mps.value)

        k_ind = 1.0 / (math.pi * oswald_e * ar)
        weight_n = actual_gross_mass * cls.GRAVITY
        q_inf = 0.5 * rho * (v_cruise ** 2)

        cl = weight_n / (q_inf * s_area)
        cd = cd0 + k_ind * (cl ** 2)
        drag_n = cd * q_inf * s_area
        ld_ratio = cl / cd if cd > 0 else 0.0

        eta_prop = float(design.propulsive_efficiency.value)
        eta_motor = float(design.motor_efficiency.value)
        eta_inv = float(design.inverter_efficiency.value)

        p_thrust = drag_n * v_cruise
        p_shaft = p_thrust / eta_prop
        p_electric = p_shaft / (eta_motor * eta_inv)
        p_peak_electric_demand = 2.0 * p_electric

        # -------------------------------------------------------------
        # 步骤 5: 能量积分与电池能力
        # -------------------------------------------------------------
        dist_m = float(design.target_range_nm.value) * 1852.0
        t_cruise = dist_m / v_cruise if v_cruise > 0 else 0.0
        e_cruise = p_electric * t_cruise

        t_loiter = float(design.reserve_loiter_time_s.value)
        loiter_fac = float(design.loiter_power_factor.value)
        p_loiter = loiter_fac * p_electric
        e_loiter = p_loiter * t_loiter

        e_mission_total = e_cruise + e_loiter

        e_pack_wh_kg = float(design.pack_specific_energy_wh_kg.value)
        dod = float(design.usable_dod.value)
        usable_pack_density_j_kg = e_pack_wh_kg * 3600.0 * dod
        usable_battery_energy = bat_m * usable_pack_density_j_kg

        # -------------------------------------------------------------
        # 步骤 6: 约束独立审计 (包含动态 CL_max)
        # -------------------------------------------------------------
        violations: List[ConstraintViolation] = []

        # 约束 1: MTOW 质量限制
        if actual_gross_mass > mtow:
            violations.append(ConstraintViolation(
                code=ConstraintCode.MTOW_LIMIT,
                description="Actual gross takeoff mass exceeds MTOW limit",
                required_value=mtow, actual_capacity=actual_gross_mass, units="kg", margin=mass_margin,
            ))

        # 约束 2: 动态失速迎角限制 (巡航点气动迎角)
        stall_unresolved = False
        if design.cl_max_clean is None or design.cl_max_clean.value is None:
            stall_unresolved = True
            unresolved_notes.append("cl_max_clean: NOT_PROVIDED (Clean cruise stall boundary CL_max cannot be verified)")
        else:
            cl_limit = float(design.cl_max_clean.value)
            if cl > cl_limit:
                violations.append(ConstraintViolation(
                    code=ConstraintCode.CL_MAX_STALL,
                    description=f"Required cruise CL ({cl:.3f}) exceeds clean stall limit CL_max ({cl_limit:.3f})",
                    required_value=cl_limit, actual_capacity=cl, units="dimensionless", margin=cl_limit - cl,
                ))

        # 约束 3: 电机持续轴功率
        mot_cont_w = float(design.motor_continuous_rating_w.value)
        if mot_cont_w < p_shaft:
            violations.append(ConstraintViolation(
                code=ConstraintCode.MOTOR_CONTINUOUS_POWER,
                description="Installed motor continuous shaft power rating is less than cruise shaft power demand",
                required_value=p_shaft, actual_capacity=mot_cont_w, units="W", margin=mot_cont_w - p_shaft,
            ))

        # 约束 4: 电机峰值轴功率
        mot_peak_w = float(design.motor_peak_rating_w.value)
        p_peak_shaft_demand = 2.0 * p_shaft
        if mot_peak_w < p_peak_shaft_demand:
            violations.append(ConstraintViolation(
                code=ConstraintCode.MOTOR_PEAK_POWER,
                description="Installed motor peak power rating is less than transient demand",
                required_value=p_peak_shaft_demand, actual_capacity=mot_peak_w, units="W", margin=mot_peak_w - p_peak_shaft_demand,
            ))

        # 约束 5: 电池持续放电功率
        bat_cont_w = float(design.continuous_discharge_power_limit_w.value)
        if bat_cont_w < p_electric:
            violations.append(ConstraintViolation(
                code=ConstraintCode.BATTERY_CONTINUOUS_POWER,
                description="Battery continuous discharge power limit is less than cruise electric power draw",
                required_value=p_electric, actual_capacity=bat_cont_w, units="W", margin=bat_cont_w - p_electric,
            ))

        # 约束 6: 电池峰值放电功率
        bat_peak_w = float(design.peak_discharge_power_limit_w.value)
        if bat_peak_w < p_peak_electric_demand:
            violations.append(ConstraintViolation(
                code=ConstraintCode.BATTERY_PEAK_POWER,
                description="Battery peak discharge power limit is less than transient electric demand",
                required_value=p_peak_electric_demand, actual_capacity=bat_peak_w, units="W", margin=bat_peak_w - p_peak_electric_demand,
            ))

        # 约束 7: 任务总电能
        if usable_battery_energy < e_mission_total:
            violations.append(ConstraintViolation(
                code=ConstraintCode.MISSION_ENERGY,
                description="Usable battery energy cannot cover total mission (cruise + reserve) demand",
                required_value=e_mission_total, actual_capacity=usable_battery_energy, units="J", margin=usable_battery_energy - e_mission_total,
            ))

        # 约束 8: 备用盘旋电能
        if usable_battery_energy < e_loiter:
            violations.append(ConstraintViolation(
                code=ConstraintCode.RESERVE_LOITER_ENERGY,
                description="Total usable battery energy is insufficient to sustain standalone reserve loiter",
                required_value=e_loiter, actual_capacity=usable_battery_energy, units="J", margin=usable_battery_energy - e_loiter,
            ))

        # -------------------------------------------------------------
        # 步骤 7: 航程解耦审计 (能量极限航程 vs 全约束合规航程)
        # -------------------------------------------------------------
        zero_res_range_nm = ((usable_battery_energy * v_cruise) / p_electric / 1852.0) if p_electric > 0 else 0.0

        if usable_battery_energy < e_loiter:
            energy_limited_range_nm = None
        else:
            net_energy_m = ((usable_battery_energy - e_loiter) * v_cruise) / p_electric
            energy_limited_range_nm = net_energy_m / 1852.0

        if violations:
            operationally_compliant_range_nm = None
            codes_str = ", ".join(v.code.value for v in violations)
            range_note = f"Operationally compliant range is None (Candidate violates {len(violations)} constraint(s): [{codes_str}])"
        elif energy_limited_range_nm is None:
            operationally_compliant_range_nm = None
            range_note = "NO_RESERVE_COMPLIANT_MISSION (Available battery energy is insufficient to cover 45-min reserve)"
        else:
            operationally_compliant_range_nm = energy_limited_range_nm
            range_note = f"Operationally compliant range: {operationally_compliant_range_nm:.1f} nm under constant-speed cruise model"

        # -------------------------------------------------------------
        # 步骤 8: 状态裁定
        # -------------------------------------------------------------
        if violations:
            verdict = EvaluationStatus.INFEASIBLE_UNDER_ASSUMPTIONS
            summary = f"Candidate design violated {len(violations)} constraint(s): [{', '.join(v.code.value for v in violations)}]."
        elif stall_unresolved:
            verdict = EvaluationStatus.UNRESOLVED
            summary = "All evaluated physical constraints passed, but clean stall boundary (cl_max_clean) is unverified."
        else:
            verdict = EvaluationStatus.FEASIBLE_UNDER_ASSUMPTIONS
            summary = "All modeled engineering, aerodynamic, and operational constraints passed under stated assumptions."

        return EvaluationReport(
            design_name=design.design_name,
            verdict=verdict,
            summary_message=summary,
            actual_takeoff_mass_kg=actual_gross_mass,
            mtow_limit_kg=mtow,
            available_mass_margin_kg=mass_margin,
            cl_cruise=cl, cd_cruise=cd, lift_to_drag=ld_ratio, drag_n=drag_n,
            thrust_power_w=p_thrust, shaft_power_w=p_shaft, electric_power_w=p_electric,
            peak_electric_power_demand_w=p_peak_electric_demand,
            usable_battery_energy_j=usable_battery_energy,
            cruise_energy_j=e_cruise,
            loiter_reserve_energy_j=e_loiter,
            total_mission_energy_j=e_mission_total,
            energy_limited_range_nm=energy_limited_range_nm,
            operationally_compliant_range_nm=operationally_compliant_range_nm,
            zero_reserve_theoretical_range_nm=zero_res_range_nm,
            range_assessment_note=range_note,
            failed_constraints=violations,
            unresolved_assumptions=unresolved_notes,
        )


# =====================================================================
# 5. 格式化报告打印器
# =====================================================================

def print_evaluation_report(rep: EvaluationReport):
    print("=" * 92)
    print(f"       AIRCRAFT DESIGN EVALUATION REPORT: {rep.design_name}")
    print("=" * 92)
    print(f"  VERDICT         : 【 {rep.verdict.value} 】")
    print(f"  SUMMARY         : {rep.summary_message}")
    print("  PROVENANCE NOTE : 'SOURCED' indicates the submitter cited a source document;")
    print("                    the evaluator does NOT independently audit or certify original sources.")
    print("-" * 92)
    print(f"[1. 实际质量预算 (Actual Mass Accounting)]")
    print(f"  - 实际起飞总重 (Actual TOW)  : {rep.actual_takeoff_mass_kg:,.1f} kg")
    print(f"  - 结构上限 (MTOW Limit)      : {rep.mtow_limit_kg:,.1f} kg")
    print(f"  - 质量裕度 (Mass Margin)     : {rep.available_mass_margin_kg:+,.1f} kg ({'PASS' if rep.available_mass_margin_kg >= 0 else 'FAIL: EXCEEDS MTOW'})")

    print(f"\n[2. 气动力与推进工况 (Calculated at Actual Mass)]")
    print(f"  - 升力系数 (C_L)             : {rep.cl_cruise:.4f}")
    print(f"  - 阻力系数 (C_D)             : {rep.cd_cruise:.4f} (L/D: {rep.lift_to_drag:.2f})")
    print(f"  - 气动阻力 (Drag)            : {rep.drag_n / 1000.0:.2f} kN")
    print(f"  - 机械轴功率 (P_shaft)       : {rep.shaft_power_w / 1e6:.3f} MW")
    print(f"  - 电端巡航需求 (P_electric)  : {rep.electric_power_w / 1e6:.3f} MW")
    print(f"  - 电端峰值需求 (P_peak)      : {rep.peak_electric_power_demand_w / 1e6:.3f} MW")

    print(f"\n[3. 能量收支与储能能力]")
    print(f"  - 可用电池总能量 (Pack E)    : {rep.usable_battery_energy_j / 1e6:,.1f} MJ ({rep.usable_battery_energy_j / 3.6e6:,.1f} kWh)")
    print(f"  - 目标航段巡航电能           : {rep.cruise_energy_j / 1e6:,.1f} MJ ({rep.cruise_energy_j / 3.6e6:,.1f} kWh)")
    print(f"  - 备用盘旋电能需求           : {rep.loiter_reserve_energy_j / 1e6:,.1f} MJ ({rep.loiter_reserve_energy_j / 3.6e6:,.1f} kWh)")
    print(f"  - 任务总需求电能             : {rep.total_mission_energy_j / 1e6:,.1f} MJ ({rep.total_mission_energy_j / 3.6e6:,.1f} kWh)")

    print(f"\n[4. 航程解耦审计 (Decoupled Range Diagnostics)]")
    print(f"  - 纯能量极限航程 (Energy-Limited)    : {f'{rep.energy_limited_range_nm:.1f} nm' if rep.energy_limited_range_nm is not None else 'NO_RESERVE_COMPLIANT_MISSION'}")
    print(f"  - 全约束合规航程 (Operationally Compliant): {f'{rep.operationally_compliant_range_nm:.1f} nm' if rep.operationally_compliant_range_nm is not None else 'None (Non-Compliant)'}")
    print(f"  - 理论零备用极限放电航程             : {rep.zero_reserve_theoretical_range_nm:.1f} nm")
    print(f"  - 航程诊断详情                       : {rep.range_assessment_note}")

    if rep.failed_constraints:
        print(f"\n[5. 违规约束清单 (Failed Constraints: {len(rep.failed_constraints)})]")
        for idx, f in enumerate(rep.failed_constraints, 1):
            print(f"  {idx}. [{f.code.value}] {f.description}")
            print(f"     需求门槛: {f.required_value:,.2f} {f.units} | 实际能力: {f.actual_capacity:,.2f} {f.units} | 裕度: {f.margin:,.2f} {f.units}")

    if rep.unresolved_assumptions:
        print(f"\n[6. 暂定假设与待解析项 (Assumed & Unresolved Items)]")
        for idx, a in enumerate(rep.unresolved_assumptions, 1):
            print(f"  - {a}")

    print(f"\n[7. 适用边界与主要未建模物理效应声明 (Model Scope & Unmodeled Effects)]")
    for idx, e in enumerate(rep.unmodeled_effects, 1):
        print(f"  {idx}. {e}")
    print("=" * 92)


# =====================================================================
# 6. 自动化回归测试套件 (12 项覆盖)
# =====================================================================

def build_baseline_candidate() -> DesignInput:
    """构建 EMB-135 500 nm, 4198 kg payload, 300 Wh/kg 团队基线配置"""
    return DesignInput(
        design_name="EMB-135_Baseline_Retrofit_Candidate",
        base_mass_kg=InputParam(11000.0, "kg", DataStatus.ESTIMATED, "Embraer WBM", "Airframe without AE3007 engines"),
        payload_kg=InputParam(4198.0, "kg", DataStatus.SOURCED, "TCDS EA-9606 Section 1", "Maximum passenger/cargo payload"),
        mtow_kg=InputParam(19000.0, "kg", DataStatus.SOURCED, "TCDS EA-9606 Section 1", "Certified Maximum Takeoff Weight"),
        wing_area_m2=InputParam(51.18, "m^2", DataStatus.SOURCED, "Embraer APM Doc 135-01", "Reference wing area"),
        aspect_ratio=InputParam(7.8, "dimensionless", DataStatus.SOURCED, "Embraer APM Doc 135-01", "Wing aspect ratio"),
        cd0=InputParam(0.028, "dimensionless", DataStatus.ASSUMED, "Preliminary Polar", "Clean zero-lift drag coefficient"),
        oswald_e=InputParam(0.80, "dimensionless", DataStatus.ASSUMED, "Preliminary Polar", "Oswald efficiency factor"),
        cruise_altitude_m=InputParam(11000.0, "m", DataStatus.ASSUMED, "Flight Ops", "Nominal cruise altitude"),
        air_density_kg_pm3=InputParam(0.364, "kg/m^3", DataStatus.SOURCED, "ISA Atmosphere Model", "Density at 11,000 m"),
        cruise_speed_mps=InputParam(230.0, "m/s", DataStatus.ASSUMED, "Flight Ops", "Nominal cruise true airspeed (~M0.78)"),
        cl_max_clean=InputParam(1.40, "dimensionless", DataStatus.ESTIMATED, "Clean Polar Estimate", "Clean wing stall CL limit"),
        battery_mass_kg=InputParam(2802.0, "kg", DataStatus.ESTIMATED, "Payload Margin", "Available battery mass under MTOW"),
        pack_specific_energy_wh_kg=InputParam(300.0, "Wh/kg", DataStatus.ASSUMED, "Tech Target", "Pack-level specific energy"),
        usable_dod=InputParam(0.80, "dimensionless", DataStatus.ASSUMED, "Cell Limits", "Maximum usable depth of discharge"),
        continuous_discharge_power_limit_w=InputParam(5.0e6, "W", DataStatus.ASSUMED, "Battery Sizing", "Pack continuous discharge power limit (5.0 MW)"),
        peak_discharge_power_limit_w=InputParam(10.0e6, "W", DataStatus.ASSUMED, "Battery Sizing", "Pack peak discharge power limit (10.0 MW)"),
        motor_mass_kg=InputParam(1000.0, "kg", DataStatus.ESTIMATED, "8 kW/kg Rating", "Propulsion motor dry mass"),
        motor_continuous_rating_w=InputParam(4.5e6, "W", DataStatus.ESTIMATED, "Motor Spec", "Continuous mechanical shaft power rating"),
        motor_peak_rating_w=InputParam(8.0e6, "W", DataStatus.ESTIMATED, "Motor Spec", "Peak mechanical shaft power rating"),
        motor_efficiency=InputParam(0.95, "dimensionless", DataStatus.ASSUMED, "Motor Spec", "Motor electric-to-shaft efficiency"),
        propulsive_efficiency=InputParam(1.0, "dimensionless", DataStatus.ASSUMED, "Ideal Baseline", "Propeller/fan aerodynamic efficiency"),
        additional_powertrain_mass_kg=InputParam(0.0, "kg", DataStatus.ASSUMED, "Zero Overhead", "Mounting, cooling, cabling overhead"),
        target_range_nm=InputParam(500.0, "nm", DataStatus.ASSUMED, "Requirement", "Target mission stage length"),
        reserve_loiter_time_s=InputParam(2700.0, "s", DataStatus.ASSUMED, "Project Policy", "45-minute holding reserve"),
        loiter_power_factor=InputParam(0.60, "dimensionless", DataStatus.ASSUMED, "Aerodynamics", "Power reduction factor during loiter"),
    )


def run_tests():
    print("Executing Hardened DesignEvaluator Verification Test Suite (12 Fixtures)...")

    # Test 1: 基线用例 (500 nm, 4198 kg payload, 300 Wh/kg)
    d1 = build_baseline_candidate()
    r1 = MissionEvaluator.evaluate(d1)
    assert r1.verdict == EvaluationStatus.INFEASIBLE_UNDER_ASSUMPTIONS
    assert r1.energy_limited_range_nm is None
    assert r1.operationally_compliant_range_nm is None
    failed_codes = [f.code for f in r1.failed_constraints]
    assert ConstraintCode.MISSION_ENERGY in failed_codes
    assert ConstraintCode.RESERVE_LOITER_ENERGY in failed_codes
    print("  [PASS] Test 1: Baseline candidate correctly identified as INFEASIBLE (energy shortfall).")

    # Test 2: 数值类型非浮点/布尔注入拦截
    d2 = build_baseline_candidate()
    d2.base_mass_kg = InputParam(True, "kg", DataStatus.SOURCED, "Doc-01")  # type: ignore
    r2 = MissionEvaluator.evaluate(d2)
    assert r2.verdict == EvaluationStatus.INPUT_INVALID
    assert len(r2.input_validation_errors) > 0
    print("  [PASS] Test 2: Input validation correctly rejects boolean type.")

    # Test 3: 超重违规 (Excessive Mass)
    d3 = build_baseline_candidate()
    d3.battery_mass_kg = InputParam(10000.0, "kg", DataStatus.ESTIMATED, "Guess")
    r3 = MissionEvaluator.evaluate(d3)
    assert r3.verdict == EvaluationStatus.INFEASIBLE_UNDER_ASSUMPTIONS
    assert r3.operationally_compliant_range_nm is None
    failed_codes = [f.code for f in r3.failed_constraints]
    assert ConstraintCode.MTOW_LIMIT in failed_codes
    print("  [PASS] Test 3: Excessive mass correctly triggers MTOW_LIMIT failure.")

    # Test 4: 电机持续功率不足
    d4 = build_baseline_candidate()
    d4.motor_continuous_rating_w = InputParam(1.0e6, "W", DataStatus.SOURCED, "Doc-02")
    r4 = MissionEvaluator.evaluate(d4)
    assert r4.verdict == EvaluationStatus.INFEASIBLE_UNDER_ASSUMPTIONS
    failed_codes = [f.code for f in r4.failed_constraints]
    assert ConstraintCode.MOTOR_CONTINUOUS_POWER in failed_codes
    print("  [PASS] Test 4: Insufficient motor power rating correctly isolated.")

    # Test 5: 电池持续放电功率不足
    d5 = build_baseline_candidate()
    d5.continuous_discharge_power_limit_w = InputParam(2.0e6, "W", DataStatus.SOURCED, "Doc-03")
    r5 = MissionEvaluator.evaluate(d5)
    assert r5.verdict == EvaluationStatus.INFEASIBLE_UNDER_ASSUMPTIONS
    failed_codes = [f.code for f in r5.failed_constraints]
    assert ConstraintCode.BATTERY_CONTINUOUS_POWER in failed_codes
    print("  [PASS] Test 5: Insufficient battery discharge limit correctly isolated.")

    # Test 6: 25 nm 可行短途微型航线
    d6 = build_baseline_candidate()
    d6.design_name = "EMB-135_Feasible_Short_Commuter"
    d6.target_range_nm = InputParam(25.0, "nm", DataStatus.ASSUMED, "Ops")
    d6.reserve_loiter_time_s = InputParam(300.0, "s", DataStatus.ASSUMED, "5 min")
    d6.pack_specific_energy_wh_kg = InputParam(600.0, "Wh/kg", DataStatus.ASSUMED, "Solid State")
    r6 = MissionEvaluator.evaluate(d6)
    assert r6.verdict == EvaluationStatus.FEASIBLE_UNDER_ASSUMPTIONS
    assert r6.operationally_compliant_range_nm is not None and r6.operationally_compliant_range_nm > 25.0
    print("  [PASS] Test 6: Short-range commuter design correctly evaluates to FEASIBLE with compliant range.")

    # Test 7: 模式与溯源校验 (Missing Citation on SOURCED / Non-InputParam)
    d7a = build_baseline_candidate()
    d7a.payload_kg = InputParam(4198.0, "kg", DataStatus.SOURCED, source="")  # SOURCED 但来源为空
    r7a = MissionEvaluator.evaluate(d7a)
    assert r7a.verdict == EvaluationStatus.INPUT_INVALID
    assert any("lacks a valid source reference" in err for err in r7a.input_validation_errors)

    d7b = build_baseline_candidate()
    d7b.payload_kg = "4198 kg"  # type: ignore # 非 InputParam 实例
    r7b = MissionEvaluator.evaluate(d7b)
    assert r7b.verdict == EvaluationStatus.INPUT_INVALID
    assert any("must be an instance of InputParam" in err for err in r7b.input_validation_errors)
    print("  [PASS] Test 7: Schema and provenance validator rejects uncited SOURCED field and non-InputParam object.")

    # Test 8: 动态失速限制未提供时输出 UNRESOLVED
    d8 = build_baseline_candidate()
    d8.cl_max_clean = None  # 未提供失速限制
    d8.design_name = "EMB-135_Stall_Unresolved_Candidate"
    d8.target_range_nm = InputParam(25.0, "nm", DataStatus.ASSUMED, "Ops")
    d8.reserve_loiter_time_s = InputParam(300.0, "s", DataStatus.ASSUMED, "5 min")
    d8.pack_specific_energy_wh_kg = InputParam(600.0, "Wh/kg", DataStatus.ASSUMED, "Solid State")
    r8 = MissionEvaluator.evaluate(d8)
    assert r8.verdict == EvaluationStatus.UNRESOLVED
    assert any("cl_max_clean" in note for note in r8.unresolved_assumptions)
    print("  [PASS] Test 8: Missing clean stall boundary correctly yields UNRESOLVED status.")

    # Test 9 (CRITICAL BUG FIX): cl_max_clean 超限 (4.0) 必须立即返回 INPUT_INVALID 而非穿透为 FEASIBLE
    d9 = build_baseline_candidate()
    d9.cl_max_clean = InputParam(4.0, "dimensionless", DataStatus.ESTIMATED, "Exaggerated limit")
    d9.target_range_nm = InputParam(25.0, "nm", DataStatus.ASSUMED, "Ops")
    d9.reserve_loiter_time_s = InputParam(300.0, "s", DataStatus.ASSUMED, "5 min")
    d9.pack_specific_energy_wh_kg = InputParam(600.0, "Wh/kg", DataStatus.ASSUMED, "Solid State")
    r9 = MissionEvaluator.evaluate(d9)
    assert r9.verdict == EvaluationStatus.INPUT_INVALID
    assert any("cl_max_clean" in err for err in r9.input_validation_errors)
    print("  [PASS] Test 9 (CRITICAL BUG FIX): Out-of-bounds cl_max_clean=4.0 blocked at pre-evaluation gate.")

    # Test 10: 单位白名单校验 (Units Validation: 电池质量误传为 "lb")
    d10 = build_baseline_candidate()
    d10.battery_mass_kg = InputParam(2802.0, "lb", DataStatus.ESTIMATED, "Imperial typo")
    r10 = MissionEvaluator.evaluate(d10)
    assert r10.verdict == EvaluationStatus.INPUT_INVALID
    assert any("incompatible units 'lb'" in err for err in r10.input_validation_errors)
    print("  [PASS] Test 10: Incompatible units ('lb' for mass) rejected by canonical units schema.")

    # Test 11: 顶层输入对象类型防护 (Top-Level Object Type-Check)
    r11a = MissionEvaluator.evaluate(None)
    assert r11a.verdict == EvaluationStatus.INPUT_INVALID
    assert any("Expected DesignInput instance" in err for err in r11a.input_validation_errors)

    r11b = MissionEvaluator.evaluate({"design_name": "DictCandidate"})
    assert r11b.verdict == EvaluationStatus.INPUT_INVALID
    print("  [PASS] Test 11: Top-level non-DesignInput objects cleanly caught without crashing.")

    # Test 12: 能量满足但电机功率不足 (Decoupled Power Failure Verification)
    d12 = build_baseline_candidate()
    d12.target_range_nm = InputParam(10.0, "nm", DataStatus.ASSUMED)
    d12.reserve_loiter_time_s = InputParam(60.0, "s", DataStatus.ASSUMED)
    d12.motor_continuous_rating_w = InputParam(1.0e6, "W", DataStatus.SOURCED, "Doc-04")  # 仅 1.0 MW (需求 4.0 MW)
    r12 = MissionEvaluator.evaluate(d12)
    assert r12.verdict == EvaluationStatus.INFEASIBLE_UNDER_ASSUMPTIONS
    failed_codes_12 = [f.code for f in r12.failed_constraints]
    assert ConstraintCode.MOTOR_CONTINUOUS_POWER in failed_codes_12
    assert ConstraintCode.MISSION_ENERGY not in failed_codes_12
    assert r12.operationally_compliant_range_nm is None
    print("  [PASS] Test 12: Candidate passing energy but failing motor power correctly isolated.")

    print("\nAll 12 automated verification test assertions passed successfully.")


if __name__ == "__main__":
    run_tests()
    print("\n" + "=" * 92)
    print("             EXECUTING REPRODUCIBLE BASELINE DESIGN EVALUATION")
    print("=" * 92)
    base_candidate = build_baseline_candidate()
    base_report = MissionEvaluator.evaluate(base_candidate)
    print_evaluation_report(base_report)