"""Command snippets & macros store with categorized presets."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..core import paths
from ..core.persistence import atomic_write_text


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

    def duplicate(self, snippet_id: str) -> Snippet | None:
        """Create a separately editable copy of a saved snippet."""
        source = self.get(snippet_id)
        if source is None:
            return None
        duplicate = Snippet.from_dict(source.to_dict())
        duplicate.id = uuid.uuid4().hex[:10]
        existing_names = {snippet.name for snippet in self._snippets.values()}
        duplicate.name = self._unique_copy_name(source.name, existing_names)
        self._snippets[duplicate.id] = duplicate
        try:
            self.save()
        except Exception:
            self._snippets.pop(duplicate.id, None)
            raise
        return duplicate

    def export_dict(self) -> dict[str, Any]:
        """Return a portable, versioned snippet library.

        The explicit envelope leaves room for future metadata while still
        letting :meth:`import_dict` accept the original list-only file format.
        """
        return {
            "format": 1,
            "snippets": [snippet.to_dict() for snippet in self.snippets()],
        }

    def import_dict(self, data: object) -> int:
        """Merge a snippet-library payload without replacing local entries.

        Invalid entries are ignored.  A colliding id receives a new id and a
        colliding name is given a stable ``(imported N)`` suffix, so importing
        the same library twice never overwrites a locally edited command.
        """
        if isinstance(data, dict):
            raw_snippets = data.get("snippets", [])
        else:
            raw_snippets = data
        if not isinstance(raw_snippets, list):
            return 0

        candidates = [Snippet.from_dict(item) for item in raw_snippets if isinstance(item, dict)]
        candidates = [snippet for snippet in candidates if snippet.name.strip() and snippet.command.strip()]
        if not candidates:
            return 0

        previous = dict(self._snippets)
        existing_names = {snippet.name for snippet in self._snippets.values()}
        imported = 0
        for snippet in candidates:
            while not snippet.id or snippet.id in self._snippets:
                snippet.id = uuid.uuid4().hex[:10]
            if snippet.name in existing_names:
                snippet.name = self._unique_import_name(snippet.name, existing_names)
            self._snippets[snippet.id] = snippet
            existing_names.add(snippet.name)
            imported += 1
        try:
            self.save()
        except Exception:
            self._snippets = previous
            raise
        return imported

    @staticmethod
    def _unique_import_name(name: str, existing_names: set[str]) -> str:
        candidate = f"{name} (imported)"
        if candidate not in existing_names:
            return candidate
        index = 2
        while f"{name} (imported {index})" in existing_names:
            index += 1
        return f"{name} (imported {index})"

    @staticmethod
    def _unique_copy_name(name: str, existing_names: set[str]) -> str:
        candidate = f"{name} (copy)"
        if candidate not in existing_names:
            return candidate
        index = 2
        while f"{name} (copy {index})" in existing_names:
            index += 1
        return f"{name} (copy {index})"

    def categories(self) -> list[str]:
        cats = {s.category for s in self._snippets.values() if s.category}
        return sorted(cats, key=str.lower)

    def reset_defaults(self) -> None:
        self._load_defaults()
        self.save()

    def save(self) -> None:
        payload = [s.to_dict() for s in self.snippets()]
        atomic_write_text(
            self.path,
            json.dumps(payload, indent=2),
            prefix=".snippets-",
        )
