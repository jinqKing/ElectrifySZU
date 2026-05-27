"""Power Archive — persistent storage for campus electricity data.

Modules:
    mapping_repo    – room-to-internal-ID cache (avoids repeated discovers)
    snapshot_repo   – snapshot/detail ingestion and querying
    collector       – unified collection engine (dorm + apartment)
    tasks           – collection-task scheduling and lifecycle
    cli             – standalone CLI for interactive / batch / backfill ops
    seed_mappings   – one-shot seed: discover roomIDs from subscriptions
"""
