# Writing protocol plugins

Every protocol in KB-Remote — including SSH and RDP — is a plugin. The UI
(tabs, sidebar, session editor, quick-connect) is protocol-agnostic and talks
only to two interfaces:

```python
from rdpstudio.core.plugin import ProtocolPlugin, SessionController, Capabilities

class MyPlugin(ProtocolPlugin):
    id = "vnc"                       # unique, stable
    title = "VNC"
    description = "Remote framebuffer to Linux/Windows desktops"
    default_port = 5900
    icon_name = "server"             # resources/icons/<name>.svg

    def create_session(self, definition, ctx) -> SessionController:
        return VncController(definition, ctx)

    def build_editor(self, definition, parent):      # optional
        return VncOptionsPage(definition, parent)    # extra editor page

    def quick_connect_target(self, text):            # optional
        ...  # parse "host:5902" into a Session
```

```python
class VncController(SessionController):
    # signals you get for free:
    #   titleChanged(str), stateChanged(str), statusInfo(dict),
    #   finished(str), reconnectScheduled(int, float)

    def start(self): ...
    def stop(self, reason=""): ...            # MUST emit finished() once
    def widget(self) -> QWidget: ...          # embedded in the tab
    def capabilities(self) -> Capabilities:   # shells get keyboard focus etc.
        return Capabilities(external_window=False)
```

`SessionContext` hands you everything you need:

| field | what it is |
|---|---|
| `settings` | user preferences (keepalive, scrollback, theme…) |
| `store` | session store (persist extra options in `Session.options`) |
| `vault` | credential vault (resolve `definition.credential_id`) |
| `prompter` | thread-safe prompts (`ask_secret`, `ask_host_key`) |
| `bus` | pub/sub for cross-cutting events (`session/connected`, …) |

## Registering

**Built-in**: add a package under `rdpstudio/protocols/<id>/` whose
`__init__.py` registers itself with `registry()` (see `ssh/__init__.py`).

**Third-party** (no fork needed): declare an entry point —

```toml
[project.entry-points."rdpstudio.protocols"]
vnc = "rdpstudio_vnc:VncPlugin"
```

— and `pip install` your package. It appears in the New-session dialog,
sidebar icons and quick-connect automatically.

## Conventions worth keeping

1. **Never block the GUI thread.** Own a `QThread` (or `QProcess`) and cross
   boundaries with signals. Connect `QThread.started` *directly to a slot of
   the object you moved to that thread* (a receiver method would execute on
   the receiver's thread — including a controller living on the GUI thread).
2. **Emit `finished(reason)` exactly once**; the tab cleans up after it.
3. **Prompts** must go through `ctx.prompter` (workers may be on any thread;
   `GuiPromptProvider` marshals to the GUI thread and blocks the caller).
4. **Persist options** in `Session.options` (free-form dict) so you never
   need to touch the store schema.
5. **Secrets**: resolve from the vault at connect time; call
   `core.log.redact_secret(value)` for anything that might reach a log.

## Worked examples in-tree

- `protocols/ssh/session.py` — full in-app shell (worker thread, tunnels,
  SFTP, reconnect)
- `protocols/rdp/session.py` — external-process protocol with monitor tab
- `protocols/local/session.py` — PTY-based local terminal

## Roadmap idea: in-process RDP

`protocols/rdp/negotiate.py` already implements the X.224 negotiation layer
in pure Python. A full in-process client would extend it with
TLS (via `ssl`), CredSSP, and the graphics pipeline (fast-path/RFX) rendered
to a `QOpenGLWidget`, wrapped in the same `SessionController` contract — the
UI would not change by a single line.
