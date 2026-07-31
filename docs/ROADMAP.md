# Roadmap

The repository is usable as an MVP. This file is the single place for improvements
that are intentionally not implemented; completed work belongs in architecture or
operations documentation.

## Provisioning

- Add a first-class home-LAN transport backend that consumes existing DHCP without
  ever starting the direct-Ethernet DHCP server.
- Support a reviewed `--expected-host-key` input to replace trust-on-first-use during
  rescue provisioning.
- Add session replay, comparison, human-readable reports, and opt-in issue bundles
  without weakening the privacy of hardware reports.
- Validate PXE fallback and Wake-on-LAN on additional firmware implementations and
  compatible mini-PC models.

## Operations and security

- Evaluate `sops-nix` after defining operator and host age identities, offline recovery,
  CI evaluation behavior, and rollback semantics.
- Add encrypted automated off-host Actual backups after selecting storage, credentials,
  retention, alerting, and a documented key-recovery process.
- Schedule recurring disposable restore drills and record their non-sensitive result.
- Add monitoring authentication or a private overlay network before extending access
  beyond the trusted LAN.

## Application assurance

- Add a fake Discord boundary or upstream readiness endpoint so CI can test bot login,
  reconnect, rate limiting, duplicate handling, bank notifications, and receipt OCR
  without production credentials.
- Add automated reviewed dependency-update pull requests for Nix inputs and container
  digests; never activate updates or database migrations automatically.
- Evaluate application-level smoke tests against seeded disposable Actual data while
  keeping real budgets out of CI.

## Monitoring

- Review database growth after a full retention window and adjust the 14-day/512 MiB
  limits from measured data.
- Add alerts only after selecting a local delivery path that requires no cloud account
  and does not put credentials in the Nix store.
- Reconsider centralized Prometheus/Grafana only when multiple hosts make a single-host
  Netdata dashboard operationally insufficient.

## CI and releases

- Move the slowest VM jobs to a maintained self-hosted KVM runner if hosted runner
  performance or disk limits become unreliable.
- Add release provenance or signatures once an operator key lifecycle and verification
  procedure are defined.
