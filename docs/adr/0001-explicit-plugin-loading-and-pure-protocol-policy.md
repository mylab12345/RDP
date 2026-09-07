# ADR 0001: Explicit plugin loading and pure protocol policy modules

- **Status:** Accepted
- **Date:** 2026-09-07

## Context

Python imports a package's `__init__.py` before any child module. The SSH, RDP,
and local package initializers used to register themselves globally. Therefore
importing `rdpstudio.protocols.rdp.negotiate` also imported the Qt plugin
contract and all built-in controllers. Pure probes and command builders were
not usable in minimal/headless processes, and registration depended on import
cache state after `reset_registry()`.

RDP client discovery and FreeRDP argument construction also lived in the Qt
session controller, despite having no UI dependency.

## Decision

1. Protocol package initializers are side-effect free.
2. `core.plugin.BUILTIN_PLUGIN_SPECS` names each built-in class, and
   `PluginRegistry.load_builtins()` imports/instantiates it when `registry()` is
   explicitly requested.
3. Pure RDP client policy lives in `protocols.rdp.client`; the Qt controller
   imports it and keeps historical forwarding names for compatibility.
4. Type-only references from pure helpers use `TYPE_CHECKING` imports.

## Consequences

- Probes, `.rdp` generation, key helpers, and command policy can run without
  importing PySide.
- Registry reset/reload is deterministic.
- Adding a built-in requires one explicit spec; third-party plugins continue to
  use the existing `rdpstudio.protocols` entry-point group.
- Code that relied on undocumented “import package to register globally” side
  effects must request `registry()` instead. Public application behavior and
  documented third-party discovery are unchanged.

## Verification

`tests/test_architecture_boundaries.py` imports pure helpers in fresh
subprocesses and fails if PySide or `core.plugin` appears. Existing registry and
quick-connect tests verify all built-ins still load.
