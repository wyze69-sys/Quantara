# Quantara Professional Repository Presentation — Implementation Plan

**Status:** Approved — authorized for implementation
**Date:** 2026-08-24
**Project root:** `D:\PROJECT\Quantara`
**Repository:** `https://github.com/wyze69-sys/Quantara`
**Design specification:** `docs/superpowers/specs/2026-08-24-professional-repository-presentation-design.md`

## 1. Goal

Implement, verify, and publish the approved evidence-first GitHub presentation for Quantara without implying that the first market-data slice or any trading/ML capability is implemented.

The pass will add the approved README, visual assets, Apache-2.0 license, governance files, citation metadata, issue forms, and pull-request template; configure approved GitHub metadata and repository features; and verify the live public result.

## 2. Required execution prompt

A coding agent should need only this instruction:

> Read `docs/superpowers/plans/2026-08-24-professional-repository-presentation.md` and execute it exactly. Treat the linked design specification as authoritative. Stop at every stated blocker. Do not widen scope, fabricate verification, expose credentials, or claim completion without live GitHub read-back and visual evidence.

## 3. Approved inputs

- Presentation posture: evidence-first engineering with research transparency.
- License: Apache License 2.0.
- Public repository/citation identity: `wyze69-sys` as an entity/handle; do not publish the user's real name. All new Quantara commits use `258711354+wyze69-sys@users.noreply.github.com`; do not rewrite the already-public `ca00220` commit.
- Private Code of Conduct report contact: `linhrathhenry@gmail.com`, explicitly approved for publication in `CODE_OF_CONDUCT.md` only.
- Conduct-route evidence: the user confirmed a successful end-to-end test message receipt on 2026-08-24; re-confirm monitoring ownership before publication.
- Repository description:
  - `Foundation-stage design for correctness-first, point-in-time market-data and ML infrastructure.`
- Topics:
  - `quantitative-finance`
  - `market-data`
  - `data-engineering`
  - `reproducible-research`
  - `point-in-time-data`
  - `temporal-validation`
  - `data-provenance`
  - `cryptocurrency`
  - `bitcoin`
  - `binance-futures`
- Homepage: unset.
- Issues: enabled.
- Discussions: disabled.
- Wiki: disabled.
- Projects: disabled.
- Private vulnerability reporting: enable when supported and authorized.
- Default branch: `main`.

## 4. Observed starting state

Observed on 2026-08-24:

- Local approved design commit: `653a570` (refresh if the approved status-marker commit changes before plan approval).
- Remote `origin/main`: `ca00220`.
- Local `main` is one commit ahead of `origin/main`.
- Worktree is clean.
- Authenticated GitHub account: `wyze69-sys`.
- GitHub viewer permission: `ADMIN`.
- GitHub token scopes include `repo`.
- Repository is public.
- Description, homepage, and topics are empty.
- Issues are enabled.
- Discussions are disabled.
- Wiki is enabled.
- Private vulnerability reporting is supported but disabled.
- Existing public Open Graph image is GitHub's default generated repository image; no custom social preview was observed.
- Browser automation is not authenticated to GitHub settings.
- Available local tools include Node `v24.16.0`, npm `11.13.0`, Python `3.11.9`, and uv `0.11.15`.
- Inkscape, ImageMagick, librsvg, and `xmllint` are unavailable.
- Existing GitHub labels are the standard labels including `bug`, `documentation`, and `enhancement`; no data-quality or design labels exist.

These observations are not permanent assumptions. Task 1 must refresh them before mutation.

## 5. Scope and file boundaries

### 5.1 Implementation files

The implementation commit may add only:

```text
README.md
LICENSE
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
CITATION.cff
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/data_quality_incident.yml
.github/ISSUE_TEMPLATE/design_proposal.yml
.github/ISSUE_TEMPLATE/config.yml
.github/pull_request_template.md
docs/assets/quantara-header.svg
docs/assets/quantara-social-preview.svg
```

`docs/assets/quantara-social-preview.svg` is included because the social composition must remain reproducible even if GitHub upload is manual.

### 5.2 Non-repository artifacts

Temporary validation and rendering artifacts must live under:

```text
C:\Users\User\AppData\Local\Temp\quantara-repository-presentation\
```

They must not be staged or committed.

### 5.3 Forbidden changes

Do not modify:

- either approved design specification;
- `.gitignore`;
- existing Git history after final plan approval through amend, rebase, reset, squash, or force-push; the required new implementation and corrective/revert commits remain allowed;
- source/data/package/CI files;
- provider data or generated market artifacts;
- GitHub labels unless separately approved.

If a required change falls outside the allowlist, stop and report `BLOCKED` pending scope approval.

## 6. Completion states

- **COMPLETE:** every applicable approved repository file, validation, commit, push, metadata/setting mutation, private-reporting flow, live rendering check, issue-form behavior, and social-preview item is applied and verified.
- **INCOMPLETE:** safe repository work is published and verified, but one or more explicitly enumerated non-critical approved items remain unapplied or unverified. Examples include unavailable custom social-preview upload, authenticated live issue-form behavior, ordinary signed-in private-reporting verification, or a transient external-link check.
- **BLOCKED:** licensing rights, identity/contact approval, remote drift, permissions, private reporting, validation, security, irreversible-state concerns, or another safety constraint prevents safe continuation.

No unavailable or unverified approved item may be hidden inside a `COMPLETE` report. If the browser remains unauthenticated, the expected maximum state is `INCOMPLETE`.

## 7. Task 1 — Approval gate, refreshed state, and reversible transaction record

### Step 1.0: Create the temporary transaction directory

Create:

```text
C:\Users\User\AppData\Local\Temp\quantara-repository-presentation\
```

Do not create a repository-local scratch directory. Persist every following preflight result in this directory as it is gathered.

### Step 1.1: Verify approval and execution baseline

Before any implementation file generation or GitHub mutation:

1. Confirm the design header says `Approved — implementation not started`.
2. Confirm this plan header says `Approved — authorized for implementation` after user approval.
3. Record the exact design commit and plan commit IDs.
4. Record that adversarial design review passed, its findings were resolved, the user approved the final design, the plan review passed, and the user approved this plan.
5. Set `IMPLEMENTATION_BASE=$(git rev-parse HEAD)` and preserve it in the transaction record.
6. Confirm `git status --short` is empty.

If approval evidence is missing or contradictory, report `BLOCKED`. The plan must be approved and committed before this execution task begins.

### Step 1.1a: Verify Git author privacy

Run:

```bash
git config user.name
git config user.email
git log -2 --format='%h %an <%ae> %s'
```

Require `wyze69-sys` and `258711354+wyze69-sys@users.noreply.github.com` for all unpublished/new commits. The already-public `ca00220` commit is a reviewed historical exception; do not rewrite it.


### Step 1.2: Confirm local and remote identity

Run from `D:\PROJECT\Quantara`:

```bash
git status --short --branch
git remote -v
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git rev-list --left-right --count origin/main...HEAD
git log --oneline --decorate -5
gh auth status
gh repo view wyze69-sys/Quantara --json nameWithOwner,url,isPrivate,viewerPermission,defaultBranchRef
```

Expected before implementation:

- worktree clean;
- branch `main`;
- `HEAD` is the approved plan commit and equals `IMPLEMENTATION_BASE`;
- remote has not changed unexpectedly;
- viewer permission remains `ADMIN`.

If `origin/main` advanced, the worktree changed, or the active account changed, stop and review the new state before continuing.

### Step 1.3: Verify approved rights and public identity

Build a tracked-file inventory:

```bash
git ls-files
git log --format='%h %an <%ae> %s' -5
```

Create `rights-inventory.json` in the transaction directory. Classify every tracked file or coherent file group as:

- owner-controlled original material covered by Apache-2.0;
- third-party/provider material excluded from the grant;
- material requiring preserved notice or attribution;
- unresolved.

Record the copyright decision explicitly: use the public holder `wyze69-sys` and current publication year only where a notice is required, or record `no additional notice outside the unmodified license body`. Confirm no third-party market data is tracked, provider content is excluded, the real name does not appear in new files, and the conduct contact is used only where approved. Any unresolved ownership, notice, or licensing classification is `BLOCKED`.

### Step 1.3a: Verify the private conduct route

Record that `linhrathhenry@gmail.com` is the explicitly approved recipient, the user/maintainer is the monitoring owner, and mailbox access is restricted to the approved recipient. Verify the address syntax and Gmail MX availability. Before publication, require a positive end-to-end receipt test: the owner must send a test message to the address through an account they control, receive it in the monitored inbox, and explicitly confirm receipt. Do not send unsolicited mail through an unapproved service. Missing receipt confirmation is `BLOCKED`.

### Step 1.4: Snapshot remote state before mutation

Save authenticated read-back JSON outside Git:

```bash
gh repo view wyze69-sys/Quantara \
  --json nameWithOwner,url,description,homepageUrl,repositoryTopics,hasIssuesEnabled,hasDiscussionsEnabled,hasWikiEnabled,hasProjectsEnabled,defaultBranchRef,isPrivate,viewerPermission,openGraphImageUrl,usesCustomOpenGraphImage \
  > /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/repo-before.json

gh api -H 'Accept: application/vnd.github+json' \
  repos/wyze69-sys/Quantara/private-vulnerability-reporting \
  > /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/vulnerability-reporting-before.json
```

Use `usesCustomOpenGraphImage` as the authoritative prior-state signal because GitHub-generated `openGraphImageUrl` hashes may change between reads. Record the current public URL in `social-preview-before.txt`. If `usesCustomOpenGraphImage` is true, stop before replacement and obtain explicit approval plus recoverable prior bytes.

### Step 1.5: Record the remote baseline

Write `transaction.json` outside Git containing:

- local and remote commit IDs;
- description;
- homepage;
- topics;
- default branch;
- Issues, Discussions, Wiki, and Projects states;
- private vulnerability reporting state;
- prior Open Graph image URL and whether a custom asset is recoverable;
- the exact read and restoration commands.

Do not include tokens or credential material.

The transaction record must include these exact restoration operations, with JSON payloads built from the snapshot rather than shell-interpolated guesses:

```bash
gh api --method PATCH -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  repos/wyze69-sys/Quantara \
  --input /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/repo-restore-payload.json

gh api --method PUT -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  repos/wyze69-sys/Quantara/topics \
  --input /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/topics-restore-payload.json
```

The repository restore payload contains the exact prior `description`, `homepage`, `has_issues`, `has_discussions`, `has_wiki`, and `has_projects` values. The topics payload is `{"names": [...]}` with the exact prior names. Restore private vulnerability reporting with `PUT` when the prior state was enabled or `DELETE` when it was disabled. Before each restore, read the current value and restore only if it still equals the value applied by this pass; then read back the restored value. Never restore the default branch because this pass does not mutate it.

## 8. Task 2 — Establish validation harness and prove the missing-state failure

### Step 2.1: Create a temporary validator

Create:

```text
C:\Users\User\AppData\Local\Temp\quantara-repository-presentation\validate_repository_presentation.py
```

The validator must check:

- exact required implementation file set relative to an explicit Git base;
- no unapproved extra file in `git diff --name-status <IMPLEMENTATION_BASE>...HEAD` after commit or `git diff --cached --name-status` before commit;
- relative Markdown links and image targets;
- internal Markdown anchors;
- heading hierarchy;
- required maturity text;
- every material capability statement has an approved state;
- YAML syntax and unique issue-form IDs;
- required checkbox option semantics;
- CFF fields and forbidden invented metadata;
- SVG XML parsing;
- SVG accessibility title/description;
- forbidden SVG scripts, external requests, remote fonts, and embedded raster content;
- approved palette values;
- required README and social-preview status wording;
- no real-name leakage;
- conduct email appears only in `CODE_OF_CONDUCT.md`;
- no secrets, provider data, or unintended absolute paths in implementation outputs.

Use Python standard library for Markdown/path/XML/static checks and `uv run --with pyyaml` for YAML parsing.

### Step 2.2: Run the validator before creating files

Run:

```bash
uv run --with 'pyyaml==6.0.2' python \
  /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/validate_repository_presentation.py \
  /d/PROJECT/Quantara \
  "$IMPLEMENTATION_BASE" \
  WORKTREE
```

Expected result: non-zero failure listing the missing approved files. If it passes before implementation, the validator is invalid; fix the validator before proceeding.

## 9. Task 3 — Create deterministic visual assets and README

### Step 3.1: Create `docs/assets/quantara-header.svg`

Implement the approved visual system:

- explicit `#07182E` background;
- `#F4F1E8` primary text;
- `#66C8D1` accent;
- `#7792A8` secondary text;
- Quantara wordmark;
- descriptor `Point-in-time market intelligence infrastructure`;
- visible status `FOUNDATION-STAGE — SPECIFIED, NOT IMPLEMENTED`;
- restrained source-to-validation-to-structured-output motif;
- no price forecast, signal, fake metric, fake checksum, coin, robot, or trader imagery;
- responsive `viewBox`;
- `<title>` and `<desc>` accessibility elements;
- no script, remote font, external URL, embedded raster, or tracking content.

Prefer exact SVG geometry and system-safe text. Do not use the generated raster concept as the committed asset.

### Step 3.2: Create `docs/assets/quantara-social-preview.svg`

Create a simplified deterministic composition containing only:

- Quantara;
- descriptor;
- exact visible status;
- one validation-to-canonical motif.

Avoid tiny labels and architecture detail.

### Step 3.3: Render both SVGs with a pinned scratch renderer

Create a scratch npm package under the transaction directory and install the reviewed renderer without touching the repository:

```bash
RENDER=/c/Users/User/AppData/Local/Temp/quantara-repository-presentation/render
mkdir -p "$RENDER"
(cd "$RENDER" && npm init --yes)
npm install --prefix "$RENDER" --save-exact 'sharp@0.35.3'
npm ls --prefix "$RENDER" sharp --depth=0
```

Retain the scratch `package-lock.json`, record `sharp 0.35.3`, Node/npm versions, complete render command, and renderer lockfile hash. Render:

- header at `1280px` width;
- header at `375px` width;
- header at `200%` effective zoom;
- social preview at `1280 × 640` unless current official documentation changes;
- a second social export with the identical command to prove identical output hashes in the same environment.

Record the authoritative GitHub social-preview documentation URL, access date, selected dimensions, and requirement that the PNG remain under `1 MiB`. Verify size with `stat -c %s`.

Write PNGs outside Git. Record commands and SHA-256 hashes.

### Step 3.4: Inspect visual output

Use image analysis on every render. Reject and revise for:

- misspelled text;
- clipping or overlap;
- unreadable reduced-size status;
- low contrast;
- promotional trading implications;
- misleading runtime/output imagery;
- status hidden behind decorative content;
- normal-text contrast below `4.5:1`;
- large-text or essential-graphic contrast below `3:1`;
- meaning that depends on color alone.

Record calculated contrast ratios. The later live review must also inspect Mermaid in GitHub light and dark themes and the header at `200%` browser zoom.

### Step 3.5: Create `README.md`

Follow the exact Section 9 order in the design specification:

1. hero and foundation-stage status;
2. why Quantara exists;
3. intended invariants with explicit limitations;
4. bounded BTCUSDT January 2024 scope;
5. contract-faithful Mermaid flow labeled `Specified first-slice flow — not implemented`;
6. authoritative specification link;
7. only paths that exist;
8. capability roadmap using exactly:
   - `Implemented and verified`
   - `Specified but not implemented`
   - `Planned`
9. engineering and contribution links;
10. Apache/data-rights/responsible-use boundaries.

At `1280 × 800`, name, descriptor, status, and non-trading disclaimer must appear before scrolling. At `375 × 812`, name, descriptor, and status must appear in the first viewport and the disclaimer no later than the second.

Do not add unsupported badges, quick-start commands, CI claims, releases, coverage, or package instructions.

### Step 3.6: Run the validator

The validator should still fail only for governance/template files not yet created. Any README or asset-specific failure must be fixed before proceeding.

## 10. Task 4 — Enable and verify private vulnerability reporting

### Step 4.1: Confirm all mandatory preflight evidence

Before mutation, require completed approval evidence, rights inventory, copyright decision, public identity mapping, operational conduct-route confirmation, GitHub permission/eligibility, remote snapshot, and reversibility review from Task 1. Then read private vulnerability reporting again. Continue only if it is still disabled as recorded. Any missing prerequisite or drift is `BLOCKED`.

### Step 4.2: Enable through the authenticated API

Run:

```bash
gh api --method PUT \
  -H 'Accept: application/vnd.github+json' \
  repos/wyze69-sys/Quantara/private-vulnerability-reporting
```

Immediately read back:

```bash
gh api -H 'Accept: application/vnd.github+json' \
  repos/wyze69-sys/Quantara/private-vulnerability-reporting
```

Expected: `{"enabled":true}`.

### Step 4.3: Validate reporting destination

Use:

```text
https://github.com/wyze69-sys/Quantara/security/advisories/new
```

Confirm GitHub recognizes the route after enablement using both authenticated API read-back and an unauthenticated HTTP request that resolves to GitHub login with the exact advisory path as `return_to`. This proves the visitor-facing destination exists without pretending the signed-in form was exercised. Do not substitute a public issue route.

If enablement or route recognition fails, restore the prior disabled state with `DELETE`, read it back, retain diagnostics outside Git, and report `BLOCKED` before generating `SECURITY.md`. If the route exists but ordinary signed-in interaction cannot later be tested because browser authentication is unavailable, safe work may continue but final status is at most `INCOMPLETE`.

## 11. Task 5 — Create license, governance, citation, and contribution files

### Step 5.1: Create `LICENSE`

Fetch the official Apache 2.0 text from:

```text
https://www.apache.org/licenses/LICENSE-2.0.txt
```

Commit the unmodified license text. Do not add third-party data to its scope. Record the fetched SHA-256 hash outside Git.

### Step 5.2: Create `CONTRIBUTING.md`

Include:

- bounded-subproject workflow;
- design-before-implementation requirement for material changes;
- tests and verification evidence;
- temporal/leakage review;
- provenance/schema impact;
- documentation requirements;
- focused pull requests;
- prohibition on credentials, provider data, and generated artifacts;
- no invented setup commands.

### Step 5.3: Create `CODE_OF_CONDUCT.md`

Fetch Contributor Covenant 2.1 from:

```text
https://www.contributor-covenant.org/version/2/1/code_of_conduct/code_of_conduct.md
```

Replace only `[INSERT CONTACT METHOD]` with a `mailto:` link for `linhrathhenry@gmail.com`. Preserve the remaining official text and attribution. Do not promise unsupported response timing or absolute confidentiality.

### Step 5.4: Create `SECURITY.md`

Include:

- the verified GitHub private vulnerability reporting URL;
- a warning not to open public vulnerability issues;
- latest `main` as the supported state;
- useful report contents;
- no unsupported response-time promise;
- distinction between vulnerability reports and data-quality incidents.

Do not put the conduct email in this file.

### Step 5.5: Create `CITATION.cff`

Use CFF `1.2.0` with:

- `title: Quantara`;
- entity author `name: wyze69-sys`;
- `repository-code: https://github.com/wyze69-sys/Quantara`;
- `license: Apache-2.0`;
- a concise foundation-stage citation message.

Omit DOI, ORCID, affiliation, version, and release date. Do not infer personal name fields.

### Step 5.6: Verify legal and CFF sources

- Compare `LICENSE` byte-for-byte or after documented line-ending normalization with the fetched official text.
- Record the versioned Contributor Covenant source URL and fetched SHA-256 hash, reverse the one approved contact substitution, and compare with the official 2.1 Markdown source after documented line-ending normalization.
- Run:

```bash
uvx 'cffconvert==2.0.0' --validate --infile CITATION.cff
```

Stop on any mismatch or validation failure.

## 12. Task 6 — Create GitHub issue forms and pull-request template

### Step 6.1: Create `bug_report.yml`

Use existing label `bug`. Require:

- description;
- reproduction steps;
- expected behavior;
- actual behavior;
- environment;
- sanitized logs/evidence;
- confirmation that the report is not a private security vulnerability.

Every non-Markdown field gets a stable unique ID. Required checkbox options set `required: true`.

### Step 6.2: Create `data_quality_incident.yml`

Do not assign a nonexistent label. Require:

- provider;
- market/symbol/interval;
- affected UTC range;
- observed invariant failure;
- reproducibility evidence;
- restricted-data confirmation.

Allow checksum and manifest identifiers to be optional.

### Step 6.3: Create `design_proposal.yml`

Do not use generic feature-request language. Require:

- problem;
- bounded scope;
- non-goals;
- temporal/leakage impact;
- provenance impact;
- alternatives;
- verification plan.

Use existing label `enhancement` only if the wording remains factual; otherwise omit labels.

### Step 6.4: Create `config.yml`

- set `blank_issues_enabled: false`;
- add a security contact link to the verified private vulnerability route;
- do not add dead discussion or documentation links.

### Step 6.5: Create pull-request template

Cover:

- bounded summary;
- linked issue/specification;
- tests and exact commands;
- verification evidence;
- data/schema/provenance impact;
- temporal/leakage assessment;
- documentation impact;
- secret/generated-artifact confirmation.

### Step 6.6: Validate YAML and issue-form behavior statically

Cache the current SchemaStore issue-form and issue-config schemas in the transaction directory from:

```text
https://www.schemastore.org/github-issue-forms.json
https://www.schemastore.org/github-issue-config.json
```

Record their URLs, access dates, and hashes. Run pinned supplementary schema checks:

```bash
uvx --from 'check-jsonschema==0.37.2' check-jsonschema \
  --schemafile /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/github-issue-forms.json \
  .github/ISSUE_TEMPLATE/bug_report.yml \
  .github/ISSUE_TEMPLATE/data_quality_incident.yml \
  .github/ISSUE_TEMPLATE/design_proposal.yml
uvx --from 'check-jsonschema==0.37.2' check-jsonschema \
  --schemafile /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/github-issue-config.json \
  .github/ISSUE_TEMPLATE/config.yml
```

Then run the custom validator. Confirm:

- YAML parses;
- IDs are unique and valid;
- required semantics are attached at option level;
- top-level names/descriptions/title prefixes exist;
- all configured labels exist remotely;
- no assignee is guessed.

## 13. Task 7 — Complete local verification

### Step 7.1: Run full validator and ignore-boundary checks

Expected: zero failures. Also run and record:

```bash
git check-ignore -v data .env .venv
```

Use representative child paths when Git requires them, and confirm `/data/`, `.env*`, virtual environments, Python caches, coverage output, editor state, and temporary local artifacts remain ignored. Do not modify `.gitignore` in this pass.

### Step 7.2: Run Markdown lint and link checks

Use transient tools from outside the repository or through `npx --yes` without creating repository package files:

```bash
npx --yes 'markdownlint-cli2@0.23.2' \
  README.md \
  CONTRIBUTING.md \
  CODE_OF_CONDUCT.md \
  SECURITY.md \
  .github/pull_request_template.md
```

Validate internal anchors and relative paths with the custom validator. Check external URLs separately and report transient/network failures distinctly.

### Step 7.3: Validate SVG security and rendering

Confirm:

- XML parsing succeeds;
- required `<title>` and `<desc>` exist;
- no `<script>`, `foreignObject`, external `href`, data URI, remote CSS/font, or event handler exists;
- required palette and status text exist;
- two same-environment social-preview exports have identical SHA-256 hashes;
- visual analysis passes at desktop, narrow, and `200%` views;
- measured contrast ratios meet `4.5:1` for normal text and `3:1` for large text and essential graphics;
- meaning remains intact in grayscale/color-blind review;
- the Mermaid prose independently covers source, unique staging, validation, operation-specific legal gates, exact quality gate, failed/ineligible paths, immutable publication, discovery verification, and both provenance categories;
- GitHub light and dark Mermaid rendering are queued as mandatory live checks.

### Step 7.4: Audit material claims

Create a temporary claim inventory outside Git. Map every material README capability claim to exactly one state:

- implemented and verified;
- specified but not implemented;
- planned.

Reject any unlabeled infrastructure, ML, point-in-time safety, or trading claim.

### Step 7.5: Scan implementation outputs

Search only changed allowlisted outputs for:

- credentials and token patterns;
- the user's real name;
- unintended personal contact details;
- absolute local paths;
- provider data;
- generated hashes presented as runtime evidence;
- unsupported maturity claims.

The approved conduct email is the only allowed personal contact and only in `CODE_OF_CONDUCT.md`.

### Step 7.6: Stage explicitly and review the exact candidate diff

New files are invisible to ordinary unstaged `git diff`, so stage explicit allowlisted paths before final review. Do not use `git add .`:

```bash
git add -- \
  README.md LICENSE CONTRIBUTING.md CODE_OF_CONDUCT.md SECURITY.md CITATION.cff \
  .github/ISSUE_TEMPLATE/bug_report.yml \
  .github/ISSUE_TEMPLATE/data_quality_incident.yml \
  .github/ISSUE_TEMPLATE/design_proposal.yml \
  .github/ISSUE_TEMPLATE/config.yml \
  .github/pull_request_template.md \
  docs/assets/quantara-header.svg \
  docs/assets/quantara-social-preview.svg
git diff --cached --check
git diff --cached --stat
git diff --cached --name-status
git diff --cached
```

Compare the cached path set exactly with the allowlist and the validator's `WORKTREE` mode. Unstage and correct any failure; do not commit until the full cached diff is reviewed.

## 14. Task 8 — Commit the bounded implementation

### Step 8.1: Confirm the explicitly staged candidate

Task 7 already staged every approved path explicitly. Re-run `git diff --cached --name-status` and confirm no file changed after validation. Never use `git add .`.

### Step 8.2: Inspect staged files

Run:

```bash
git diff --cached --name-status
git diff --cached --check
git status --short
```

Expected: only allowlisted implementation files.

### Step 8.3: Commit

Use one implementation commit:

```bash
git commit -m "docs: professionalize repository presentation"
```

Do not amend the approved design or plan commits.

### Step 8.4: Re-run validation at committed state

Run the full local validator against `HEAD` with:

```bash
uv run --with 'pyyaml==6.0.2' python \
  /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/validate_repository_presentation.py \
  /d/PROJECT/Quantara \
  "$IMPLEMENTATION_BASE" \
  HEAD
```

Confirm the worktree is clean and `git diff --name-status "$IMPLEMENTATION_BASE"...HEAD` equals the allowlist.

## 15. Task 9 — Prepare remote mutations without applying them

### Step 9.1: Compare remote state before push

Read every current remote property and compare with `transaction.json`. Confirm private vulnerability reporting remains enabled and its URL remains valid. Stop on drift; do not publish dead reporting instructions.

### Step 9.2: Build exact mutation payloads outside Git

Create `repo-apply-payload.json` containing exactly:

```json
{
  "description": "Foundation-stage design for correctness-first, point-in-time market-data and ML infrastructure.",
  "homepage": "",
  "has_issues": true,
  "has_discussions": false,
  "has_wiki": false,
  "has_projects": false
}
```

Create `topics-apply-payload.json` containing the exact approved ten-topic `names` array. Do not apply non-security metadata before the push; otherwise a push failure could leave the public metadata describing files that are not live. Do not alter visibility, merge strategies, branch protection, labels, Actions, or default branch.

## 16. Task 10 — Push and verify the remote repository

### Step 10.1: Final pre-push state check

Run:

```bash
git status --short --branch
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git log --oneline --decorate -5
```

If `origin/main` changed since Task 1, stop and reconcile without force-pushing.

### Step 10.2: Push normally

Run:

```bash
git push origin main
```

This publishes the approved specification commit, approved plan commit, and one implementation commit. Do not force-push.

### Step 10.3: Verify commit identity and remote files

- compare local `HEAD` with `refs/remotes/origin/main` and GitHub API commit identity;
- read back README, LICENSE, SECURITY, citation, issue forms, and SVG files from GitHub;
- confirm no file was truncated or omitted.

### Step 10.4: Apply metadata and feature settings after successful push

Compare current values with the transaction snapshot again, then apply exact payloads:

```bash
gh api --method PATCH -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  repos/wyze69-sys/Quantara \
  --input /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/repo-apply-payload.json

gh api --method PUT -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  repos/wyze69-sys/Quantara/topics \
  --input /c/Users/User/AppData/Local/Temp/quantara-repository-presentation/topics-apply-payload.json
```

### Step 10.5: Read back all remote settings

Read back repository properties, exact topics, default branch, and private vulnerability reporting. Compare exact values. A successful mutation response without read-back is insufficient.

### Step 10.6: Verify public rendering

Inspect the live repository at:

```text
https://github.com/wyze69-sys/Quantara
```

Capture evidence at:

- `1280 × 800`;
- `375 × 812`;
- `200%` zoom.

Verify:

- header and status visibility;
- non-trading disclaimer placement;
- Mermaid rendering and accompanying prose;
- no clipping/overlap;
- links resolve;
- license is detected;
- repository metadata and topics display correctly.

If the browser cannot emulate an authenticated narrow view, public read-only rendering is still testable.

### Step 10.7: Verify live issue forms

Open the issue-creation page publicly. Confirm:

- three intended forms appear;
- blank issues are disabled;
- security contact points to the private advisory route;
- required fields prevent incomplete submission;
- no test issue is actually submitted.

### Step 10.8: Verify private reporting

- read back `enabled: true` through the authenticated API;
- confirm the visitor-facing private report route exists;
- confirm `SECURITY.md` and issue-template configuration use the same URL;
- confirm Code of Conduct reports use the separate approved email;
- confirm the conduct mailbox's approved recipient/monitoring ownership remains valid;
- if authenticated browser interaction is unavailable, list issue-form required-field behavior and ordinary signed-in private-reporting flow as unverified non-critical items and report at most `INCOMPLETE`.

## 17. Task 11 — Upload or hand off the social preview

### Step 11.1: Determine whether an authenticated upload path exists

GitHub documentation currently describes settings-page upload and no supported REST endpoint was identified during planning. Re-check current official documentation at execution time.

### Step 11.2: Upload if safely possible

If an authenticated browser/settings interface is available:

- upload the validated raster generated from `docs/assets/quantara-social-preview.svg`;
- verify the public `og:image` changes from GitHub's default image;
- fetch or screenshot the resulting social card;
- record the uploaded asset hash and evidence.

### Step 11.3: Manual fallback

If browser authentication is unavailable and no supported API exists:

- do not attempt cookie or token injection workarounds;
- retain the validated PNG outside Git;
- deliver the PNG to the user with exact steps:
  1. Repository **Settings**;
  2. **General**;
  3. **Social preview**;
  4. **Edit** → **Upload an image**;
  5. select the delivered PNG;
  6. save and confirm the preview.
- report final state as `INCOMPLETE`, listing social-preview upload plus every other non-critical unverified item such as authenticated issue-form behavior or ordinary signed-in private-reporting flow.

## 18. Task 12 — Failure handling and rollback

### Step 12.1: Local failure before commit

Remove only newly created allowlisted implementation files after capturing diagnostics outside Git. Do not reset or alter approved spec/plan commits.

### Step 12.2: Failure after implementation commit but before push

Use a new corrective commit if approved. Do not amend/rewrite approved history. If correction requires scope change, stop for approval.

### Step 12.3: Remote settings rollback

Restore properties in reverse mutation order only when compare-before-restore confirms the current value still equals the value applied by this pass. Stop on drift.

Reporting links and private vulnerability reporting must be restored as one coordinated unit. Do not disable private vulnerability reporting if reports/advisories were created or other published instructions now depend on it without explicit security-owner approval.

Read back every restored value.

### Step 12.4: Git publication failure

Do not force-push. Fetch, inspect divergence, and stop for reconciliation if remote advanced.

### Step 12.5: Post-publication repository rollback

If the implementation commit must be removed after publication:

1. compare current remote settings with the values applied by this pass and stop on drift;
2. restore non-security metadata/settings with the recorded restore payloads and read them back;
3. create a new revert commit with `git revert --no-edit <implementation-commit>`—never reset or force-push;
4. run the full validator in rollback mode and inspect the revert diff;
5. push the revert commit normally and verify the remote commit;
6. restore or disable private vulnerability reporting only as a coordinated final step after checking for reports/advisories and obtaining explicit security-owner approval when required.

The approved design and plan commits remain published documentation unless separately reverted through another approved commit.

### Step 12.6: Social preview

The observed prior state is GitHub's default generated preview. If execution discovers a custom image, stop before replacement. Never claim rollback can restore unavailable image bytes.

## 19. Final evidence report

Report:

- `COMPLETE`, `INCOMPLETE`, or `BLOCKED`;
- local and remote commit IDs;
- committed file list;
- validator/linter/CFF/legal-text/SVG results;
- renderer and package versions;
- GitHub social-preview documentation URL, access date, dimensions, and size limit;
- Apache and Contributor Covenant source URLs and fetched hashes;
- rights inventory and copyright decision;
- conduct-route operational confirmation;
- rendered asset hashes and evidence paths;
- GitHub description, topics, feature settings, and private-reporting read-back;
- live repository and issue-form URLs;
- screenshots or equivalent rendering evidence;
- social-preview state;
- residual limitations and exact manual step, if any.

Do not collapse a successful push, successful file validation, and successful social-preview publication into one unsupported claim.