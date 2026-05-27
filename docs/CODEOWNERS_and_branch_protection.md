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
