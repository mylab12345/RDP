# ADR 0002: Durable private state writes

- **Status:** Accepted
- **Date:** 2026-09-07

## Context

Sessions, settings, snippets, and the encrypted vault each implemented their
own temporary-file replacement. The variants differed in permissions and
cleanup and did not flush data before rename. Paramiko's known-hosts serializer
wrote the trust file in place. A crash or full filesystem could therefore
publish incomplete state or erase host trust, while future fixes had to be
replicated across stores.

## Decision

All replaceable application state uses `core.persistence`:

1. create a temporary file in the destination directory;
2. apply the requested mode before writing (`0600` by default);
3. serialize, flush, and `fsync` the file;
4. atomically `os.replace` the destination;
5. best-effort `fsync` the parent directory on POSIX;
6. remove the temporary file on every pre-commit failure.

`atomic_write_via_path` provides the same transaction for third-party APIs that
require a filename, currently Paramiko `HostKeys.save`.

## Consequences

- Persisted JSON/encrypted formats do not change.
- Readers observe either the old complete file or the new complete file.
- Sensitive content is never temporarily group/world readable.
- Writes can be marginally slower because they are durable; these files are
  small and user-triggered, so correctness dominates throughput.
- An error after atomic replacement but during directory sync is treated as
  committed; unsupported directory fsync is deliberately best effort.

## Verification

`tests/test_core_persistence.py` injects replacement and serializer failures,
checks old-file preservation/temp cleanup/mode, and round-trips every migrated
store. Existing security tests continue to assert private state permissions.
