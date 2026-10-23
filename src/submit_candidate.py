import json
import sys
import os
import math
import dataclasses
import traceback

# Import the FROZEN engine (Ensure DesignEvaluator.py is in the same folder)
try:
    from DesignEvaluator import DesignInput, InputParam, DataStatus, MissionEvaluator, print_evaluation_report
    from readable_report import print_readable_report
except ImportError:
    print("CRITICAL ERROR: Could not import DesignEvaluator.py.")
    print("Make sure submit_candidate.py and DesignEvaluator.py are in the same directory.")
    sys.exit(1)

def is_finite_number(value):
    """Safely checks if a value is a finite number, preventing OverflowErrors on huge ints."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False

def load_candidate_from_json(filepath: str):
    """Safely parses a JSON file, validates schema, and converts to DesignInput."""
    if not os.path.exists(filepath):
        return None, [f"File not found -> {filepath}"]

    # 1. Robust File I/O
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"Invalid JSON syntax: {e}"]
    except Exception as e:
        return None, [f"Failed to read file (OS Error/Permission): {e}"]

    if not isinstance(data, dict):
        return None, ["JSON top-level must be a dictionary object (e.g., {...})."]

    errors = []
    
    # 2. Validate design_name explicitly
    design_name = data.get("design_name")
    if not isinstance(design_name, str) or not design_name.strip():
        errors.append("Field 'design_name' must be a non-empty string.")

    # 3. Map fields and enforce strict schema
    input_fields = {f.name: f for f in dataclasses.fields(DesignInput)}
    valid_keys = set(input_fields.keys())
    kwargs = {}

    # Check for unexpected fields (Strict Rejection to prevent silent typos)
    for key in data.keys():
        if key not in valid_keys and key != "design_name":
            errors.append(f"Unknown field '{key}' found in JSON. Check for typos. (Submission rejected).")

    for field_name, field_def in input_fields.items():
        if field_name == "design_name":
            continue

        # Check for missing required fields
        if field_name not in data:
            if field_def.default is dataclasses.MISSING and field_def.default_factory is dataclasses.MISSING:
                errors.append(f"Missing required field: '{field_name}'")
            continue

        field_data = data[field_name]

        # Handle optional cl_max_clean explicitly if None
        if field_name == "cl_max_clean" and field_data is None:
            kwargs[field_name] = None
            continue

        if not isinstance(field_data, dict):
            errors.append(f"Field '{field_name}' must be a JSON object ({{value, units, status, ...}}).")
            continue

        # 4. Validate nested data types
        
        # A. Value check (Must be finite number, reject bool/string/overflow)
        value = field_data.get("value")
        if not is_finite_number(value):
            errors.append(f"Field '{field_name}': 'value' must be a finite number.")

        # B. Units check (Must be non-empty string)
        units = field_data.get("units", "")
        if not isinstance(units, str) or not units.strip():
            errors.append(f"Field '{field_name}': 'units' must be a non-empty string.")

        # C. Status check
        status_str = field_data.get("status", "")
        if not isinstance(status_str, str):
            errors.append(f"Field '{field_name}': 'status' must be a string.")
            status_enum = None
        else:
            try:
                status_enum = DataStatus[status_str]
            except KeyError:
                errors.append(f"Field '{field_name}': Invalid status '{status_str}'. Must be SOURCED, ESTIMATED, or ASSUMED.")
                status_enum = None

        # D. Source check (String, and required if SOURCED)
        source = field_data.get("source", "")
        if not isinstance(source, str):
            errors.append(f"Field '{field_name}': 'source' must be a string.")
        elif status_str == "SOURCED" and not source.strip():
            errors.append(f"Field '{field_name}': 'source' cannot be empty when status is SOURCED.")

        # E. Description check
        description = field_data.get("description", "")
        if not isinstance(description, str):
            errors.append(f"Field '{field_name}': 'description' must be a string.")

        # 5. Construct InputParam if nested types are clean
        if (is_finite_number(value) and
            isinstance(units, str) and units.strip() and
            status_enum is not None and
            isinstance(source, str) and (status_str != "SOURCED" or source.strip()) and
            isinstance(description, str)):
            
            try:
                kwargs[field_name] = InputParam(
                    value=value,
                    units=units,
                    status=status_enum,
                    source=source,
                    description=description
                )
            except Exception as e:
                errors.append(f"Field '{field_name}': Failed to construct InputParam -> {e}")

    if errors:
        return None, errors

    # 6. Construct final DesignInput
    try:
        design = DesignInput(design_name=design_name, **kwargs)
        return design, []
    except TypeError as e:
        return None, [f"Failed to construct DesignInput (missing fields or type mismatch): {e}"]

def main():
    args = [a for a in sys.argv[1:] if a != "--full"]
    if len(args) != 1:
        print("Usage: python submit_candidate.py <path_to_candidate.json> [--full]")
        print("Example: python submit_candidate.py candidate_lambert.json")
        sys.exit(1)

    json_path = args[0]
    print(f"Loading candidate design from: {json_path} ...")
    
    design, errors = load_candidate_from_json(json_path)
    
    if errors:
        print("\n" + "!" * 60)
        print("           INPUT INVALID: JSON SCHEMA / FORMAT ERRORS")
        print("!" * 60)
        for err in errors:
            print(f"  - {err}")
        print("\nEvaluation aborted. Please fix the JSON file and try again.")
        sys.exit(1)
        
    print("JSON successfully validated against strict schema.")
    print("Executing FROZEN MissionEvaluator...")
    print("\n")
    
    # Run the frozen physics engine
    try:
        report = MissionEvaluator.evaluate(design)
        if "--full" in sys.argv:
            print_evaluation_report(report)
        print_readable_report(report, design)
    except Exception as e:
        print("\nCRITICAL ERROR: The frozen evaluator crashed. This should not happen.")
        print(f"Error details: {e}")
        traceback.print_exc()
        sys.exit(2)

if __name__ == "__main__":
    main()