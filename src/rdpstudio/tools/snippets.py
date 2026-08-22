"""Command snippets & macros store with categorized presets."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..core import paths


@dataclass
class Snippet:
    name: str
    command: str
    category: str = "General"
    description: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snippet:
        return cls(
            id=str(data.get("id", uuid.uuid4().hex[:10])),
            name=str(data.get("name", "Untitled")),
            command=str(data.get("command", "")),
            category=str(data.get("category", "General")),
            description=str(data.get("description", "")),
        )

    def render(self, context: dict[str, str] | None = None) -> str:
        """Replace placeholders such as $HOST, $USER, $PORT, $SELECTION."""
        ctx = context or {}
        rendered = self.command
        for key, val in ctx.items():
            rendered = rendered.replace(f"${key.upper()}", str(val))
            rendered = rendered.replace(f"${{{key.upper()}}}", str(val))
        return rendered


DEFAULT_SNIPPETS: list[dict[str, str]] = [
    # System Info
    {
        "category": "System Info",
        "name": "OS & Kernel Info",
        "command": "uname -a && (lsb_release -d 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME)",
        "description": "Kernel version, distro, and architecture",
    },
    {
        "category": "System Info",
        "name": "CPU & Hardware Summary",
        "command": "lscpu | grep -E 'Model name|Socket|Thread|NUMA|CPU\\(s\\)'",
        "description": "CPU models, core counts, and topology",
    },
    {
        "category": "System Info",
        "name": "Memory Usage (MB)",
        "command": "free -m -h",
        "description": "Human-readable RAM and swap usage",
    },
    {
        "category": "System Info",
        "name": "Uptime & System Load",
        "command": "uptime",
        "description": "System uptime and 1/5/15 minute load averages",
    },
    # Disk & Files
    {
        "category": "Disk & Storage",
        "name": "Disk Free (Human)",
        "command": "df -hT -x tmpfs -x devtmpfs",
        "description": "Filesystem usage excluding temporary mounts",
    },
    {
        "category": "Disk & Storage",
        "name": "Largest Directories (Top 10)",
        "command": "du -ahx / 2>/dev/null | sort -rh | head -n 10",
        "description": "Find top 10 largest directories on root filesystem",
    },
    {
        "category": "Disk & Storage",
        "name": "I/O Disk Activity (iostat)",
        "command": "iostat -xz 1 3 2>/dev/null || vmstat 1 5",
        "description": "Device I/O throughput and utilization",
    },
    # Processes & Monitoring
    {
        "category": "Processes",
        "name": "Top CPU Consumers",
        "command": "ps aux --sort=-%cpu | head -n 15",
        "description": "Top 15 processes ranked by CPU usage",
    },
    {
        "category": "Processes",
        "name": "Top Memory Consumers",
        "command": "ps aux --sort=-%mem | head -n 15",
        "description": "Top 15 processes ranked by memory consumption",
    },
    {
        "category": "Processes",
        "name": "Process Tree",
        "command": "pstree -p 2>/dev/null || ps -ef --forest",
        "description": "Hierarchical process tree view",
    },
    # Networking
    {
        "category": "Network",
        "name": "Listening Ports & Services",
        "command": "ss -tulpn 2>/dev/null || netstat -tulpn",
        "description": "All listening TCP/UDP sockets with process names",
    },
    {
        "category": "Network",
        "name": "Network Interfaces & IPs",
        "command": "ip -br addr show 2>/dev/null || ifconfig -a",
        "description": "Network adapter names, states, and IPv4/IPv6 addresses",
    },
    {
        "category": "Network",
        "name": "Established Sockets",
        "command": "ss -s 2>/dev/null || netstat -s",
        "description": "Socket summary statistics",
    },
    {
        "category": "Network",
        "name": "DNS Test & Connectivity",
        "command": "ping -c 3 8.8.8.8 && curl -Is https://pypi.org | head -n 1",
        "description": "Verify external gateway and HTTP connectivity",
    },
    # Docker & Containers
    {
        "category": "Docker & Containers",
        "name": "Running Containers",
        "command": "docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}'",
        "description": "Clean tabular view of active docker containers",
    },
    {
        "category": "Docker & Containers",
        "name": "Container Resource Stats",
        "command": "docker stats --no-stream",
        "description": "Snapshot of container CPU, RAM, and network I/O",
    },
    {
        "category": "Docker & Containers",
        "name": "Docker Disk Usage",
        "command": "docker system df",
        "description": "Space used by images, containers, and volumes",
    },
    # Logs & Services
    {
        "category": "Services & Logs",
        "name": "Systemd Failed Units",
        "command": "systemctl --failed",
        "description": "List all failed systemd services and units",
    },
    {
        "category": "Services & Logs",
        "name": "Recent System Errors",
        "command": "journalctl -p 3 -xb --no-pager -n 30 2>/dev/null || dmesg -T | grep -i err | tail -n 20",
        "description": "Last 30 priority-3 (error) log entries from current boot",
    },
    {
        "category": "Services & Logs",
        "name": "Recent User Logins",
        "command": "last -n 15",
        "description": "Recent interactive login history and IP origins",
    },
]


class SnippetStore:
    """JSON-backed persistent store for snippets with presets."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.snippets_file()
        self._snippets: dict[str, Snippet] = {}
        self.reload()

    def reload(self) -> None:
        self._snippets.clear()
        if not self.path.exists():
            self._load_defaults()
            self.save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        s = Snippet.from_dict(item)
                        self._snippets[s.id] = s
            elif isinstance(data, dict) and "snippets" in data:
                for item in data["snippets"]:
                    if isinstance(item, dict):
                        s = Snippet.from_dict(item)
                        self._snippets[s.id] = s
            else:
                self._load_defaults()
        except Exception:
            self._load_defaults()

    def _load_defaults(self) -> None:
        self._snippets.clear()
        for d in DEFAULT_SNIPPETS:
            s = Snippet(
                name=d["name"],
                command=d["command"],
                category=d.get("category", "General"),
                description=d.get("description", ""),
            )
            self._snippets[s.id] = s

    def snippets(self) -> list[Snippet]:
        return sorted(self._snippets.values(), key=lambda s: (s.category.lower(), s.name.lower()))

    def get(self, snippet_id: str) -> Snippet | None:
        return self._snippets.get(snippet_id)

    def upsert(self, snippet: Snippet) -> None:
        self._snippets[snippet.id] = snippet
        self.save()

    def delete(self, snippet_id: str) -> bool:
        if snippet_id in self._snippets:
            del self._snippets[snippet_id]
            self.save()
            return True
        return False

    def categories(self) -> list[str]:
        cats = {s.category for s in self._snippets.values() if s.category}
        return sorted(cats, key=str.lower)

    def reset_defaults(self) -> None:
        self._load_defaults()
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [s.to_dict() for s in self.snippets()]
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".snippets-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
