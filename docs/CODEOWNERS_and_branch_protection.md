# CODEOWNERS and branch protection

This repo uses [`.github/CODEOWNERS`](../.github/CODEOWNERS) so GitHub can request reviews from code owners. **CODEOWNERS only affects behavior meaningfully when branch protection requires reviews from code owners** (and owners have write access to the repository).

## 1. Enable branch protection (repository admin)

For each protected branch (for example `main` or `develop`):

1. Open **Settings → Branches → Branch protection rules** (or **Rules → Rulesets** if your org uses rulesets).
2. Edit the rule that applies to the branch (or create one).
3. Enable **Require a pull request before merging**.
4. Enable **Require an approval from a code owner** (wording may be **Require review from Code Owners**).
5. Set **Required number of approvals before merging** to **1** (or your team policy). With `docs/` listing multiple owners, one approval from any listed owner for the changed paths is usually enough.

Without step 4, owners may still appear as suggested reviewers, but merges are not blocked on owner review.

### Required status checks (CI)

Branch protection on `develop` currently enforces CODEOWNERS review and approvals only—it does **not** require CI jobs to pass before merge. To block merges when tests fail, enable **Require status checks to pass before merging** and add at least:

- `test-ubuntu`
- `test-macos`
- `test-windows`

Optionally add `lint`, `pyright`, `compose-smoke`, and jobs from [`.github/workflows/security-audit.yml`](../.github/workflows/security-audit.yml) per team policy. Job names must match the workflow job `id` values exactly.

**Performance benchmarks (`benchmark` job):** [`.github/workflows/benchmarks.yml`](../.github/workflows/benchmarks.yml) runs on push/PR to `main` and `develop` and compares results to [`benchmarks/baselines.json`](../benchmarks/baselines.json). Rollout:

1. **Phase 1 (current):** The `benchmark` job runs on qualifying changes and **fails on regression**, but is **not** listed as a required status check—merges are not blocked while the gate stabilizes.
2. **Phase 2 (after ~2 weeks of stable green runs on `develop`):** Add `benchmark` to required status checks alongside `test-ubuntu`, `test-macos`, and `test-windows`.

**Status (`develop`):** Branch protection with **Require review from Code Owners** and **1** required approval was enabled on `cppalliance/boost-data-collector` (verified 2026-05-26). Re-check with:

```bash
gh api repos/cppalliance/boost-data-collector/branches/develop/protection \
  --jq '.required_pull_request_reviews'
```

See also [BUS_FACTOR_DELIVERABLES.md](BUS_FACTOR_DELIVERABLES.md).

## 2. Verify after CODEOWNERS is on the default branch

GitHub reads `CODEOWNERS` from the **default** branch for review assignment. After your PR that adds or updates `.github/CODEOWNERS` is **merged**:

1. **App path:** open a **draft** PR that changes one file under a single app (e.g. `boost_mailing_list_tracker/`). Confirm the **Reviewers** section lists the owner from the matching `CODEOWNERS` line.
2. **`docs/`:** open a draft PR that only changes a file under `docs/`. Confirm all handles on the `docs/` line are requested (users with write access only).
3. **Workflows:** open a draft PR that only changes a file under `.github/workflows/`. Confirm the expected owner is requested.

Then close or merge the draft PRs as appropriate.

## 3. Updating owners

When primary owners change, edit [`.github/CODEOWNERS`](../.github/CODEOWNERS) only. Optionally align the human ↔ app table in [Onboarding.md](Onboarding.md) or [cross-app-dependencies.md](cross-app-dependencies.md) so docs stay in sync.
