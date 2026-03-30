# agent-profile-runtime

Provider-agnostic runtime for agent profile homes, session/run execution, and MCP-aware config management.

## Overview

This repository hosts the extracted runtime layer for managing agent profile directories, provider-specific config homes, session lifecycle state, run execution, and MCP-backed configuration composition across multiple agent CLIs.

The project is intended to remain independent from any single upstream application so it can be reused as a standalone library or imported as a submodule by larger systems.

## Repository Layout

- `src/`: source code
- `tests/`: automated tests
- `docs/`: long-lived reusable documentation
- `dev_docs/`: local development notes and design records
- `data/`: local data and intermediate artifacts
- `configs/`: local configuration files and examples

## Status

This repository is currently scaffolded for design and incremental implementation.
