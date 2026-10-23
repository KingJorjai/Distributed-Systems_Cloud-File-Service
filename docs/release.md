# Release and Versioning Policy

The project uses Semantic Versioning with a deliberate `0.x.y` phase.

## Rules

- `MAJOR.MINOR.PATCH` is the Git tag format: `v0.11.1`.
- `MINOR` increments for each completed milestone or grouped feature set.
- `PATCH` increments for fixes and maintenance without a milestone.
- `1.0.0` is reserved for the final validated delivery. It is not used while
  GUI/tray validation, final documentation, or release checks are pending.
- A hyphen denotes a pre-release (`v0.12.0-rc.1`), not a build number.
- Build metadata stays outside the Git tag. Release artifacts append
  `-build.<run>`; strict SemVer build metadata would be `+build.<run>`.
- Historical milestone tags are local only. Pushing every tag would trigger the
  release workflow for old commits. Only the current release tag is pushed.

## Milestone tags

| Tag | Milestone |
| --- | --- |
| `v0.3.0` | M0 baseline |
| `v0.4.0` | M1 foundations |
| `v0.5.0` | M2 reconciliation |
| `v0.6.0` | M3 replication |
| `v0.7.0` | M4 election and failover |
| `v0.8.0` | M5 shares and notifications |
| `v0.9.0` | M6 daemon and GUI |
| `v0.10.0` | M7 server administration |
| `v0.11.0` | M8 delivery preparation |
| `v0.11.1` | M8 delivery fixes |

`v1.0.0` will be created only after the final manual GUI/tray validation and
the final report review.

## Commands

```sh
python -c "import version; print(version.__version__)"
python -m unittest discover -s tests -v
python -m ruff check .
mkdocs build --strict
```

Publish only the current tag:

```sh
git push origin v0.11.1
```

Do not use `git push --tags` with the historical milestone tags. The release
workflow also checks that the pushed tag matches `version.py`.
