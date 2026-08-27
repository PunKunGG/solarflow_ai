# SolarFlow AI — AI-Driven Solar Architecture Optimization

Prototype workflow for EGAT Circular Innovation Challenge.

## Product architecture
1. Product 1 — AI Simulation & Optimization Platform
   - MEEP: electromagnetic/photon simulation
   - Solcore: solar-cell / semiconductor modelling
   - DEVSIM: semiconductor device PDE/TCAD verification
   - Python optimizer: searches geometry/design space
   - OpenAI: research orchestration, experiment planning, result interpretation
2. Product 2 — Hardware fabrication
   - Convert selected geometry into a manufacturable physical coupon
   - Control vs AI-designed treatment sample
3. Product 3 — Solar integration / pilot
   - Integrate treatment with a compatible module
   - A/B testing and field validation

## Important scientific scope
This repository does NOT claim that the concept already increases efficiency. The numerical and experimental results must be generated and validated. The first goal is a reproducible proof-of-physics workflow.

## First experiment
Compare a flat silicon surface with a simple periodic surface texture using MEEP, then use the optical result to inform solar-cell modelling.

## Current environment note
The container used to prepare this prototype does not include MEEP, Solcore, or DEVSIM. The package therefore includes real adapter scripts plus a dry-run surrogate so the workflow can be exercised immediately. Do not present surrogate outputs as physics results.
