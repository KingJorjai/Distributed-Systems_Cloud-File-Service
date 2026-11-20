# Pending work

Current status: M0-M8 implemented and published as `v0.11.3`. LAN tooling and the
offline kit are ready. Final manual validation and the `v1.0.0` tag remain.

## Final validation

- [ ] Open the GUI on a real Linux desktop and check login, upload, download,
      tray hide/show, pause/resume, quit, and autostart.
- [ ] Repeat the visual check with the Windows x64 bundle.
- [ ] Review the final report, presentation, and PDFs.
- [ ] Create `v1.0.0` only when the validation above is complete.

## Production hardening

- [ ] Rate limiting and account recovery.
- [ ] Persistent administrative audit log.
- [ ] Chunked snapshots and configurable size limits.
- [ ] Version history and garbage collection of tombstones/conflicts.
- [ ] Groups and inherited ACLs.
- [ ] Signed installers, auto-update, and secret management with a keyring.
- [ ] Certificate rotation and TLS deployment automation.

These improvements are outside the scope of the current delivery and are
detailed in `docs/limitations.md`.