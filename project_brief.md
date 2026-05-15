# HYDRUS-1D Agent Project Brief

## Project goal

Build a local research assistant that can help generate, run, and analyse HYDRUS-1D simulations based on structured user input.

The first version should not be a fully autonomous agent. It should be a controlled workflow that can:

1. Read a user-defined model configuration from a JSON file.
2. Validate soil, boundary condition, time, and observation settings.
3. Generate the required HYDRUS-1D input files from templates.
4. Run HYDRUS-1D locally if the executable path is provided.
5. Read selected HYDRUS output files.
6. Produce plots and a short model summary.

## Development principle

The system must be transparent, reproducible, and safe.

Do not modify files outside this project folder.
Do not delete files unless explicitly requested.
Do not overwrite existing simulation folders without creating a backup.
Before making major changes, explain the planned file changes.

## First milestone

Create a minimal Python project with the following structure:

hydrus_1d_agent/
├── README.md
├── requirements.txt
├── config/
│   └── example_case.json
├── hydrus_agent/
│   ├── __init__.py
│   ├── schema.py
│   ├── validator.py
│   ├── input_writer.py
│   ├── runner.py
│   ├── output_reader.py
│   └── plotter.py
├── templates/
│   └── placeholder.txt
├── runs/
│   └── .gitkeep
└── tests/
    └── test_schema.py

## First technical requirement

The first working version should only read `config/example_case.json`, validate the configuration, and create a simulation folder under `runs/case_001/`.

It does not need to run HYDRUS yet.

## Example model configuration

The model configuration should include:

- project_name
- simulation_time
- soil_profile
- van Genuchten parameters
- initial condition
- upper boundary condition
- lower boundary condition
- observation depths
- output settings

## Coding style

Use Python.
Use pydantic for configuration validation.
Use pathlib for file paths.
Use clear error messages.
Keep each module small and readable.