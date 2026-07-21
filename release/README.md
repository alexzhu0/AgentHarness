<!-- markdownlint-disable MD013 -->

# AgentHarness release and milestone history

This directory separates three kinds of records:

- **versioned GitHub release notes** describe a published source release;
- **historical GitHub milestone records** bind a curated retrospective note to
  an immutable commit without claiming that a package was published then; and
- **internal milestone or handoff records** preserve planning/review evidence
  that cannot be mapped truthfully to a same-date complete commit.

The date in a filename is an **evidence or review date** unless the record says
it is a published version. It is not automatically a publication date.

## Milestone phases

| Phase | Evidence dates | Scope | Immutable checkpoint |
| --- | --- | --- | --- |
| 1. Asset foundation | 2026-06-13 | Initial policy, governance, safety, schema, and prompt assets | `8a657d2` |
| 2. Evidence control-plane foundation | 2026-06-15 to 2026-06-24 | File bus, gates, approvals, preflight, handoff, export, digest, glossary | `78b0475`, `cd27d11` |
| 3. Enterprise audit and reviewer readiness | 2026-06-29 to 2026-07-06 | Audit report/checklist, readback, reproducible demo, reviewer workflow | `c510864` through `1b5e725` |
| 4. Pi contract and block-only shadow integration | 2026-07-07 to 2026-07-16 | Static contracts, block-only bridge, evidence integrity, shadow verification | `d9c1c8e`, `5ff9bef` |
| 5. Finite methodology-permit evidence pilot | 2026-07-20 | Exact, single-use evidence decision and source prerelease | `12ba939` (`v0.2.0-alpha.1`) |

## Record inventory

| Record | Type | Evidence basis | GitHub release body |
| --- | --- | --- | --- |
| [`2026.07.20.md`](./2026.07.20.md) | Versioned source prerelease | Release commit, merged `main`, annotated tag | Yes: `v0.2.0-alpha.1` |
| [`2026.07.13.md`](./2026.07.13.md) | No-release handoff snapshot | Review evidence dated 2026-07-13; committed 2026-07-16 | No |
| [`2026.07.07.md`](./2026.07.07.md) | Historical review-reset snapshot | Same-day repository checkpoint plus later supersession note | Yes: curated historical prerelease |
| [`2026.07.06.md`](./2026.07.06.md) | Historical milestone record | External planning evidence and later aggregate commits | No |
| [`2026.07.05.md`](./2026.07.05.md) | Historical milestone record | External planning evidence and same/later-day commits | No |
| [`2026.07.03.md`](./2026.07.03.md) | Historical milestone record | External planning evidence and later aggregate commits | No |
| [`2026.07.02.md`](./2026.07.02.md) | Historical milestone record | External planning evidence and later aggregate commit | No |
| [`2026.07.01.md`](./2026.07.01.md) | Historical milestone record | External planning evidence and later aggregate commit | No |
| [`2026.06.29.md`](./2026.06.29.md) | Historical milestone record | External planning evidence and later aggregate commit | No |
| [`2026.06.24.md`](./2026.06.24.md) | Historical milestone record | Two same-day commits plus later T016/T017 packaging | No |
| [`2026.06.22.md`](./2026.06.22.md) | Historical milestone record | External planning evidence; packaged 2026-06-24 | No |
| [`2026.06.18.md`](./2026.06.18.md) | Historical milestone record | External planning evidence; packaged 2026-06-24 | No |
| [`2026.06.15.md`](./2026.06.15.md) | Historical milestone record | External planning evidence; packaged 2026-06-24 | No |
| [`2026.06.13.md`](./2026.06.13.md) | Historical asset-baseline record | Same-day git history through `8a657d2` | Yes: curated historical prerelease |

The records marked **No** are intentionally not one-to-one GitHub Releases.
Their full stated scope did not exist in a complete commit on the filename date.
Creating tags for them would manufacture a false release chronology.

## Public GitHub mapping

The truthful public mapping is:

- `history-2026.06.13` at `8a657d2609eb58dd32dd18e702b407cab8c1d4bf`;
- `history-2026.07.07` at `d9c1c8e0a6a171dada07d42979802cba982915ce`;
- `v0.2.0-alpha.1` at `12ba9393ab85ebc511ab875df52ed93ddccfd5c4`.

Historical entries are prereleases with no assets and do not become GitHub's
Latest release. The alpha release is also a source prerelease with no PyPI or
npm publication.

## Current product boundary

AgentHarness is a pre-execution evidence control-plane. Its repository outputs
remain evidence records, including `result_status: not_executed` where the
contract requires it. AgentHarness does not itself execute Pi or Win9 tools.

Later cross-repository pilots demonstrated separately bounded Pi-side behavior,
including one finite pinned local read-only action. Those controls belong to the
external Pi runtime TCB; they do not convert AgentHarness evidence into general
runtime authorization, sandboxing, identity, signing, or safe-to-execute
approval.
