"""
readable_report.py
Readable report formatter for the FROZEN DesignEvaluator.
Does not modify or re-implement any physics; it only presents the results.
ASCII-only output so it prints correctly on any console.
"""
from DesignEvaluator import EvaluationStatus, ConstraintCode

W = 78


def _line(ch="-"):
    print(ch * W)


def _title(text):
    print()
    _line("=")
    print(f" {text}")
    _line("=")


def _row(label, value, note=""):
    print(f"  {label:<38}{value:>18}   {note}")


def _kwh(j):
    return j / 3.6e6


def print_readable_report(rep, design):
    v = lambda p: float(p.value)
    failed = {f.code: f for f in rep.failed_constraints}

    print()
    _line("#")
    print(f"  AIRCRAFT DESIGN EVALUATION: {rep.design_name}")
    _line("#")

    # Invalid input: nothing else is meaningful
    if rep.verdict == EvaluationStatus.INPUT_INVALID:
        _title("INPUT ERRORS")
        for e in rep.input_validation_errors:
            print(f"  - {e}")
        _title("CONCLUSION")
        print("  RESULT: NOT EVALUATED (input invalid). Fix the errors above and rerun.")
        _line("=")
        return

    # ---- 1. Mass ----
    _title("1. MASS BUDGET")
    _row("Base airframe (no engines/fuel)", f"{v(design.base_mass_kg):,.0f} kg")
    _row("Payload", f"{v(design.payload_kg):,.0f} kg")
    _row("Battery", f"{v(design.battery_mass_kg):,.0f} kg")
    _row("Motor", f"{v(design.motor_mass_kg):,.0f} kg")
    _row("Additional powertrain", f"{v(design.additional_powertrain_mass_kg):,.0f} kg")
    _line()
    _row("Takeoff mass", f"{rep.actual_takeoff_mass_kg:,.0f} kg")
    _row("MTOW limit", f"{rep.mtow_limit_kg:,.0f} kg")
    _row("Margin", f"{rep.available_mass_margin_kg:+,.0f} kg",
         "OK" if rep.available_mass_margin_kg >= 0 else "OVER MTOW")

    # ---- 2. Cruise ----
    _title("2. CRUISE CONDITION")
    _row("Lift coefficient CL", f"{rep.cl_cruise:.3f}")
    _row("Drag coefficient CD", f"{rep.cd_cruise:.4f}")
    _row("Lift-to-drag L/D", f"{rep.lift_to_drag:.2f}")
    _row("Drag", f"{rep.drag_n/1e3:,.2f} kN")
    _row("Shaft power", f"{rep.shaft_power_w/1e6:.3f} MW")
    _row("Electric power (cruise)", f"{rep.electric_power_w/1e6:.3f} MW")
    _row("Electric power (peak demand)", f"{rep.peak_electric_power_demand_w/1e6:.3f} MW",
         "= 2 x cruise (fixed in evaluator)")

    # ---- 3. Energy ----
    _title("3. ENERGY (kWh)")
    usable = _kwh(rep.usable_battery_energy_j)
    need = _kwh(rep.total_mission_energy_j)
    _row("Usable battery energy", f"{usable:,.1f} kWh")
    _row("Cruise leg needs", f"{_kwh(rep.cruise_energy_j):,.1f} kWh",
         f"({v(design.target_range_nm):,.0f} nm)")
    _row("Reserve loiter needs", f"{_kwh(rep.loiter_reserve_energy_j):,.1f} kWh",
         f"({v(design.reserve_loiter_time_s)/60:,.0f} min)")
    _line()
    _row("Total needed", f"{need:,.1f} kWh")
    _row("Surplus / (shortfall)", f"{usable - need:+,.1f} kWh",
         "OK" if usable >= need else "SHORT")
    _row("Battery covers", f"{100*usable/need:,.1f} %" if need > 0 else "n/a", "of mission energy")

    # ---- 4. Range ----
    _title("4. RANGE")
    _row("Zero-reserve range (all energy)", f"{rep.zero_reserve_theoretical_range_nm:,.1f} nm")
    _row("Range with reserve kept",
         f"{rep.energy_limited_range_nm:,.1f} nm" if rep.energy_limited_range_nm is not None else "none",
         "" if rep.energy_limited_range_nm is not None else "reserve alone exceeds battery")
    _row("Required range", f"{v(design.target_range_nm):,.0f} nm")

    # ---- 5. Constraint checklist ----
    _title("5. CONSTRAINT CHECKLIST")
    p_sh, p_el = rep.shaft_power_w, rep.electric_power_w
    checks = [
        (ConstraintCode.MTOW_LIMIT, "Takeoff mass <= MTOW",
         rep.actual_takeoff_mass_kg, rep.mtow_limit_kg, "kg", 0),
        (ConstraintCode.CL_MAX_STALL, "Cruise CL <= CL_max (clean)",
         rep.cl_cruise, v(design.cl_max_clean) if design.cl_max_clean else None, "", 3),
        (ConstraintCode.MOTOR_CONTINUOUS_POWER, "Motor continuous >= shaft power",
         p_sh / 1e6, v(design.motor_continuous_rating_w) / 1e6, "MW", 2),
        (ConstraintCode.MOTOR_PEAK_POWER, "Motor peak >= 2 x shaft power",
         2 * p_sh / 1e6, v(design.motor_peak_rating_w) / 1e6, "MW", 2),
        (ConstraintCode.BATTERY_CONTINUOUS_POWER, "Battery continuous >= electric",
         p_el / 1e6, v(design.continuous_discharge_power_limit_w) / 1e6, "MW", 2),
        (ConstraintCode.BATTERY_PEAK_POWER, "Battery peak >= 2 x electric",
         2 * p_el / 1e6, v(design.peak_discharge_power_limit_w) / 1e6, "MW", 2),
        (ConstraintCode.MISSION_ENERGY, "Battery energy >= cruise + reserve",
         need, usable, "kWh", 1),
        (ConstraintCode.RESERVE_LOITER_ENERGY, "Battery energy >= reserve alone",
         _kwh(rep.loiter_reserve_energy_j), usable, "kWh", 1),
    ]
    print(f"  {'Status':<8}{'Check':<38}{'Required':>12}{'Available':>12}")
    _line()
    for code, name, req, cap, unit, nd in checks:
        if code == ConstraintCode.CL_MAX_STALL and cap is None:
            st, r, c = "????", f"{req:.3f}", "not given"
        else:
            st = "FAIL" if code in failed else "PASS"
            r, c = f"{req:,.{nd}f}", f"{cap:,.{nd}f}"
        print(f"  [{st}]  {name:<38}{r:>12}{c:>12} {unit}")

    # ---- 6. Warnings ----
    _title("6. ATTENTION POINTS")
    warns = []
    if v(design.propulsive_efficiency) >= 0.99:
        warns.append("propulsive_efficiency is ~1.0 (not physical); real value is ~0.8-0.9.")
    if v(design.inverter_efficiency) >= 0.99:
        warns.append("inverter_efficiency is ~1.0 (idealized); real value is ~0.95-0.98.")
    if v(design.additional_powertrain_mass_kg) == 0:
        warns.append("additional_powertrain_mass_kg = 0 (cabling/cooling/mounting ignored).")
    if 0 <= rep.available_mass_margin_kg < 100:
        warns.append(f"Mass margin is only {rep.available_mass_margin_kg:,.0f} kg; any added mass breaks MTOW.")
    for nm, p in vars(design).items():
        if nm != "design_name" and p is not None and p.status.value == "SOURCED" \
                and "replace" in p.source.lower():
            warns.append(f"{nm} is SOURCED but source is still a placeholder.")
    warns.append("Climb energy to cruise altitude is NOT modeled (can be a large share of the battery).")
    for w in warns:
        print(f"  ! {w}")

    # ---- Conclusion ----
    _title("CONCLUSION")
    if rep.verdict == EvaluationStatus.FEASIBLE_UNDER_ASSUMPTIONS:
        print("  RESULT:  FEASIBLE  (under the stated assumptions)")
        print(f"  All modeled constraints pass. Range with reserve: "
              f"{rep.operationally_compliant_range_nm:,.1f} nm "
              f"(required {v(design.target_range_nm):,.0f} nm).")
    elif rep.verdict == EvaluationStatus.UNRESOLVED:
        print("  RESULT:  UNRESOLVED  (not confirmed feasible)")
        print("  All evaluated constraints pass, but cl_max_clean was not provided,")
        print("  so the stall check could not be completed.")
    else:
        print("  RESULT:  NOT FEASIBLE  (under the stated assumptions)")
        print(f"  {len(failed)} of 8 constraints failed:")
        for f in rep.failed_constraints:
            print(f"    - {f.code.value}")
        if ConstraintCode.MISSION_ENERGY in failed or ConstraintCode.RESERVE_LOITER_ENERGY in failed:
            dens = v(design.pack_specific_energy_wh_kg) * v(design.usable_dod) / 1000.0  # kWh/kg
            need_mass = need / dens if dens > 0 else float("nan")
            print(f"  Energy shortfall: {need - usable:,.0f} kWh. At the current pack density this")
            print(f"  needs about {need_mass:,.0f} kg of battery (vs {v(design.battery_mass_kg):,.0f} kg now),")
            print("  and more mass raises power demand further, so the real need is higher.")
            print(f"  Max range with reserve at current battery: "
                  f"{'none' if rep.energy_limited_range_nm is None else f'{rep.energy_limited_range_nm:,.0f} nm'}"
                  f" (zero-reserve: {rep.zero_reserve_theoretical_range_nm:,.0f} nm).")
        print("  Options: shorter range, smaller reserve, higher Wh/kg, or a different concept.")
    _line("=")
    print("  Note: 'SOURCED' is declared by the submitter, not verified by the evaluator.")
    _line("=")
