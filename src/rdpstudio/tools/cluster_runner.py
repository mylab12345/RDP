"""Multi-host parallel command runner across saved SSH sessions."""

from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import paramiko

from ..core import paths
from ..core.models import AUTH_AGENT, AUTH_CREDENTIAL, AUTH_KEY, Session
from ..core.plugin import SessionContext
from ..protocols.ssh.knownhosts import KnownHostsVerifier


@dataclass
class ClusterHostResult:
    session_id: str
    host: str
    display_name: str
    status: str  # "success" | "failed" | "timeout" | "auth_error" | "conn_error"
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClusterRunner:
    """Executes commands concurrently across multiple SSH sessions."""

    def __init__(self, ctx: SessionContext, max_workers: int = 20) -> None:
        self.ctx = ctx
        self.max_workers = max_workers
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def execute(
        self,
        sessions: list[Session],
        command: str,
        timeout: int = 15,
        on_host_done: Callable[[ClusterHostResult], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[ClusterHostResult]:
        self._cancelled = False
        ssh_sessions = [s for s in sessions if s.protocol == "ssh"]
        total = len(ssh_sessions)
        if total == 0:
            return []

        completed = 0
        results: list[ClusterHostResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, total)) as executor:
            future_to_session = {
                executor.submit(self._exec_single, s, command, timeout): s
                for s in ssh_sessions
            }

            for future in concurrent.futures.as_completed(future_to_session):
                s = future_to_session[future]
                if self._cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    res = future.result()
                except Exception as exc:
                    res = ClusterHostResult(
                        session_id=s.id,
                        host=s.host,
                        display_name=s.display_name(),
                        status="failed",
                        error=str(exc),
                    )
                results.append(res)
                if on_host_done is not None:
                    on_host_done(res)
                completed += 1
                if on_progress is not None:
                    on_progress(completed, total)

        return results

    def _exec_single(self, session: Session, command: str, timeout: int) -> ClusterHostResult:
        name = session.display_name()
        host = session.host
        port = session.port or 22
        user = session.username or "root"
        start_time = time.perf_counter()

        # Resolve credentials
        password = session.password or None
        key_filename = session.key_path or None

        if session.auth == AUTH_CREDENTIAL and session.credential_id:
            try:
                cred = self.ctx.vault.get(session.credential_id)
                if cred and cred.secret:
                    if cred.kind in ("password", "secret"):
                        password = cred.secret
                    elif cred.kind == "passphrase":
                        pass
            except Exception:
                pass
        elif session.auth == AUTH_KEY and not key_filename:
            pass

        client = paramiko.SSHClient()
        kh_path = Path(paths.known_hosts_file())
        client.set_missing_host_key_policy(
            KnownHostsVerifier(kh_path, policy=self.ctx.settings.host_key_policy, prompter=None)
        )

        try:
            client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password,
                key_filename=key_filename,
                timeout=float(timeout),
                allow_agent=(session.auth == AUTH_AGENT),
                look_for_keys=(session.auth in (AUTH_KEY, AUTH_AGENT)),
                banner_timeout=float(timeout),
                auth_timeout=float(timeout),
            )

            stdin, stdout_f, stderr_f = client.exec_command(command, timeout=float(timeout))
            chan = stdout_f.channel
            try:
                chan.settimeout(float(timeout))
            except Exception:
                pass
            # Bound memory if a host streams forever.
            _max = 8 * 1024 * 1024
            out_bytes = stdout_f.read(_max)
            err_bytes = stderr_f.read(_max)
            exit_status = chan.recv_exit_status()
            duration = time.perf_counter() - start_time

            out_text = out_bytes.decode("utf-8", "replace")
            err_text = err_bytes.decode("utf-8", "replace")
            status = "success" if exit_status == 0 else "failed"

            return ClusterHostResult(
                session_id=session.id,
                host=host,
                display_name=name,
                status=status,
                exit_code=exit_status,
                stdout=out_text,
                stderr=err_text,
                duration_s=duration,
            )

        except (paramiko.AuthenticationException, paramiko.PasswordRequiredException) as exc:
            return ClusterHostResult(
                session_id=session.id,
                host=host,
                display_name=name,
                status="auth_error",
                duration_s=time.perf_counter() - start_time,
                error=f"Authentication failed: {exc}",
            )
        except (TimeoutError, paramiko.SSHException) as exc:
            is_timeout = "timeout" in str(exc).lower() or isinstance(exc, TimeoutError)
            return ClusterHostResult(
                session_id=session.id,
                host=host,
                display_name=name,
                status="timeout" if is_timeout else "conn_error",
                duration_s=time.perf_counter() - start_time,
                error=str(exc),
            )
        except Exception as exc:
            return ClusterHostResult(
                session_id=session.id,
                host=host,
                display_name=name,
                status="failed",
                duration_s=time.perf_counter() - start_time,
                error=str(exc),
            )
        finally:
            try:
                client.close()
            except Exception:
                pass
