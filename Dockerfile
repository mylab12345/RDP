# syntax=docker/dockerfile:1
#
# Multi-stage, minimal-size Docker image for KB-Remote (rdp-studio).
#
# Includes all runtime dependencies:
#   - Python dependencies: PySide6-Essentials, paramiko, cryptography, pyte,
#     and the optional native Linux terminal renderer (pyside6-qtermwidget)
#   - System / protocol clients: FreeRDP X11 client (xfreerdp3 / xfreerdp) for
#     embedded (/parent-window) and external RDP sessions, OpenSSH client
#     (ssh, sftp, scp, ssh-keygen, ssh-agent), bash PTY shell, xauth, xdg-utils
#   - GUI / Qt6 runtime libraries: X11/XCB (incl. xcb-cursor0), Wayland client,
#     OpenGL/EGL, libxkbcommon, D-Bus, PulseAudio/ALSA, Fontconfig + DejaVu Sans Mono
#
# Size optimizations:
#   - Built on python:3.12-slim-bookworm with --no-install-recommends
#   - Builder stage runs packaging/docker/prune_venv.py to remove transitive
#     PySide6-Addons (QtWebEngine/Chromium, Qt3D, QtMultimedia, ffmpeg), unused
#     QtQuick/QML/Designer/ShaderTools libs, translations, C++ headers, .pyi
#     stubs, pip/setuptools, and strips ELF debug symbols (~580 MB saved)

ARG PYTHON_VERSION=3.12

# =============================================================================
# Stage 1: builder — install Python dependencies and prune unused Qt bloat
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        binutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /opt/venv

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY packaging/docker/prune_venv.py ./packaging/docker/prune_venv.py

# Install KB-Remote with the native Linux terminal extra when a wheel is
# available for the target architecture, falling back cleanly to the portable
# pyte renderer otherwise.
RUN if /opt/venv/bin/pip install --no-cache-dir --no-compile ".[native-terminal]"; then \
        echo "Installed KB-Remote with native Linux terminal renderer"; \
    else \
        echo "Native terminal wheel unavailable on this arch; installing portable core"; \
        /opt/venv/bin/pip install --no-cache-dir --no-compile .; \
    fi \
    && python ./packaging/docker/prune_venv.py /opt/venv \
    && /opt/venv/bin/kb-remote --version

# =============================================================================
# Stage 2: runtime — slim Debian runtime with all protocol & GUI dependencies
# =============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="KB-Remote" \
      org.opencontainers.image.description="Cross-platform SSH/SFTP/RDP remote-access workbench" \
      org.opencontainers.image.source="https://github.com/mylab12345/RDP" \
      org.opencontainers.image.licenses="MIT"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    HOME="/home/kbremote" \
    KB_REMOTE_HOME="/home/kbremote/.config/kb-remote" \
    XDG_RUNTIME_DIR="/tmp/runtime-kbremote"

# Install all system runtime dependencies in a single layer and purge caches/docs:
#   - freerdp3-x11 (or freerdp2-x11 on Bookworm): embedded & external RDP
#   - openssh-client, ca-certificates: SSH/SFTP/SCP/key tools
#   - bash, tini, xauth, xdg-utils: local terminal PTY, init reaper, X11 auth
#   - fonts-dejavu-core, fontconfig: default terminal & UI fonts
#   - libxcb*, libx11*, libxkbcommon*, libwayland*, libgl1, libegl1, libdbus-1-3,
#     libpulse0, libasound2: Qt6 XCB/Wayland/Offscreen platforms & audio
RUN apt-get update \
    && FREERDP_PKG="$(apt-cache show freerdp3-x11 >/dev/null 2>&1 && echo freerdp3-x11 || echo freerdp2-x11)" \
    && apt-get install -y --no-install-recommends \
        "${FREERDP_PKG}" \
        bash \
        ca-certificates \
        fontconfig \
        fonts-dejavu-core \
        libasound2 \
        libdbus-1-3 \
        libegl1 \
        libfontconfig1 \
        libfreetype6 \
        libgl1 \
        libglib2.0-0 \
        libglx0 \
        libopengl0 \
        libpulse0 \
        libwayland-client0 \
        libwayland-cursor0 \
        libwayland-egl1 \
        libx11-6 \
        libx11-xcb1 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-render0 \
        libxcb-shape0 \
        libxcb-shm0 \
        libxcb-sync1 \
        libxcb-util1 \
        libxcb-xfixes0 \
        libxcb-xkb1 \
        libxcb1 \
        libxkbcommon-x11-0 \
        libxkbcommon0 \
        openssh-client \
        tini \
        xauth \
        xdg-utils \
    && apt-get clean \
    && rm -rf \
        /var/lib/apt/lists/* \
        /var/cache/apt/archives/* \
        /usr/share/doc/* \
        /usr/share/man/* \
        /usr/share/info/* \
        /usr/share/locale/*

# Create non-root user (UID/GID 1000 matches standard desktop Linux host user
# for seamless X11/Wayland socket and volume access) and private state dirs.
RUN groupadd -g 1000 kbremote \
    && useradd -m -u 1000 -g 1000 -s /bin/bash kbremote \
    && install -d -m 0700 -o kbremote -g kbremote \
        /home/kbremote/.config/kb-remote \
        /home/kbremote/.ssh \
        /tmp/runtime-kbremote \
    && install -d -m 0755 \
        /usr/share/applications \
        /usr/share/icons/hicolor/scalable/apps \
        /usr/share/icons/hicolor/512x512/apps

COPY --from=builder /opt/venv /opt/venv
COPY packaging/linux/io.github.mylab12345.KBRemote.desktop /usr/share/applications/io.github.mylab12345.KBRemote.desktop
COPY src/rdpstudio/resources/icons/logo.svg /usr/share/icons/hicolor/scalable/apps/io.github.mylab12345.KBRemote.svg
COPY src/rdpstudio/resources/icons/logo.png /usr/share/icons/hicolor/512x512/apps/io.github.mylab12345.KBRemote.png
COPY --chmod=0755 packaging/docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh

USER kbremote
WORKDIR /home/kbremote

# Persistent application state (sessions, encrypted vault, known_hosts, logs)
VOLUME ["/home/kbremote/.config/kb-remote"]

# Built-in SFTP share server port (opt-in from GUI / settings)
EXPOSE 2222

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD QT_QPA_PLATFORM=offscreen kb-remote --version >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["kb-remote"]
