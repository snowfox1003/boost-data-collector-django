# Operations

**Operations** are shared, app-agnostic helpers under **`core/operations/`** for talking to the outside world (GitHub, CLIs, and similar). They are **not** the per-app **service API**, which is reserved for **database** writes.

| Name | Where it lives | Doc | Role |
|------|----------------|-----|------|
| GitHub | `core.operations.github_ops` | [github.md](github.md) | Clone, fetch, PR/issue/comment helpers; tokens. |

**Adding a new operation:** Put shared integration code in **`core/operations/`**, document it here, and add a row to the table (use a new Django app only if you need models).

**Service API vs operations:** *Service API* = one module per app for ORM create/update/delete. *Operations* = shared external I/O any app may import.
