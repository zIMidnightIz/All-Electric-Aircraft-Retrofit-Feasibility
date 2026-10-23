"""
Aircraft Design Framework — Sensitivity Sweep & Series-Hybrid Sizing Engine
Module: Sensitivity_and_Hybrid_Solver.py
Designation: Design Space Exploration & Hybrid Powertrain Evaluation
Scaffold Status: Screening Scaffold Frozen (v0.3.5-FINAL)
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple


# =====================================================================
# 1. 基础参数与纯电边界物理引擎
# =====================================================================

@dataclass(frozen=True)
class BaselineAircraft:
    mtow_kg: float = 19000.0
    base_mass_after_engine_removal_kg: float = 11000.0
    nominal_payload_kg: float = 4198.0
    wing_area_m2: float = 51.18
    aspect_ratio: float = 7.8
    cd0: float = 0.028
    oswald_e: float = 0.80
    air_density_kg_pm3: float = 0.364       # 11,000 m (FL360)
    gravity_mps2: float = 9.80665

    propulsive_efficiency: float = 1.0      # 暂定理想推进器效率
    motor_efficiency: float = 0.95
    motor_shaft_specific_power_w_kg: float = 8000.0  # 8 kW/kg 轴功率
    reserve_loiter_time_s: float = 45.0 * 60.0       # 45 min
    loiter_power_factor: float = 0.60

    @property
    def induced_drag_k(self) -> float:
        return 1.0 / (math.pi * self.oswald_e * self.aspect_ratio)

    @property
    def available_retrofit_mass_kg(self) -> float:
        return self.mtow_kg - self.base_mass_after_engine_removal_kg - self.nominal_payload_kg


# =====================================================================
# 2. 敏感性分析遍历模块 (Sensitivity Sweep)
# =====================================================================

class SensitivityAnalyzer:
    def __init__(self, ac: BaselineAircraft = BaselineAircraft()):
        self.ac = ac

    def compute_electric_point(
        self,
        gross_mass_kg: float,
        range_nm: float,
        battery_wh_kg: float,
        cruise_speed_mps: float = 230.0,
        dod: float = 0.80,
    ) -> Dict[str, float]:
        """计算指定飞机总重、航程和电池比能量下的纯电需求"""
        weight_n = gross_mass_kg * self.ac.gravity_mps2
        q = 0.5 * self.ac.air_density_kg_pm3 * (cruise_speed_mps ** 2)
        cl = weight_n / (q * self.ac.wing_area_m2)
        cd = self.ac.cd0 + self.ac.induced_drag_k * (cl ** 2)
        drag_n = cd * q * self.ac.wing_area_m2

        p_thrust = drag_n * cruise_speed_mps
        p_shaft = p_thrust / self.ac.propulsive_efficiency
        p_electric = p_shaft / self.ac.motor_efficiency
        motor_mass = (2.0 * p_shaft) / self.ac.motor_shaft_specific_power_w_kg

        t_cruise = (range_nm * 1852.0) / cruise_speed_mps
        e_cruise = p_electric * t_cruise
        e_loiter = (self.ac.loiter_power_factor * p_electric) * self.ac.reserve_loiter_time_s
        e_total = e_cruise + e_loiter

        usable_density_j_kg = battery_wh_kg * 3600.0 * dod
        req_batt_mass = e_total / usable_density_j_kg
        total_powertrain = motor_mass + req_batt_mass

        return {
            "drag_n": drag_n,
            "p_electric_mw": p_electric / 1e6,
            "motor_mass_kg": motor_mass,
            "e_cruise_mj": e_cruise / 1e6,
            "e_loiter_mj": e_loiter / 1e6,
            "e_total_mj": e_total / 1e6,
            "req_batt_mass_kg": req_batt_mass,
            "total_powertrain_kg": total_powertrain,
        }

    def run_all_sweeps(self, cruise_speed_mps: float = 230.0):
        print("=" * 95)
        print("                   EMB-135 电动改装三维敏感性分析 (SENSITIVITY SWEEP)")
        print(f"      基线设定: 可用改装质量 = {self.ac.available_retrofit_mass_kg:,.1f} kg | 巡航速度 = {cruise_speed_mps:.1f} m/s (~Mach 0.778)")
        print("=" * 95)

        # -------------------------------------------------------------
        # 1. 电池技术突破遍历 (500 nm, 4198 kg 载荷, MTOW 边界阻力基准)
        # -------------------------------------------------------------
        print("\n[维度 1: 电池技术突破遍历 (500 nm 任务, MTOW 19,000 kg 气动基线)]")
        print(f"{'电池比能量 (Wh/kg)':<20} | {'所需电池质量 (kg)':<18} | {'电机质量 (kg)':<15} | {'电驱总质量 (kg)':<18} | {'质量缺口 (vs 3,802 kg)':<20}")
        print("-" * 95)
        densities = [300.0, 400.0, 500.0, 600.0, 800.0, 1000.0]
        for d in densities:
            res = self.compute_electric_point(19000.0, 500.0, d, cruise_speed_mps)
            deficit = res["total_powertrain_kg"] - self.ac.available_retrofit_mass_kg
            print(f"{d:<20.1f} | {res['req_batt_mass_kg']:<18,.1f} | {res['motor_mass_kg']:<15.1f} | {res['total_powertrain_kg']:<18,.1f} | {deficit:>+18,.1f} kg")

        # 临界比能量求解 (让电驱总质量恰好等于 3,802 kg)
        res_ref = self.compute_electric_point(19000.0, 500.0, 300.0, cruise_speed_mps)
        batt_avail = self.ac.available_retrofit_mass_kg - res_ref["motor_mass_kg"]
        crit_density = (res_ref["e_total_mj"] * 1e6) / (batt_avail * 3600.0 * 0.80)
        print(f"\n>>> 临界突破点: 电池比能量必须达到 【 {crit_density:,.1f} Wh/kg 】 (当前 300 Wh/kg 的 {crit_density/300:.2f} 倍) 才能满足 MTOW 限制。")

        # -------------------------------------------------------------
        # 2. 航程妥协遍历 (保持 300 Wh/kg, 4198 kg 载荷, 包含 45 min 备用)
        # -------------------------------------------------------------
        print("\n" + "=" * 95)
        print("[维度 2: 航程妥协遍历 (保持 300 Wh/kg, 4,198 kg 载荷, 满足 45 min 备用)]")
        print(f"{'目标航程 (nm)':<15} | {'巡航电能 (MJ)':<15} | {'备用电能 (MJ)':<15} | {'所需电池质量 (kg)':<18} | {'电驱总质量 (kg)':<18} | {'是否满足 MTOW'}")
        print("-" * 95)
        ranges = [500.0, 400.0, 300.0, 200.0, 100.0, 50.0]
        for r in ranges:
            res = self.compute_electric_point(19000.0, r, 300.0, cruise_speed_mps)
            status = "FEASIBLE" if res["total_powertrain_kg"] <= self.ac.available_retrofit_mass_kg else "EXCEEDS MTOW"
            print(f"{r:<15.1f} | {res['e_cruise_mj']:<15,.1f} | {res['e_loiter_mj']:<15,.1f} | {res['req_batt_mass_kg']:<18,.1f} | {res['total_powertrain_kg']:<18,.1f} | {status}")

        print(f"\n>>> 航程妥协发现: 即使航程缩减至 0 nm，仅 45 分钟备用盘旋电能就需消耗 {res_ref['e_loiter_mj']:,.1f} MJ 电能，")
        print(f"    需要电池质量高达 {res_ref['e_loiter_mj']*1e6 / (300*3600*0.8):,.1f} kg，单项已超过可用改装总预算 ({self.ac.available_retrofit_mass_kg:,.1f} kg)！")
        print("    结论: 在当前 45 分钟备用规则下，仅凭缩减航程无法实现纯电改装合法可行。")

        # -------------------------------------------------------------
        # 3. 载荷妥协遍历 (保持 300 Wh/kg, 500 nm 航程)
        # -------------------------------------------------------------
        print("\n" + "=" * 95)
        print("[维度 3: 载荷妥协遍历 (保持 300 Wh/kg, 500 nm 航程, 总重固定在 MTOW 边界)]")
        print(f"{'商载质量 (kg)':<15} | {'可用改装质量 (kg)':<18} | {'所需电池质量 (kg)':<18} | {'所需电驱质量 (kg)':<18} | {'净质量缺口 (kg)'}")
        print("-" * 95)
        payloads = [4198.0, 3000.0, 2000.0, 1000.0, 0.0]
        for p in payloads:
            avail_mass = self.ac.mtow_kg - self.ac.base_mass_after_engine_removal_kg - p
            res = self.compute_electric_point(19000.0, 500.0, 300.0, cruise_speed_mps)
            deficit = res["total_powertrain_kg"] - avail_mass
            print(f"{p:<15.1f} | {avail_mass:<18,.1f} | {res['req_batt_mass_kg']:<18,.1f} | {res['total_powertrain_kg']:<18,.1f} | {deficit:>+16,.1f} kg")

        print("\n>>> 载荷妥协发现: 即使商载清零 (空机轮渡 0 载荷)，可用质量仅上升到 8,000 kg，仍远低于所需的 28,515 kg 电驱质量。")


# =====================================================================
# 3. 串联混合动力求解器 (Series Hybrid Mission Solver)
# =====================================================================

@dataclass(frozen=True)
class HybridSystemConfig:
    genset_mass_kg: float = 1500.0              # 燃气涡轮发电机质量
    genset_continuous_power_w: float = 2.0e6     # 恒定 2.0 MW 净电功率
    genset_thermal_efficiency: float = 0.40      # 热效率 40%

    motor_mass_kg: float = 1000.0               # 电机质量 (机械轴峰值 8.0 MW)
    battery_mass_kg: float = 1302.0             # 缓冲电池质量 (3,802 - 1500 - 1000)
    battery_specific_energy_wh_kg: float = 300.0
    battery_usable_dod: float = 0.80

    kerosene_specific_energy_wh_kg: float = 12000.0  # 航空煤油比能量 (12,000 Wh/kg = 43.2 MJ/kg)


class HybridMissionSolver:
    """
    EMB-135 串联混合动力 (Series-Hybrid) 质量-能量-燃油闭环求解器
    """

    def __init__(self, ac: BaselineAircraft = BaselineAircraft(), hy: HybridSystemConfig = HybridSystemConfig()):
        self.ac = ac
        self.hy = hy

    def evaluate_hybrid_mission(
        self,
        range_nm: float = 500.0,
        cruise_speed_mps: float = 230.0,
    ) -> Dict[str, Any]:
        """
        在 MTOW 19,000 kg 气动功率需求下，计算混合动力能耗、燃油消耗与总重缺口
        """
        # 1. 结构与动力干重核算
        dry_powertrain_mass = self.hy.genset_mass_kg + self.hy.motor_mass_kg + self.hy.battery_mass_kg
        dry_takeoff_mass = self.ac.base_mass_after_engine_removal_kg + self.ac.nominal_payload_kg + dry_powertrain_mass

        # 2. 气动力与电功率需求 (在 MTOW 19,000 kg 边界评估)
        weight_n = self.ac.mtow_kg * self.ac.gravity_mps2
        q = 0.5 * self.ac.air_density_kg_pm3 * (cruise_speed_mps ** 2)
        cl = weight_n / (q * self.ac.wing_area_m2)
        cd = self.ac.cd0 + self.ac.induced_drag_k * (cl ** 2)
        drag_n = cd * q * self.ac.wing_area_m2

        p_thrust = drag_n * cruise_speed_mps
        p_shaft = p_thrust / self.ac.propulsive_efficiency
        p_electric_cruise = p_shaft / self.ac.motor_efficiency  # ~4.21 MW
        p_electric_loiter = self.ac.loiter_power_factor * p_electric_cruise  # ~2.53 MW

        # 3. 飞行时间
        t_cruise_s = (range_nm * 1852.0) / cruise_speed_mps  # ~4026 s
        t_loiter_s = self.ac.reserve_loiter_time_s           # 2700 s
        t_total_s = t_cruise_s + t_loiter_s                  # 6726 s

        # 4. 发电机电能贡献 (发电机全功率恒定 2.0 MW 运行)
        e_gen_cruise = self.hy.genset_continuous_power_w * t_cruise_s
        e_gen_loiter = self.hy.genset_continuous_power_w * t_loiter_s
        e_gen_total_electric = self.hy.genset_continuous_power_w * t_total_s

        # 发电机消耗煤油质量
        kerosene_energy_density_j_kg = self.hy.kerosene_specific_energy_wh_kg * 3600.0  # 43.2 MJ/kg
        fuel_energy_required_j = e_gen_total_electric / self.hy.genset_thermal_efficiency
        fuel_burned_kg = fuel_energy_required_j / kerosene_energy_density_j_kg

        # 5. 任务总电能需求与电池供电分析
        e_req_cruise = p_electric_cruise * t_cruise_s
        e_req_loiter = p_electric_loiter * t_loiter_s
        e_req_total = e_req_cruise + e_req_loiter

        # 电池最大可用容量
        e_batt_usable = (
            self.hy.battery_mass_kg * self.hy.battery_specific_energy_wh_kg * 3600.0 * self.hy.battery_usable_dod
        )

        # 净能量缺口分析 (发电机贡献 + 电池最大可用)
        total_energy_supplied = e_gen_total_electric + e_batt_usable
        unmet_energy_j = max(0.0, e_req_total - total_energy_supplied)

        # 巡航功率缺口与电池支撑时间
        p_deficit_cruise = max(0.0, p_electric_cruise - self.hy.genset_continuous_power_w)
        batt_endurance_cruise_s = e_batt_usable / p_deficit_cruise if p_deficit_cruise > 0 else float("inf")

        # 6. 起飞总重与 MTOW 闭合判定
        # 起飞时必须携带全部燃油: TOW = Dry + Fuel
        actual_takeoff_mass_kg = dry_takeoff_mass + fuel_burned_kg
        mtow_deficit_kg = actual_takeoff_mass_kg - self.ac.mtow_kg

        feasible = (mtow_deficit_kg <= 0.0) and (unmet_energy_j <= 0.0)

        return {
            "dry_powertrain_mass_kg": dry_powertrain_mass,
            "dry_takeoff_mass_kg": dry_takeoff_mass,
            "p_electric_cruise_mw": p_electric_cruise / 1e6,
            "p_electric_loiter_mw": p_electric_loiter / 1e6,
            "e_req_total_mj": e_req_total / 1e6,
            "e_gen_total_electric_mj": e_gen_total_electric / 1e6,
            "e_batt_usable_mj": e_batt_usable / 1e6,
            "fuel_burned_kg": fuel_burned_kg,
            "fuel_energy_required_mj": fuel_energy_required_j / 1e6,
            "unmet_energy_mj": unmet_energy_j / 1e6,
            "p_deficit_cruise_mw": p_deficit_cruise / 1e6,
            "batt_endurance_cruise_min": batt_endurance_cruise_s / 60.0,
            "actual_takeoff_mass_kg": actual_takeoff_mass_kg,
            "mtow_deficit_kg": mtow_deficit_kg,
            "feasible": feasible,
        }

    def print_hybrid_report(self, r: Dict[str, Any]):
        print("\n" + "=" * 95)
        print("          EMB-135 串联混合动力 (SERIES HYBRID) 500 NM 任务评估报告")
        print("=" * 95)

        print("\n[1. 质量与构型分解 (Mass Architecture)]")
        print(f"  - 扣除原发动机后机体空重       : {self.ac.base_mass_after_engine_removal_kg:,.1f} kg")
        print(f"  - 目标商载 (4198 kg)           : {self.ac.nominal_payload_kg:,.1f} kg")
        print(f"  - 燃气涡轮发电机 (2.0 MW 恒定) : {self.hy.genset_mass_kg:,.1f} kg")
        print(f"  - 推进电机 (8.0 MW 峰值轴功率) : {self.hy.motor_mass_kg:,.1f} kg")
        print(f"  - 缓冲电池组 (300 Wh/kg, 80%)  : {self.hy.battery_mass_kg:,.1f} kg")
        print(f"  - 动力改装总干重 (Dry Retrofit): {r['dry_powertrain_mass_kg']:,.1f} kg (恰好占满 3,802 kg 预算)")
        print(f"  - 零燃油起飞质量 (Zero-Fuel Mass): {r['dry_takeoff_mass_kg']:,.1f} kg (恰好达到 MTOW 19,000 kg)")

        print("\n[2. 能量流与功率匹配 (Power & Energy Balance)]")
        print(f"  - 巡航所需总电功率需求         : {r['p_electric_cruise_mw']:.3f} MW")
        print(f"  - 发电机净输出电功率           : {self.hy.genset_continuous_power_w / 1e6:.3f} MW (热效率 40%)")
        print(f"  - 巡航电功率缺口 (需电池补充)  : {r['p_deficit_cruise_mw']:.3f} MW")
        print(f"  - 缓冲电池组可用电能           : {r['e_batt_usable_mj']:,.1f} MJ ({r['e_batt_usable_mj']/3.6:,.1f} kWh)")
        print(f"  - 电池支撑巡航放电时间         : {r['batt_endurance_cruise_min']:.1f} 分钟 (随后电池耗尽!)")
        print(f"  - 任务总需求电能 (巡航+45m备用): {r['e_req_total_mj']:,.1f} MJ")
        print(f"  - 发电机全程供电总量           : {r['e_gen_total_electric_mj']:,.1f} MJ")
        print(f"  - 任务最终未满足电能缺口       : {r['unmet_energy_mj']:,.1f} MJ ({r['unmet_energy_mj']/r['e_req_total_mj']*100:.1f}%)")

        print("\n[3. 燃油消耗与起飞质量闭环 (Fuel Burn & MTOW Closure)]")
        print(f"  - 全程消耗航空煤油质量         : {r['fuel_burned_kg']:,.1f} kg ({r['fuel_burned_kg']/0.8:,.1f} 升)")
        print(f"  - 燃油释放总化学能             : {r['fuel_energy_required_mj']:,.1f} MJ")
        print(f"  - 实际起飞总重 (干重 + 燃油)   : {r['actual_takeoff_mass_kg']:,.1f} kg")
        print(f"  - 结构最大起飞总重 (MTOW)      : {self.ac.mtow_kg:,.1f} kg")
        print(f"  - 超出 MTOW 质量缺口           : +{r['mtow_deficit_kg']:,.1f} kg (超限比例: +{r['mtow_deficit_kg']/self.ac.mtow_kg*100:.2f}%)")

        print("\n[4. 最终系统工程判定 (System Verdict)]")
        if r["feasible"]:
            print("  >>> 判定结论: 【 FEASIBLE_UNDER_HYBRID_ASSUMPTIONS 】")
        else:
            print("  >>> 判定结论: 【 INFEASIBLE_UNDER_CURRENT_HYBRID_PARAMETERS 】")
            print("  >>> 致命物理瓶颈总结:")
            print(f"      1. [起飞总重超限] 改装干重已占满全部 3,802 kg 预算，携带的 {r['fuel_burned_kg']:,.1f} kg 燃油直接造成起飞总重超标！")
            print(f"      2. [发电机功率不足] 2.0 MW 发电机无法维持 4.21 MW 巡航需求，1,302 kg 缓冲电池在第 {r['batt_endurance_cruise_min']:.1f} 分钟耗尽，")
            print(f"         随后动力不足，无法维持平飞，任务中断且尚有 {r['unmet_energy_mj']:,.1f} MJ 电能未满足！")
        print("=" * 95)


# =====================================================================
# 4. 主执行入口
# =====================================================================

if __name__ == "__main__":
    # 执行 1: 纯电三维敏感性分析
    analyzer = SensitivityAnalyzer()
    analyzer.run_all_sweeps(cruise_speed_mps=230.0)

    # 执行 2: 串联混合动力求解
    hybrid_solver = HybridMissionSolver()
    hybrid_result = hybrid_solver.evaluate_hybrid_mission(range_nm=500.0, cruise_speed_mps=230.0)
    hybrid_solver.print_hybrid_report(hybrid_result)