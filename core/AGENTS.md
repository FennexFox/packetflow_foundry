# Core AGENTS

This subtree is the authoritative home for shared PacketFlow Foundry semantics.

Keep only cross-project behavior here:
- contracts
- templates
- default semantic values

Do not put these in `core/`:
- repo-specific paths
- one-project review doc ownership
- project-only worker routing
- consumer-specific prompt overlays

Change rules:
- define shared behavior changes in `core/` first
- update `builders/packet-workflow/` in the same change so the builder keeps consuming the new authoritative core
- update builder tests when contract, template, or default changes alter generated output

Boundary rules:
- `profile-boundary-contract.md` is authoritative for what can move into profiles
- `packet-heavy-orchestrator` is an additive opt-in overlay, not the blanket default
