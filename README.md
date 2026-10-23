# All-Electric Aircraft Retrofit Feasibility

A Python-based engineering tool for evaluating whether
existing aircraft designs can be converted to fully
electric operation.

## Features
- Mass and weight constraint evaluation
- Battery energy and power analysis
- Mission range assessment
- Sensitivity analysis

## Project Status
Preliminary engineering screening tool.
Not certified aircraft design software.

## Development Notes
This project was developed with AI assistance.
The framework is intended for preliminary engineering
screening of existing aircraft converted to all-electric
operation.

Model assumptions, input data, calculations, and
results should be independently reviewed and validated.


## How to Use

### Requirements
- Python 3 installed.
- No additional package installation is required if the project uses only the Python standard library.

### 1. Prepare the aircraft input

The project includes `data/Json_template.json`, which contains an EMB-135 baseline configuration with a mixture of engineering inputs and assumed parameters.

Review the input values and their data-status fields before interpreting the results. Some values are assumptions rather than verified aircraft data.

For a separate aircraft configuration, create a copy of the JSON template and edit the parameters to match the aircraft being evaluated. Preserve the original template as a reference.

### 2. Run the evaluation

Open a terminal in the project root directory.

**Option A — Readable report (default)**

```bash
python src/submit_candidate.py data/Json_template.json
```

This validates the JSON input and prints a readable engineering evaluation report.

**Option B — Full report**

```bash
python src/submit_candidate.py data/Json_template.json --full
```

This prints the detailed evaluation report followed by the readable report.

Replace the input path with the path to your own aircraft configuration when evaluating a modified or different design.

### 3. Understand the results

The evaluator reports its findings against the constraints implemented in the model, including aircraft mass, propulsion power, battery energy, mission range, and reserve requirements.

Results depend on the input data and engineering assumptions. A positive feasibility result is not proof of flight safety, airworthiness, or regulatory compliance.

### Project Scope

This framework is intended for preliminary engineering screening of existing aircraft converted to fully electric operation. It does not constitute a certified aircraft design or certification assessment.