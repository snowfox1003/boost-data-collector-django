# core.adapters

Stable adapter protocols and thin wrappers for external platform APIs (Pinecone, Slack Web API, GitHub REST/GraphQL).

## Layout

| Module | Role |
| --- | --- |
| `protocols.py` | `@runtime_checkable` protocols — no third-party imports |
| `pinecone.py` | **Only** `pinecone` SDK import site in the repo |
| `slack.py` | Delegates to `core.operations.slack_ops.client.SlackAPIClient` |
| `github.py` | Delegates to `core.operations.github_ops.client.GitHubAPIClient` |

Adapters sit **below** per-app Pydantic boundary schemas (`api_schemas.py`) and **above** vendor SDKs or HTTP clients.

## Pinecone

Production code constructs a client via `PineconeAdapter.from_api_key(api_key)`. `cppa_pinecone_sync.ingestion.PineconeIngestion` accepts an optional injected `PineconeClientProtocol` for tests.

**Dependency bumps:** change `core/adapters/pinecone.py` only. Verify with:

```bash
rg "from pinecone import|import pinecone" --glob "*.py"
```

## Testing

Inject a fake implementing `PineconeClientProtocol` instead of patching `pinecone.Pinecone`:

```python
from core.tests.adapters.fakes import FakePineconeClient
from cppa_pinecone_sync.ingestion import PineconeIngestion

ing = PineconeIngestion(client=FakePineconeClient())
```

Shared fakes live in `core/tests/adapters/fakes.py`.

## Public API

See [docs/Core_public_API.md](../../docs/Core_public_API.md#external-adapters).
