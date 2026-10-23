# Mind Twin Sandbox: Cognitive Digital Twin

This directory houses the isolated sandbox for Gemini's next-generation cognitive architecture.

## Architectural Principles
1. **Mathematical Hypergraph**: Directed Attributed Hypergraph $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{W}, \mathcal{T})$ with multi-source, multi-target causal contexts.
2. **Associative Spreading Activation**: ACT-R cognitive memory dynamics with Ebbinghaus retention decay and Hebbian plasticity.
3. **Complementary Learning Systems (CLS)**: Fast episodic ingestion (hippocampal) with background distillation into long-term architectural invariants (neocortical).
4. **Zero-Production Risk**: Standalone offline testing harness. Does not modify or bind to active sockets or live chat state.

## Directory Structure
- `core/`: Core mathematical primitives (`hypergraph.py`, `activation.py`, `cls_consolidator.py`).
- `data/`: Point-in-time snapshots of live session metadata, segments, and SQLite memory (read-only reference).
- `tests/`: Automated deterministic test suite verifying mathematical properties and retention dynamics.
- `harness/`: Offline simulation runners and probe scripts that print diagnostics to feed.
