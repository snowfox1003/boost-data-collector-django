## Summary

<!-- What changed and why? -->

## Apps touched

<!-- e.g. github_activity_tracker, core -->

-

## Test plan

- [ ] `python -m pytest` (or scoped: `python -m pytest <app>/tests`)
- [ ] `uv run pyright` (if typed code changed)
- [ ] `lint-imports` (if imports or cross-app coupling changed)
- [ ] App command smoke-tested (if collector/command changed):

```bash
# python manage.py <command> ...
```

## Docs / coupling

- [ ] [cross-app-dependencies.md](docs/cross-app-dependencies.md) updated (if FKs or cross-app imports changed)
- [ ] `python scripts/generate_service_docs.py` run (if `services.py` or `core/protocols.py` changed)
- [ ] App README or `docs/` updated (if behavior or ops changed)
