"""
Aircraft Design Framework — Boundary Evaluation & Sensitivity Engine
Module: MissionSolver.py
Designation: Closed-Form Algebraic Boundary Physics Solver with Lower-Bound Proof
Scaffold Status: Screening Scaffold Frozen (v0.3.5-FINAL)
Version: v1.1-FINAL (Thrust-to-Electric Power Chain Hardened)
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BoundaryVerdict(Enum):
    FEASIBLE_UNDER_ASSUMPTIONS = "FEASIBLE_UNDER_ASSUMPTIONS"
    INFEASIBLE_UNDER_ASSUMPTIONS = "INFEASIBLE_UNDER_ASSUMPTIONS"
    CALCULATION_ERROR = "CALCULATION_ERROR"


@dataclass(frozen=True)
class AircraftPhysicsParameters:
    # 平台基线数据 (EMB-135)
    mtow_kg: float = 19000.0
    base_mass_after_engine_removal_kg: float = 11000.0  # 扣除原 AE3007 发动机及附属系统后的机体空重
    nominal_payload_kg: float = 4198.0                  # 目标设计商载 (最大载荷)
    wing_area_m2: float = 51.18
    aspect_ratio: float = 7.8
    cd0: float = 0.028
    oswald_e: float = 0.80

    # 大气环境与任务要求
    air_density_kg_pm3: float = 0.364                   # 11,000 m (FL360) ISA 大气密度
    target_range_nm: float = 500.0
    reserve_loiter_time_s: float = 45.0 * 60.0          # 项目假设 45 分钟备用盘旋 (PROJECT_ASSUMPTION)
    loiter_power_factor: float = 0.60                   # 盘旋功率系数

    # 推进系统参数 (PROVISIONAL ASSUMPTIONS)
    propulsive_efficiency: float = 1.0                  # 推进器效率 (暂定理想乐观假设: 1.0)
    motor_efficiency: float = 0.95                      # 电机电-机转换效率
    motor_shaft_specific_power_w_kg: float = 8000.0     # 8.0 kW/kg 机械输出比功率 (轴功率)
    battery_specific_energy_wh_kg: float = 300.0        # 300 Wh/kg 包级比能量
    battery_usable_dod: float = 0.80                    # 可用放电深度 80%

    # 物理常数
    gravity_mps2: float = 9.80665

    @property
    def induced_drag_k(self) -> float:
        return 1.0 / (math.pi * self.oswald_e * self.aspect_ratio)

    @property
    def target_range_m(self) -> float:
        return self.target_range_nm * 1852.0

    @property
    def available_retrofit_mass_kg(self) -> float:
        return self.mtow_kg - self.base_mass_after_engine_removal_kg - self.nominal_payload_kg

    @property
    def minimum_gross_mass_kg(self) -> float:
        return self.base_mass_after_engine_removal_kg + self.nominal_payload_kg

    def validate(self) -> Optional[str]:
        """严格输入参数物理有效性与范围校验"""
        checks = [
            ("mtow_kg", self.mtow_kg, 1000.0, 1000000.0),
            ("base_mass_after_engine_removal_kg", self.base_mass_after_engine_removal_kg, 500.0, self.mtow_kg),
            ("nominal_payload_kg", self.nominal_payload_kg, 0.0, self.mtow_kg),
            ("wing_area_m2", self.wing_area_m2, 1.0, 1000.0),
            ("aspect_ratio", self.aspect_ratio, 1.0, 30.0),
            ("cd0", self.cd0, 0.001, 0.20),
            ("oswald_e", self.oswald_e, 0.1, 1.0),
            ("air_density_kg_pm3", self.air_density_kg_pm3, 0.01, 2.0),
            ("target_range_nm", self.target_range_nm, 1.0, 10000.0),
            ("reserve_loiter_time_s", self.reserve_loiter_time_s, 0.0, 86400.0),
            ("loiter_power_factor", self.loiter_power_factor, 0.1, 1.5),
            ("propulsive_efficiency", self.propulsive_efficiency, 0.1, 1.0),
            ("motor_efficiency", self.motor_efficiency, 0.1, 1.0),
            ("motor_shaft_specific_power_w_kg", self.motor_shaft_specific_power_w_kg, 100.0, 100000.0),
            ("battery_specific_energy_wh_kg", self.battery_specific_energy_wh_kg, 10.0, 5000.0),
            ("battery_usable_dod", self.battery_usable_dod, 0.1, 1.0),
            ("gravity_mps2", self.gravity_mps2, 1.0, 20.0),
        ]
        for name, val, v_min, v_max in checks:
            if not isinstance(val, (int, float)) or type(val) is bool or not math.isfinite(val):
                return f"Input parameter {name} must be a finite real number, got: {val}"
            if not (v_min <= val <= v_max):
                return f"Input parameter {name} = {val} is outside valid physical range [{v_min}, {v_max}]"

        if self.available_retrofit_mass_kg <= 0:
            return (
                f"Invalid mass configuration: Available retrofit mass <= 0 "
                f"({self.mtow_kg} - {self.base_mass_after_engine_removal_kg} - {self.nominal_payload_kg} = {self.available_retrofit_mass_kg})"
            )
        return None


@dataclass
class PointCalculation:
    eval_mass_kg: float
    drag_n: float
    cl: float
    cd: float
    ld_ratio: float
    thrust_power_w: float
    shaft_power_w: float
    electric_power_w: float
    peak_shaft_power_w: float
    motor_mass_kg: float
    cruise_energy_j: float
    loiter_energy_j: float
    total_energy_500nm_j: float
    required_battery_mass_kg: float
    total_powertrain_mass_kg: float
    mass_margin_kg: float  # available_retrofit_mass_kg - total_powertrain_mass_kg


@dataclass
class BoundaryEvaluationReport:
    verdict: BoundaryVerdict
    status_summary: str
    cruise_speed_mps: float
    available_retrofit_mass_kg: float

    # 两个质量边界的确定计算点
    minimum_mass_bound: PointCalculation
    mtow_mass_bound: PointCalculation

    # 敏感性分析情景
    available_battery_mass_kg: float
    scenario_a_reserve_satisfied: bool
    scenario_a_compliant_range_str: str
    scenario_a_zero_reserve_range_nm: float
    scenario_b_req_battery_wh_kg: float
    scenario_b_technology_multiple: float

    error_detail: Optional[str] = None


class MissionSolver:
    """
    EMB-135 电动改装代数边界求解与敏感性分析引擎
    """

    def __init__(self, params: Optional[AircraftPhysicsParameters] = None):
        self.p = params or AircraftPhysicsParameters()

    def _evaluate_mass_point(self, mass_kg: float, speed_mps: float) -> PointCalculation:
        """在特定飞机总重下执行闭式代数计算"""
        weight_n = mass_kg * self.p.gravity_mps2
        q = 0.5 * self.p.air_density_kg_pm3 * (speed_mps ** 2)
        cl = weight_n / (q * self.p.wing_area_m2)
        cd = self.p.cd0 + self.p.induced_drag_k * (cl ** 2)
        drag_n = cd * q * self.p.wing_area_m2
        ld_ratio = cl / cd if cd > 0 else 0.0

        # 三级功率拆解
        p_thrust = drag_n * speed_mps
        p_shaft = p_thrust / self.p.propulsive_efficiency
        p_electric = p_shaft / self.p.motor_efficiency
        p_peak_shaft = 2.0 * p_shaft  # 电机机械轴功率峰值按 2x 巡航设计

        # 电机质量 (按机械轴比功率 8 kW/kg)
        motor_mass = p_peak_shaft / self.p.motor_shaft_specific_power_w_kg

        # 500 nm 巡航电能与 45 分钟盘旋电能 (基于电功率积分)
        t_cruise_s = self.p.target_range_m / speed_mps
        e_cruise = p_electric * t_cruise_s
        p_loiter = self.p.loiter_power_factor * p_electric
        e_loiter = p_loiter * self.p.reserve_loiter_time_s
        e_total = e_cruise + e_loiter

        # 所需电池组质量
        usable_pack_density_j_kg = self.p.battery_specific_energy_wh_kg * 3600.0 * self.p.battery_usable_dod
        req_batt_mass = e_total / usable_pack_density_j_kg

        total_powertrain_mass = motor_mass + req_batt_mass
        mass_margin = self.p.available_retrofit_mass_kg - total_powertrain_mass

        return PointCalculation(
            eval_mass_kg=mass_kg,
            drag_n=drag_n,
            cl=cl,
            cd=cd,
            ld_ratio=ld_ratio,
            thrust_power_w=p_thrust,
            shaft_power_w=p_shaft,
            electric_power_w=p_electric,
            peak_shaft_power_w=p_peak_shaft,
            motor_mass_kg=motor_mass,
            cruise_energy_j=e_cruise,
            loiter_energy_j=e_loiter,
            total_energy_500nm_j=e_total,
            required_battery_mass_kg=req_batt_mass,
            total_powertrain_mass_kg=total_powertrain_mass,
            mass_margin_kg=mass_margin,
        )

    def evaluate_comprehensive_boundaries(
        self,
        cruise_speed_mps: float = 230.0,  # 暂定工程假设: 230 m/s (~Mach 0.778)
    ) -> BoundaryEvaluationReport:
        """
        入口级安全校验与代数双边界求解
        """
        try:
            # 1. 严格参数校验 (防止除零与非法类型)
            validation_error = self.p.validate()
            if validation_error:
                return self._create_error_report(validation_error)

            if (
                not isinstance(cruise_speed_mps, (int, float))
                or type(cruise_speed_mps) is bool
                or not math.isfinite(cruise_speed_mps)
                or cruise_speed_mps <= 1.0
            ):
                return self._create_error_report(
                    f"Invalid cruise_speed_mps: must be a finite real number > 1.0 m/s, got: {cruise_speed_mps}"
                )

            avail_retrofit_mass = self.p.available_retrofit_mass_kg  # 3,802.0 kg
            min_mass = self.p.minimum_gross_mass_kg                  # 15,198.0 kg
            mtow_mass = self.p.mtow_kg                              # 19,000.0 kg

            # 2. 计算最低质量边界 (Minimum Mass Bound: 15,198 kg)
            min_bound = self._evaluate_mass_point(min_mass, cruise_speed_mps)

            # 3. 计算 MTOW 质量边界 (MTOW Bound: 19,000 kg)
            mtow_bound = self._evaluate_mass_point(mtow_mass, cruise_speed_mps)

            # 4. 数值有限性核实
            for pt in [min_bound, mtow_bound]:
                for attr in [
                    pt.drag_n,
                    pt.thrust_power_w,
                    pt.shaft_power_w,
                    pt.electric_power_w,
                    pt.motor_mass_kg,
                    pt.required_battery_mass_kg,
                ]:
                    if not math.isfinite(attr) or attr <= 0:
                        return self._create_error_report(
                            "Calculation produced non-finite or non-positive physical quantities."
                        )

            # 5. 核心不可行性判定 (基于代数下界证明)
            infeasible_summary_text = (
                "INFEASIBLE_UNDER_ASSUMPTIONS (Infeasible under given assumptions: "
                "500 nm mission, 4,198 kg payload, 300 Wh/kg battery, 80% DoD, "
                "and simplified aerodynamic model)"
            )

            if min_bound.total_powertrain_mass_kg > avail_retrofit_mass:
                verdict = BoundaryVerdict.INFEASIBLE_UNDER_ASSUMPTIONS
                summary = infeasible_summary_text
            elif mtow_bound.total_powertrain_mass_kg <= avail_retrofit_mass:
                verdict = BoundaryVerdict.FEASIBLE_UNDER_ASSUMPTIONS
                summary = "FEASIBLE_UNDER_ASSUMPTIONS (Mass budget closed under simplified screening equations)"
            else:
                verdict = BoundaryVerdict.INFEASIBLE_UNDER_ASSUMPTIONS
                summary = infeasible_summary_text

            # -------------------------------------------------------------
            # 6. 敏感性分析 (在 MTOW 边界阻力/功率基线处计算)
            # -------------------------------------------------------------
            batt_mass_avail = avail_retrofit_mass - mtow_bound.motor_mass_kg

            # 情景 A: 最大航程 (固定 3,802 kg 动力总成上限)
            usable_pack_density_j_kg = (
                self.p.battery_specific_energy_wh_kg * 3600.0 * self.p.battery_usable_dod
            )
            if batt_mass_avail <= 0:
                scen_a_res_ok = False
                scen_a_range_str = "NO_RESERVE_COMPLIANT_MISSION"
                scen_a_zero_res_nm = 0.0
            else:
                total_batt_avail_energy = batt_mass_avail * usable_pack_density_j_kg
                scen_a_zero_res_m = (total_batt_avail_energy * cruise_speed_mps) / mtow_bound.electric_power_w
                scen_a_zero_res_nm = scen_a_zero_res_m / 1852.0

                net_cruise_energy = total_batt_avail_energy - mtow_bound.loiter_energy_j
                if net_cruise_energy <= 0:
                    scen_a_res_ok = False
                    scen_a_range_str = "NO_RESERVE_COMPLIANT_MISSION"
                else:
                    scen_a_res_ok = True
                    scen_a_max_range_m = (net_cruise_energy * cruise_speed_mps) / mtow_bound.electric_power_w
                    scen_a_range_str = f"{scen_a_max_range_m / 1852.0:.1f} nm"

            # 情景 B: 所需电池技术突破比能量 (500 nm 航程 + 3,802 kg 动力总成上限)
            if batt_mass_avail <= 0:
                scen_b_req_wh_kg = float("inf")
                scen_b_multiple = float("inf")
            else:
                scen_b_req_wh_kg = mtow_bound.total_energy_500nm_j / (
                    batt_mass_avail * 3600.0 * self.p.battery_usable_dod
                )
                scen_b_multiple = scen_b_req_wh_kg / self.p.battery_specific_energy_wh_kg

            return BoundaryEvaluationReport(
                verdict=verdict,
                status_summary=summary,
                cruise_speed_mps=cruise_speed_mps,
                available_retrofit_mass_kg=avail_retrofit_mass,
                minimum_mass_bound=min_bound,
                mtow_mass_bound=mtow_bound,
                available_battery_mass_kg=batt_mass_avail,
                scenario_a_reserve_satisfied=scen_a_res_ok,
                scenario_a_compliant_range_str=scen_a_range_str,
                scenario_a_zero_reserve_range_nm=scen_a_zero_res_nm,
                scenario_b_req_battery_wh_kg=scen_b_req_wh_kg,
                scenario_b_technology_multiple=scen_b_multiple,
            )

        except Exception as ex:
            return self._create_error_report(f"Unhandled numerical exception: {type(ex).__name__}: {str(ex)}")

    def _create_error_report(self, error_msg: str) -> BoundaryEvaluationReport:
        dummy_point = PointCalculation(
            eval_mass_kg=0.0,
            drag_n=0.0,
            cl=0.0,
            cd=0.0,
            ld_ratio=0.0,
            thrust_power_w=0.0,
            shaft_power_w=0.0,
            electric_power_w=0.0,
            peak_shaft_power_w=0.0,
            motor_mass_kg=0.0,
            cruise_energy_j=0.0,
            loiter_energy_j=0.0,
            total_energy_500nm_j=0.0,
            required_battery_mass_kg=0.0,
            total_powertrain_mass_kg=0.0,
            mass_margin_kg=0.0,
        )
        return BoundaryEvaluationReport(
            verdict=BoundaryVerdict.CALCULATION_ERROR,
            status_summary="CALCULATION_ERROR",
            cruise_speed_mps=0.0,
            available_retrofit_mass_kg=0.0,
            minimum_mass_bound=dummy_point,
            mtow_mass_bound=dummy_point,
            available_battery_mass_kg=0.0,
            scenario_a_reserve_satisfied=False,
            scenario_a_compliant_range_str="CALCULATION_ERROR",
            scenario_a_zero_reserve_range_nm=0.0,
            scenario_b_req_battery_wh_kg=0.0,
            scenario_b_technology_multiple=0.0,
            error_detail=error_msg,
        )


if __name__ == "__main__":
    solver = MissionSolver()
    rep = solver.evaluate_comprehensive_boundaries(cruise_speed_mps=230.0)

    if rep.verdict == BoundaryVerdict.CALCULATION_ERROR:
        print(f"[CALCULATION ERROR]: {rep.error_detail}")
        exit(1)

    min_pt = rep.minimum_mass_bound
    mtow_pt = rep.mtow_mass_bound

    print("=" * 86)
    print("  EMB-135 电动改装双边界判定与敏感性分析 (MissionSolver.py - Closed-Form Bounds)")
    print("=" * 86)
    print(f"\n[1. 基础质量预算 (Mass Budget Breakdown)]")
    print(f"  - 结构最大起飞总重 (MTOW)               : {solver.p.mtow_kg:,.1f} kg")
    print(f"  - 扣除原发动机后空重 (Base Mass)        : {solver.p.base_mass_after_engine_removal_kg:,.1f} kg (不含原 AE3007 发动机)")
    print(f"  - 目标设计商载 (Payload)                : {solver.p.nominal_payload_kg:,.1f} kg")
    print(f"  - 理论最低总质量下界 (Minimum Mass)     : {solver.p.minimum_gross_mass_kg:,.1f} kg (完全不含动力系统)")
    print(f"  - 刚性剩余可用改装质量预算              : {rep.available_retrofit_mass_kg:,.1f} kg")

    print(f"\n[2. 气动与推进功率边界对照]")
    print(f"  - 巡航速度 (PROVISIONAL ASSUMPTION)     : {rep.cruise_speed_mps:.1f} m/s (~Mach 0.778)")
    print(f"  - 推进器效率 (PROVISIONAL ASSUMPTION)   : {solver.p.propulsive_efficiency:.2f} (理想乐观基准)")
    print(f"  - 电机效率                              : {solver.p.motor_efficiency:.2f}")
    print(f"  {'指标名称':<32} | {'最低质量边界 (15,198 kg)':<22} | {'MTOW边界 (19,000 kg)':<20}")
    print(f"  {'-'*32}-|-{'-'*22}-|-{'-'*20}")
    print(f"  {'升力系数 (C_L)':<30} | {min_pt.cl:<22.4f} | {mtow_pt.cl:<20.4f}")
    print(f"  {'阻力系数 (C_D)':<30} | {min_pt.cd:<22.4f} | {mtow_pt.cd:<20.4f}")
    print(f"  {'升阻比 (L/D)':<30} | {min_pt.ld_ratio:<22.2f} | {mtow_pt.ld_ratio:<20.2f}")
    print(f"  {'巡航气动阻力 (Drag)':<28} | {min_pt.drag_n / 1000.0:<19.2f} kN | {mtow_pt.drag_n / 1000.0:<17.2f} kN")
    print(f"  {'有效推力功率 (P_thrust)':<25} | {min_pt.thrust_power_w / 1e6:<19.3f} MW | {mtow_pt.thrust_power_w / 1e6:<17.3f} MW")
    print(f"  {'机械轴功率 (P_shaft)':<27} | {min_pt.shaft_power_w / 1e6:<19.3f} MW | {mtow_pt.shaft_power_w / 1e6:<17.3f} MW")
    print(f"  {'电机输入电功率 (P_electric)':<25} | {min_pt.electric_power_w / 1e6:<19.3f} MW | {mtow_pt.electric_power_w / 1e6:<17.3f} MW")
    print(f"  {'电机所需质量 (8 kW/kg 轴功率)':<24} | {min_pt.motor_mass_kg:<19.1f} kg | {mtow_pt.motor_mass_kg:<17.1f} kg")

    print(f"\n[3. 500 nm 任务能量与电池质量需求对照]")
    print(f"  {'500 nm 巡航电能需求':<30} | {min_pt.cruise_energy_j / 1e6:<19.1f} MJ | {mtow_pt.cruise_energy_j / 1e6:<17.1f} MJ")
    print(f"  {'项目假设 45 min 盘旋备用电能':<26} | {min_pt.loiter_energy_j / 1e6:<19.1f} MJ | {mtow_pt.loiter_energy_j / 1e6:<17.1f} MJ")
    print(f"  {'任务总需求电能':<32} | {min_pt.total_energy_500nm_j / 1e6:<19.1f} MJ | {mtow_pt.total_energy_500nm_j / 1e6:<17.1f} MJ")
    print(f"  {'所需电池质量 (300 Wh/kg, 80%)':<24} | {min_pt.required_battery_mass_kg:<19.1f} kg | {mtow_pt.required_battery_mass_kg:<17.1f} kg")
    print(f"  {'电驱总质量 (电机 + 电池)':<26} | {min_pt.total_powertrain_mass_kg:<19.1f} kg | {mtow_pt.total_powertrain_mass_kg:<17.1f} kg")
    print(f"  {'可用质量裕度 (Margin)':<28} | {min_pt.mass_margin_kg:<19.1f} kg | {mtow_pt.mass_margin_kg:<17.1f} kg")

    print(f"\n[4. 核心系统判定 (Core Architectural Verdict)]")
    print(f"  - 判定结论: 【 {rep.verdict.value} 】")
    print(f"  - 完整声明: {rep.status_summary}")

    print(f"\n[5. 敏感性分析 (Sensitivity Analysis)]")
    print(f"  (A) Scenario A (Trade-off: 严格限制改装质量 <= 3,802 kg):")
    print(f"      - 扣除 MTOW 边界电机后可用电池质量 : {rep.available_battery_mass_kg:,.1f} kg")
    print(f"      - 满足项目假设 45 min 备用巡航航程 : {rep.scenario_a_compliant_range_str}")
    print(f"      - [参考] 理论零备用极限放电航程   : {rep.scenario_a_zero_reserve_range_nm:.1f} nm")
    print(f"  (B) Scenario B (Tech Leap: 必须飞 500 nm 且总改装质量 <= 3,802 kg):")
    print(f"      - 维持 500 nm 所需的电池包比能量 : {rep.scenario_b_req_battery_wh_kg:,.1f} Wh/kg")
    print(f"      - 相比当前假设 (300 Wh/kg) 的倍数  : {rep.scenario_b_technology_multiple:.2f} 倍 (技术代差差距)")
    print("=" * 86)