# Approval-controlled release workflow

This foundation implements offline preparation and inspection only. It contains
no publisher, GitHub write adapter, credential injection, enabled GitHub Actions
workflow, timer or daemon. An approved operator publishes through a separately
scoped process. Model conclusions and `release_approved` fields are not authority
to publish. User approval must bind the concrete result.

1. The add-on developer freezes reviewed source in its independent repository;
   supplies repository/ref/commit, clean-state disposition, license notices,
   runtime-file allowlist, deterministic ZIP and source/file/ZIP SHA-256.
2. The tester supplies version/platform-specific static and native acceptance,
   warnings and limitations. The release reviewer independently inspects frozen
   bytes, dependency closure, rights and evidence. Packages with unresolved
   rights, runtime or release gates remain inadmissible to production.
3. The operator verifies and copies only approved ZIP/evidence into `incoming/`.
   `config/production.json` lists zip, sha256, review_record,
   review_record_sha256 and selected lanes. Review records contain package_sha256,
   runtime_files (relative path to SHA-256), source_repository, source_commit,
   release_approved, rights_approved, fixture_only=false and compatibility entries
   with static_accepted, runtime_accepted and evidence references. Evidence is
   human reviewed; booleans do not authenticate its claims.
   Ordinary new records use the version 2 [approval contract](APPROVAL-CONTRACT.md)
   and [schema](REVIEW-RECORD-SCHEMA.json): separately record rights review,
   owner acknowledgment, technical approval, runtime results/deferrals and final
   release approval. Legacy valid records retain their boolean contract. No
   acknowledgment or deferral replaces a required approval or completed test.
4. The manager builds local candidates, verifies catalogs/sidecars/dependencies,
   compares whole-site repeat builds, checks historical retention and root installer
   copy identity, qualifies Kodi directory discovery, and prepares
   a release plan containing exact package/feed hashes and intended actions.
   Independent reviewer freezes its approval against the plan and input hashes.
5. Before a new remote creation or promotion, review owner/name, visibility, branch policy,
   exact source snapshot, license/rights, reviewed bytes, proposed tag/assets,
   Pages source/path, retention/recovery plan and unresolved gates against explicit user approval.
6. Only after explicit approval may the operator create/push/tag/upload or
   deploy. Use protected environments with required human reviewers and prevent
   self-approval; keep default jobs read-only and credentials absent from PR jobs.
   Use manual dispatch for reviewed artifact promotion; never execute untrusted
   PR code with release secrets, and pin action dependencies to reviewed commits.
7. Stage/download-verify release assets before promoting catalogs. Pages static
   deployment should promote a coherent complete site. Verify public GET/HEAD,
   HTTPS certificate/redirect/MIME behavior, exact checksums and native Kodi
   installation/update behavior on separately authorized disposable targets.
8. Record the approved id/version/hash in `releases/manifest.json`, retain all
   historical ZIPs/records and back up approved site/ledger evidence. Future
   release plans bind the previous ledger and exact new bytes; never delete a
   published version or silently replace it. Content-addressed backups help
   restore coherent metadata. Catalog rollback does not automatically downgrade
   an already installed add-on. A corrective higher version or explicitly
   approved manual downgrade and profile backup may be required.

The optional future CI topology is `validate` (read-only, all PRs),
`prepare` (manual, no write credentials, creates candidate artifact),
`review` (human review of exact digest), `promote` (protected environment, exact
digest recheck, minimum scoped GitHub/Pages permissions), then `verify` and record.
This is a design, not an installed workflow or scheduled task.

Current local commands generate a dry-run plan with `publication_authorized=false`,
`remote_actions_executed=[]` and `live_https_verified=false`. Fixture outputs are
marked, use `qualification/` URLs and installer version 0.0.0, and must never be
included in a production deployment. Production's initial infrastructure version is 0.1.0. The user-authorized initial
source/Pages setup is separate from these offline tools; their dry-run authority
flags remain false. No real add-on release is approved by that setup.

## Private candidate qualification

Before rights/native approval, copy this source into an isolated staging area
without Git, agent configuration or existing distribution outputs. In that copy,
place only the allowlisted runtime ZIP and a truthful review record in `incoming/`.
Create ignored `config/candidate.json` using the production input schema and
proposed lanes. Keep `rights_approved`, `release_approved` and unobserved acceptance
false. Records must still bind the exact source commit, ZIP and every runtime
file; dependency, path, resource and manifest controls apply unchanged.

```sh
python3 -B scripts/repository.py build --profile candidate
python3 -B scripts/repository.py verify --profile candidate
python3 -B scripts/audit_candidate.py --profile candidate
python3 -B scripts/qualify.py --profile candidate
```

A structural PASS with release blockers does not make the package releasable.
The preview installer has private URLs and must not be installed or published.
If a retention ledger pins the current production installer, a preview with
different installer bytes fails closed; use a separately reviewed test repository
identity for any future native candidate-feed installation.
Do not create synthetic rights or runtime approvals for a real candidate. The
production checker accepts only a production plan, independently rechecks its
reviewed intake and ledger, and scans extracted runtime files as well as the
complete site. Candidate and fixture output must never be deployed.

After genuine approvals, production deterministic qualification is explicit:
`python3 -B scripts/qualify.py --profile production`. The default remains fixture
qualification for existing role tools. `check_publication.py --https` is a
read-only check of already promoted production bytes, including `.nojekyll`;
never use candidate data as a public HTTPS expectation. Ordinary approved
packages and historical downloads replace the initial installer-only assumptions.
Canonical ZIP order, 1980 timestamps and regular 0644 entries remain required by
the independent audit. Numeric x.y.z versions, file-based library declarations
and the existing external dependency-snapshot restriction remain unchanged.

Schema 3 / `unofficial-integration-v1` is an opt-in alternative only for an
independently developed package with supported package-distribution rights and
documented provider-service terms concerns. Follow the complete v3 contract: independently
review all distributed content/attribution and any applicable distribution or
operation authorization requirement; record separate service findings, owner
acknowledgment and owner distribution decision; bind bundled and release-facing
non-affiliation disclosures. Broad rights stay false/pending. Owner acceptance
supplies no provider authorization and cannot clear missing rights, attribution,
required tests or security/provenance issues. Only the contract's explicit
`provider_authorization_exception` may replace this repository's provider-authorization
gate: require an attributable owner acceptance, matching provider, inspected add-on
ID/version, frozen ZIP checksum, known terms concern and current expiry. Record
provider authorization as unverified and retain accepted findings as unresolved
in every plan and independent audit. This supplies no legal clearance. User-reported
runtime results retain their evidence and scope; required unknown/deferred tests
still block final release. Do not seek provider permission as an implicit prerequisite
of this owner-risk route.

Use a newly reviewed successor record and new intake digest only under separate
release authority. Upgrade builder/auditor/qualifier/preflight together and
regenerate the complete toolchain/schema-pinned plan. Check complete rendered
notice bytes and retained evidence digests/substance before final approval.
Candidate-profile qualification remains private and cannot authorize publication.

The separate schema 3 `unofficial-integration-initial-release-v1` policy may admit
named initial-release runtime coverage limitations. Retain unobserved/environment
observations, scoped supplemental evidence, false runtime acceptance and deferred
outstanding scenario IDs. Require exact artifact/source/lane binding, checked
first-release history, expiring owner acceptance, independent core native/offline
verification with no known security defect, all-risk acknowledgment, and a
separate final owner decision binding the complete exception digest. Rights,
archive/provenance, security, provider-risk, audit and publication controls remain
intact. Never fabricate owner decisions or convert failed/unknown tests to PASS
for a dry run. Truthful pending real records use private candidate qualification;
positive synthetic fixtures exercise eligible production admission without
supplying any actual release approval.


## Bootstrap promotion and future installers

The standard public entry point remains the root HTTPS File manager source.
Each build derives its sole installer link from the configured installer version,
creates byte-identical versioned root mirrors and SHA-256 sidecars, and retains
older installer copies. Ordinary add-ons remain in version-compatible catalogs
with native categories, dependencies and updates. No per-add-on bootstrap links
are added when a new independently developed add-on is admitted.

Review root copies as additional site files in the complete release plan. Their
canonical ZIP hashes, existing release assets, review records, catalogs and
retention ledger must remain unchanged for an index-only release. The independent
auditor reconstructs the page and permitted mirrors from reviewed inputs; a
matching forged plan alone cannot admit extra files or altered copies. Required
provider/runtime disclosures remain visible and unchanged in meaning.

This bootstrap implementation grants no publication authority and requires no
new package release. Approve an exact source/site digest before Pages promotion.
Do not run `check_publication.py --https` against undeployed expected bytes and
report it as a pass. After an approved promotion, verify public HTTPS and perform
the separately authorized [native acceptance plan](NATIVE-ACCEPTANCE.md).

## Local D1/D2 publication simulation

The [local publication implementation](PUBLICATION-OPERATOR.md) adds frozen
P/R/E proposals, explicitly simulated approvals and a file-backed fake state
machine. It reuses these release gates and cannot publish, change an existing
approval, or promote a candidate into production. Its successful synthetic cases
are not native acceptance, GitHub enforcement tests or production authorization.
Current real proposals retain missing-input, compatibility and decision blockers.
