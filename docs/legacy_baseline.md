# Legacy ACO audit baseline

## Scope and provenance

This record uses only the approved Stage 0 audit and the committed read-only
hash manifest. The historical ACO source was not executed, imported, or copied
（未执行、导入或复制）during Stage 3.

- Manifest-relative path: `实习/过程/第6周7.31-8.6/ACO.py`
- File SHA-256: `02b8da882eb5b307592cc4e99b20f7f96320e414e7225f214da870857ccbbfa1`
- Legacy manifest SHA-256: `f534b2543beb31e8f0253001b96494b0086b4b085a340d8d4ae4d33e10c91e8e`

## Audited defects excluded from the grid implementation

The approved design records that the historical file is a 48-city TSP example,
not a grid planner. Its formal search did not invoke a complete pheromone update,
so the regression target is **只挥发不学习**. The new edge-tensor deposit helper
also covers every forward and reverse path edge, preventing the historical target
described as **闭环边更新不完整**.

These observations define regression targets only. No historical call chain,
source fragment, data, or executable artifact is part of the new implementation.

## Read-only protection baseline

- Regular files: 75
- Subdirectories: 21
- Total bytes: 74,097,025
- The committed `legacy_hashes.before.sha256` manifest remains the only formal
  baseline; the final after-manifest is reserved for S8-T06.
