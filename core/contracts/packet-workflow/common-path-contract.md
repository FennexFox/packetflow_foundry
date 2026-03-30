# Common Path Contract

This contract is used only when the `packet-heavy-orchestrator` overlay is selected.
It is not the blanket default.

Shared rules:
- local synthesis should complete from `global_packet.json`, `synthesis_packet.json`, and at most one focused packet reread on the common path
- raw rereads remain exception-only
- packet insufficiency on the common path is a failure, not a reason to guess
- runtime metadata stays in runtime packets
- token-efficiency and packet-sizing metrics stay in evaluation artifacts such as `packet_metrics.json`

Profiles may opt into this contract.
They must not redefine its meaning.
