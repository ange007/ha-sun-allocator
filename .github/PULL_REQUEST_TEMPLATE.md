# Pull Request

## Summary

<!-- One or two sentences describing what changes and why. -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Refactor (no functional change)
- [ ] Breaking change (fix or feature that would cause existing setups to misbehave)
- [ ] Documentation only

## Checklist

- [ ] Tests added or updated for the change (including regression tests for fixed bugs).
- [ ] `python -m ruff check custom_components/sun_allocator/ tests/` is clean.
- [ ] `pytest` passes locally (or CI is green).
- [ ] If config-entry data shape changed: a new migration was added in `core/migrations.py` with `Added in vX.Y.Z` docstring.
- [ ] User-facing changes (new entity, new config field, changed defaults) are reflected in `README.md`, `README_UK.md`, and the relevant `docs/*.md` pair.
- [ ] `manifest.json` version bumped if user-facing behavior changed.
- [ ] Translation keys added in both `translations/en.json` and `translations/uk.json` for any new error / form field.

## Screenshots / logs (if relevant)

<!-- Optional. Helpful for UI changes or behavior fixes. -->
