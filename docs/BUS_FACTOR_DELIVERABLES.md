# Bus factor reduction — deliverables checklist

Ticket: **Bus factor reduction: cross-training documentation + review process** (8 pts, High).

Use this page when closing the ticket or for audit (Test 38 / B10 / C3 / C6).

---

## Acceptance criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Architecture overview (15 Django apps + `core`) | Done | [Architecture_overview.md](Architecture_overview.md) |
| CODEOWNERS file (≥1 reviewer per PR path) | Done | [.github/CODEOWNERS](../.github/CODEOWNERS) (merged #223; not modified in this work) |
| CODEOWNERS **enforced** on `develop` | Done (2026-05-26) | Branch protection: PR required, code owner review, 1 approval — verify below |
| 2 onboarding walkthroughs (Leo + Jonathan) | Runbooks done | [walkthrough_leo.md](onboarding/walkthrough_leo.md), [walkthrough_jonathan.md](onboarding/walkthrough_jonathan.md) — **session logs:** fill after live 1:1 |
| External review evidence (B10) | **Action required** | Link merged PR(s) with approval from `@leostar0412` and/or `@jonathanMLDev` after sessions |

---

## Artifacts (links)

| Artifact | Path |
|----------|------|
| Architecture entry point | [docs/Architecture_overview.md](Architecture_overview.md) |
| Data-flow diagrams | [docs/Architecture_data_flow.md](Architecture_data_flow.md) |
| Cross-app / import-linter | [docs/cross-app-dependencies.md](cross-app-dependencies.md) |
| CODEOWNERS + protection how-to | [docs/CODEOWNERS_and_branch_protection.md](CODEOWNERS_and_branch_protection.md) |
| Review process | [docs/Development_guideline.md § Review process](Development_guideline.md#review-process) |
| PR template | [.github/pull_request_template.md](../.github/pull_request_template.md) |
| Walkthrough index | [docs/onboarding/README.md](onboarding/README.md) |
| Leo walkthrough | [docs/onboarding/walkthrough_leo.md](onboarding/walkthrough_leo.md) |
| Jonathan walkthrough | [docs/onboarding/walkthrough_jonathan.md](onboarding/walkthrough_jonathan.md) |

---

## Verify branch protection

```bash
gh api repos/cppalliance/boost-data-collector/branches/develop/protection \
  --jq '.required_pull_request_reviews | {require_code_owner_reviews, required_approving_review_count}'
```

Expected: `require_code_owner_reviews: true`, `required_approving_review_count: 1`.

**Settings UI:** `https://github.com/cppalliance/boost-data-collector/settings/branches`

---

## CODEOWNERS smoke tests

Follow [CODEOWNERS_and_branch_protection.md §2](CODEOWNERS_and_branch_protection.md#2-verify-after-codeowners-is-on-the-default-branch):

1. Draft PR changing `boost_mailing_list_tracker/` → owners requested.
2. Draft PR changing `docs/` only → doc owners requested.
3. Draft PR changing `.github/workflows/` → workflow owners requested.

Close draft PRs after verification.

---

## Ticket comment template

Paste into the tracking ticket when closing:

```
Bus factor reduction deliverables (boost-data-collector):

- Architecture overview: docs/Architecture_overview.md
- CODEOWNERS: .github/CODEOWNERS (unchanged); branch protection enabled on develop (code owner review, 1 approval)
- Review process: docs/Development_guideline.md#review-process + .github/pull_request_template.md
- Walkthroughs: docs/onboarding/walkthrough_leo.md, walkthrough_jonathan.md (session logs: <dates>)
- Sample reviewed PRs: <PR URLs with @leostar0412 / @jonathanMLDev approval>

Note: CODEOWNERS still lists @wpak-ai; Leo's handle for reviews is @leostar0412.
```

---

## Follow-ups (out of scope)

- Update `.github/CODEOWNERS` `@wpak-ai` → `@leostar0412` in a separate org-approved PR if auto-review requests fail for Leo.
- Enable the same protection on `main` if merges bypass `develop`.
- Fill **Session log** tables in walkthrough files after each 1:1.
