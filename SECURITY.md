# Security policy

Thank you for helping keep Boost Data Collector and its users safe. This document describes **supported versions**, **what we consider in scope**, **how to report vulnerabilities privately**, **response expectations**, and **credentials you should rotate** if a deployment may have been compromised.

## Supported versions

- **Source of security fixes:** fixes land on **`develop`**, this repository’s **GitHub default** branch (where pull requests land), and are promoted to **`main`** for stable production releases. Track the latest commit on **`main`** for production-aligned deployments, or **`develop`** for the latest default-branch integration, unless maintainers say otherwise for a specific case. We do not commit to backporting fixes to older tags unless maintainers explicitly agree for a specific case.
- **Python:** this project targets **[Python 3.13](https://github.com/python/cpython)** (`requires-python = ">=3.13,<3.14"` in `pyproject.toml`). Reports that only reproduce on **end-of-life** or unsupported Python runtimes are **out of scope** for this policy.
- **Dependencies:** we address vulnerabilities in **this repository’s code and shipped configuration** as described below. Third-party package or platform bugs are handled upstream unless this project must apply a mitigation.

## How to report a vulnerability (private channels only)

**Do not** file a **public GitHub Issue** to report an undisclosed security vulnerability. Public issues can spread exploit details, put deployments at risk, and leak information about secrets or architecture before a fix exists.

Use one of these **private** channels instead:

### 1. GitHub private vulnerability reporting (preferred)

1. Open this repository on GitHub.
2. Go to the **Security** tab.
3. Choose **Report a vulnerability** (private reporting).

This requires repository maintainers to enable **[Private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository)** for the repository. General guidance: **[Privately reporting a security vulnerability](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)**.

If you already have a direct link to this repo’s security page, it follows the pattern:
`https://github.com/<owner>/<repo>/security`

### 2. Email (alternative)

**Email is not an offered reporting channel until a dedicated address is listed in this section.** Until then, use [**GitHub private vulnerability reporting**](#1-github-private-vulnerability-reporting-preferred) when it is enabled, or reach out through an existing **non-public** relationship with maintainers. **Do not** send exploit details to a public mailing list or issue tracker.

### What to include in your report

- Short description of the issue and its impact
- Steps to reproduce (commands, URLs, configuration), with minimal proof-of-concept where possible
- Affected area (e.g. Django view, management command, Celery task, integration) and file paths if known
- Whether you believe **credentials, session data, or personal data** may be exposed
- Your preferred secure follow-up channel (if different from the one you used)

## Expected response timeline

These timelines are **goals**, not guarantees. Severity, complexity, and maintainer availability affect scheduling.

| Milestone | Target |
| --- | --- |
| **Initial acknowledgement** | Within **7 business days** of a coherent private report |
| **Status updates** | At least every **14 business days** while the issue remains open, or sooner for **critical** issues |
| **Fix and disclosure** | **Best effort**; we avoid promising a specific patch date |

If a fix cannot be delivered within **90 days** of initial acknowledgement, we will work with you on a **mutually agreed disclosure date** rather than asking for an indefinite embargo. This remains subject to the “goals, not guarantees” framing above.

We will coordinate **public disclosure** (release notes, advisory, or CVE as appropriate) with you when possible after a fix is available or a risk accepted. When a CVE is warranted, **maintainers** coordinate assignment (often via a **GitHub Security Advisory** where applicable); you may **note CVE preference** in your initial report.

## Scope of covered components

We consider reports for security weaknesses in **this repository** in the following areas:

- **Django application** — web views, authentication and authorization, sessions, CSRF, admin, settings in [`config/settings.py`](config/settings.py), and deployment-related toggles documented in [`.env.example`](.env.example) (for example `USE_X_FORWARDED_HOST`, `USE_TLS_PROXY_HEADERS`, `CSRF_TRUSTED_ORIGINS`, `ALLOWED_HOSTS`).
- **Management commands and scheduled work** — collectors and related commands, including behavior under Celery/Celery Beat when used as documented (for example [`docs/Workflow.md`](docs/Workflow.md), `config/boost_collector_schedule.yaml`).
- **Credential and secret handling** — how tokens, keys, cookies, and workspace files are read, stored, logged, and passed to subprocesses or external APIs.
- **Integrations** — GitHub API usage; Slack and Discord connectors; Pinecone sync; YouTube API usage; **Chrome profile / session token** flows for Slack huddles (see [`.env.example`](.env.example)).
- **Workspace and filesystem** — paths under `WORKSPACE_DIR` / `RAW_DIR` and related processing, when failure could lead to arbitrary file access, data leaks, or unsafe deserialization.

### Out of scope

- Vulnerabilities only in **third-party** services, infrastructure, or dependencies **without** a practical mitigation in this repo
- **SSH**, firewall, or OS hardening for your servers, unless this repository ships the specific vulnerable configuration you are reporting
- Theoretical issues with **no** plausible impact on a maintainer-supported deployment (we still appreciate heads-ups for defense-in-depth)

## Safe harbor

We support **good-faith** security research that:

- Avoids privacy violations and data theft beyond what is necessary to demonstrate the issue
- Avoids **destructive** actions (data loss, sustained DoS, spam) on production systems without prior agreement
- Keeps details **private** until we agree on a disclosure timeline

If you conduct research in **good faith** and in accordance with these guidelines, we will **not initiate or recommend legal action** against you in connection with that research.

## Credential rotation after a suspected compromise

If you operate a deployment and suspect a leak or breach, **rotate** at least the following (names align with [`.env.example`](.env.example) and the project README):

| Category | Examples / environment variables |
| --- | --- |
| **GitHub** | `GITHUB_TOKEN`, `GITHUB_TOKENS_SCRAPING` (multi-token pool), `GITHUB_TOKEN_WRITE`; PAT-style tokens used by integrations (for example `SLACK_PR_BOT_GITHUB_TOKEN` if it is a PAT) |
| **Slack** | `SLACK_BOT_TOKEN_<team_id>`, `SLACK_APP_TOKEN_<team_id>`; if enabled: internal session tokens in `workspace/slack_event_handler/slack_internal_tokens.json` (see `ALLOW_INTERNAL_SLACK_TOKENS` in `.env.example`) |
| **Discord** | `DISCORD_TOKEN` (bot token — supported path); **`DISCORD_USER_TOKEN`** for automation **conflicts with Discord’s Terms of Service** and may result in **account termination** — **rotate and discontinue** use; migrate to bot-based flows where applicable (see [`.env.example`](.env.example) and project docs) |
| **Pinecone** | `PINECONE_API_KEY`, `PINECONE_PRIVATE_API_KEY`, and any host/index settings that grant write access |
| **YouTube** | `YOUTUBE_API_KEY` |
| **Browser session material** | Data derived from **Chrome profiles or cookies** (`CHROME_PROFILE_PATH`, `slack_internal_tokens.json`, and related flows) — treat as secrets; clear or rotate sessions and profiles as appropriate |

Also rotate **Django** `SECRET_KEY` and **database** credentials (`DATABASE_URL` or `DB_*`) if there is any chance the application or its configuration was exposed.

## Maintainer checklist (repository settings)

GitHub reads `SECURITY.md` from the repository **default branch** (**`develop`** for this project) and surfaces it as the **[Security policy](https://docs.github.com/en/code-security/getting-started/github-security-features)** (for example at `https://github.com/<owner>/<repo>/security/policy`).

1. Land `SECURITY.md` on **`develop`** (the default branch) via pull request so GitHub publishes the policy; merge **`develop`** to **`main`** for production releases as usual.
2. Enable **[Private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository)** if you want reporters to use the GitHub **Security** tab flow.
3. Confirm the policy page loads and links work.
4. When you have an org-approved **security email**, add it under [Email (alternative)](#2-email-alternative) and state clearly that email reporting is available (until then, reporters should use private reporting or an existing private maintainer contact).

---

Thank you for responsible disclosure.
