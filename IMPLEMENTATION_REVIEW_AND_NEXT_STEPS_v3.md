
# IMPLEMENTATION_REVIEW_AND_NEXT_STEPS.md

# Goal

This document describes the next implementation phase after the initial repository review.

It intentionally does **not** replace IMPLEMENTATION_PLAN.md.
Instead, it captures architectural improvements and concrete implementation work discovered during the first implementation.

---

# Overall Direction

The project should evolve towards a **headless provisioning appliance**.

The long-term user experience should be as close as possible to:

```text
just provision-m710q
```

The command should perform the complete provisioning pipeline with minimal user interaction while remaining extremely safe.

The only manual action expected before the command is:

- connect one Ethernet cable between the development PC and the Lenovo
- power the Lenovo on (later this can become Wake-on-LAN)

Everything else should be automated.

---

# Architectural Principles

## 1. Separate three independent concepts

Instead of mixing USB and PXE with provisioning, use three layers.

```text
Delivery
--------
USB
PXE

↓

Transport
---------
Direct Ethernet
Home LAN

↓

Provisioning
------------
SSH
Discovery
Disk selection
Installation
Verification
```

Every layer must expose a clean interface.

Provisioning must never depend on whether rescue was started from USB or PXE.

---

## 2. Delivery

Supported delivery mechanisms:

- USB rescue ISO
- PXE/iPXE
- QEMU

All three must boot exactly the same rescue system.

Only the wrapper differs.

---

## 3. Transport

Treat transport as a pluggable backend.

### Backend A (primary)

Direct Ethernet cable

PC <-------> Lenovo

No switch required.

No router required.

No Internet required.

This becomes the reference provisioning workflow.

### Backend B (future)

Home LAN

Router
Switch
Existing DHCP

This is a future extension.

The provisioning logic must not assume Home LAN.

---

## 4. Provisioning

Provisioning begins only after rescue SSH is reachable.

Pipeline:

1. Wait for SSH.
2. Run hardware discovery.
3. Select safe disk.
4. Ask for confirmation.
5. Run nixos-anywhere.
6. Wait for reboot.
7. Verify installed system.
8. Verify application.
9. Cleanup temporary provisioning services.

---

# New Milestone

Introduce a new milestone before expanding PXE support.

## Temporary Provisioning Environment

The project should be able to temporarily create everything needed for provisioning.

Components:

- dnsmasq
- DHCP
- TFTP
- HTTP
- optional Wake-on-LAN

Those services should exist only during provisioning.

After success or failure they should be stopped automatically.

---

# Direct Ethernet Workflow

Target workflow:

```text
PC
 |
 | Wi-Fi -> Internet (optional)
 |
 +---- Ethernet ---- Lenovo
```

Provisioning network:

192.168.77.0/24

Suggested addresses:

PC
192.168.77.1

Lenovo
DHCP

Internet access on Lenovo is intentionally **not** required.

The rescue environment and installation should complete using only local artifacts.

After verification succeeds the user reconnects Lenovo to the normal network.

---

# just provision-m710q

Create a new high-level command.

Responsibilities:

1.
Verify prerequisites.

- rescue image exists
- provisioning bundle exists
- SSH keys exist

2.
Detect dedicated Ethernet interface.

3.
Verify no conflicting DHCP server is present.

4.
Start temporary:

- dnsmasq
- TFTP
- HTTP

5.
(Optional)
Send Wake-on-LAN.

6.
Wait for PXE or rescue SSH.

7.
Run discovery.

8.
Generate discovery report.

9.
Run safe disk selector.

10.
Display:

- disk
- model
- serial
- size

11.
Require full disk path confirmation.

12.
Run installer.

13.
Wait for reboot.

14.
Reconnect to installed system.

15.
Verify:

- SSH
- Docker
- nginx service
- HTTP endpoint over the direct Ethernet provisioning network

Only after HTTP succeeds should the command report success.

This guarantees that the user can unplug the provisioning cable and connect Lenovo to the normal network with confidence.

16.
Stop temporary services.

17.
Generate final provisioning report.

---

# Installed Target Handling

Current implementation reconnects using the rescue hostname.

Replace this with:

--installed-target

Example:

admin@m710q.local

Fallback strategy:

1.
Explicit installed target.

2.
mDNS hostname.

3.
Previously discovered IP.

---

# CI Safety

Strengthen --ci-disposable.

It should additionally require:

- QEMU DMI
- expected virtual disk identifier
- expected host configuration
- CI environment

The flag alone must never bypass confirmation on physical hardware.

---

# PXE Improvements

Current PXE support should be expanded.

Add:

- ipxe.efi
- boot manifest
- generated HTTP root
- generated TFTP root

Do not require manual downloads.

Everything should come from pinned nixpkgs.

---

# PXE Testing

Create dedicated PXE integration tests.

Workflow:

UEFI firmware

↓

DHCP

↓

TFTP

↓

iPXE

↓

HTTP

↓

boot.ipxe

↓

rescue

↓

SSH

↓

existing provisioning tests

---

# Disk Safety

Immediately before invoking nixos-anywhere:

Repeat disk validation.

Confirm:

- by-id unchanged
- model unchanged
- serial unchanged
- size unchanged
- device still unmounted

Abort otherwise.

---

# Stable by-id Policy

Do not pick the alphabetically first by-id.

Create an explicit priority.

Suggested order:

1.
WWN

2.
NVMe EUI

3.
NVMe serial

4.
ATA

5.
SCSI

Always include every alias in the discovery report.

---

# Rescue Identity

Continue copying host keys.

Future enhancement:

Allow:

--expected-host-key

to eliminate TOFU during provisioning.

---

# Documentation

Expand README with:

- direct Ethernet workflow
- Home LAN workflow (future)
- why isolated DHCP is safer
- why Internet is unnecessary
- Lenovo M710q firmware recommendations
- tested BIOS boot order

---

# Lenovo-specific Notes

Target hardware:

ThinkCentre M710q

Machine type:

10MQ

CPU:

Pentium G4400T

No Intel AMT.

No remote BIOS.

Wake-on-LAN is optional.

Recommended boot order:

Network

↓

USB

↓

Internal SSD

Current testing indicates that when PXE is unavailable the firmware falls back automatically to the next boot device. This should continue to be validated but is now the preferred provisioning strategy.

---

# Do NOT implement yet

Leave for later:

- Actual Budget
- Reverse proxy
- TLS
- VPN
- Automatic router integration
- Automatic router DHCP configuration

The first goal is a robust, repeatable provisioning pipeline.

---

# Provisioning Orchestrator

The repository should explicitly adopt an orchestration architecture instead of
allowing `just provision-m710q` to become a large monolithic script.

## Principle

`just provision-m710q` is an orchestrator.

It should compose a sequence of small, independently testable stages.

Every stage must:

- have a single responsibility;
- expose a stable CLI interface;
- accept explicit inputs;
- produce structured outputs;
- be executable independently;
- be unit-testable whenever possible;
- avoid hidden global state.

## Stage Pipeline

```text
check-prerequisites
        ↓
start-provisioning-network
        ↓
wait-for-rescue
        ↓
discover-hardware
        ↓
select-disk
        ↓
install-system
        ↓
wait-for-installed-system
        ↓
verify-system
        ↓
cleanup
```

## Stage Contracts

### check-prerequisites

Input:
- repository
- flake
- required binaries

Output:
- validation report

### start-provisioning-network

Input:
- selected transport backend

Output:
- running temporary services
- provisioning endpoint description

### wait-for-rescue

Input:
- provisioning endpoint

Output:
- SSH connection

### discover-hardware

Input:
- SSH connection

Output:
- discovery.json

### select-disk

Input:
- discovery.json

Output:
- selected-disk.json

### install-system

Input:
- selected-disk.json
- host configuration

Output:
- installation-report.json

### wait-for-installed-system

Input:
- installation report

Output:
- installed SSH connection

### verify-system

Verify:

- SSH
- Docker
- systemd services
- nginx HTTP endpoint
- application health over the direct provisioning Ethernet

Output:
- verification-report.json

### cleanup

Always execute, including on failure.

Responsibilities:

- stop dnsmasq
- stop HTTP
- stop TFTP
- remove temporary files
- archive logs

---

# Architectural Separation

The codebase should explicitly separate two categories of code.

## Pure decision logic

Examples:

- disk selection
- disk validation
- report parsing
- provisioning planning

Properties:

- no subprocesses
- no SSH
- no filesystem side effects
- deterministic
- unit-test friendly

## System interaction layer

Examples:

- SSH
- nixos-anywhere
- dnsmasq
- TFTP
- HTTP server
- Wake-on-LAN
- process management

Properties:

- isolated adapters
- integration-tested
- replaceable

Business decisions should remain pure.
System interactions should remain isolated.

---

# Project Vision

Treat NixOS as an implementation detail.

The long-term project goal is:

> Deterministic provisioning platform for headless x86_64 mini PCs.

Success means:

Given an empty compatible machine and a Git commit, the platform should
recreate the desired machine deterministically with a single high-level
command while providing strong safety guarantees and comprehensive
verification.


---

# Provisioning Sessions

Introduce the concept of a **Provisioning Session**.

Every execution of `just provision-m710q` should create a unique session
directory containing all artifacts produced during that run.

Suggested layout:

```text
artifacts/
└── sessions/
    └── 2026-07-17T22-31-05/
        ├── discovery.json
        ├── selected-disk.json
        ├── installation-report.json
        ├── verification-report.json
        ├── provisioning.log
        ├── journal.log
        ├── environment.json
        └── metadata.json
```

## Goals

- Preserve complete evidence from every provisioning attempt.
- Make failed installations easy to debug.
- Allow comparison between multiple provisioning runs.
- Archive hardware discovery from physical machines.
- Provide a stable foundation for future HTML reports or diagnostics.
- Allow issues to be reproduced from a single archived session.

## Session Metadata

The metadata should include at least:

- timestamp;
- Git commit hash;
- flake.lock revision;
- target hostname;
- transport backend (Direct Ethernet, Home LAN, etc.);
- delivery backend (USB, PXE, QEMU);
- provisioning result;
- total duration.

## Failure Handling

Even if provisioning fails, the session directory should still be finalized.

Cleanup of temporary services (dnsmasq, TFTP, HTTP, etc.) must not remove
session artifacts.

## Future Direction

In the future, the repository should be able to:

- replay parts of a provisioning session;
- generate human-readable HTML reports;
- compare two sessions and highlight differences;
- attach session bundles automatically to GitHub issues.
