#twentytw93-KronosTeam
from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import xbmc
import xbmcaddon
import xbmcvfs

# ---------------------------------------------------------------------------
# Add-on metadata / paths
# ---------------------------------------------------------------------------

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")

HOST = "0.0.0.0"   # Listen on all interfaces (LAN)
PORT = 9001        # Static port for Kronos Remote LAN

# Translate special:// path to real filesystem path
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
INTERFACE_HTML_PATH = os.path.join(ADDON_PATH, "resources", "interface.html")

# Cache for interface.html contents
_INTERFACE_CACHE = None


def load_interface_html() -> str:
    """
    Load interface.html from resources folder.
    Cached in memory after first read.
    """
    global _INTERFACE_CACHE

    if _INTERFACE_CACHE is not None:
        return _INTERFACE_CACHE

    try:
        if not os.path.isfile(INTERFACE_HTML_PATH):
            xbmc.log(
                f"[{ADDON_ID}] interface.html not found at: {INTERFACE_HTML_PATH}",
                xbmc.LOGERROR,
            )
            return "<h1>Kronos Remote LAN</h1><p>interface.html missing.</p>"

        with open(INTERFACE_HTML_PATH, "r", encoding="utf-8") as f:
            _INTERFACE_CACHE = f.read()
        return _INTERFACE_CACHE
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to load interface.html: {exc}",
            xbmc.LOGERROR,
        )
        return "<h1>Kronos Remote LAN</h1><p>Error loading interface.html.</p>"


# ---------------------------------------------------------------------------
# App shortcut helpers
# ---------------------------------------------------------------------------


def _open_elementum_movies() -> bool:
    """
    Open Elementum Movies section.
    """
    try:
        xbmc.executebuiltin(
            'ActivateWindow(Videos,"plugin://plugin.video.elementum/movies/",return)'
        )
        xbmc.log(
            f"[{ADDON_ID}] Shortcut: Elementum Movies",
            xbmc.LOGDEBUG,
        )
        return True
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to open Elementum Movies: {exc}",
            xbmc.LOGERROR,
        )
        return False


def _open_elementum_tvshows() -> bool:
    """
    Open Elementum TV Shows section.
    """
    try:
        xbmc.executebuiltin(
            'ActivateWindow(Videos,"plugin://plugin.video.elementum/shows/",return)'
        )
        xbmc.log(
            f"[{ADDON_ID}] Shortcut: Elementum TV Shows",
            xbmc.LOGDEBUG,
        )
        return True
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to open Elementum TV Shows: {exc}",
            xbmc.LOGERROR,
        )
        return False


def _open_watchnixtoon2() -> bool:
    """
    Open WatchNixtoon2 addon root.
    """
    try:
        xbmc.executebuiltin(
            'ActivateWindow(Videos,"plugin://plugin.video.watchnixtoons2/",return)'
        )
        xbmc.log(
            f"[{ADDON_ID}] Shortcut: WatchNixtoon2",
            xbmc.LOGDEBUG,
        )
        return True
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to open WatchNixtoon2: {exc}",
            xbmc.LOGERROR,
        )
        return False


def _open_iptv_simple() -> bool:
    """
    Open TV Channels (PVR / IPTV Simple).
    """
    try:
        xbmc.executebuiltin("ActivateWindow(TVChannels)")
        xbmc.log(
            f"[{ADDON_ID}] Shortcut: IPTV Simple (TVChannels)",
            xbmc.LOGDEBUG,
        )
        return True
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to open IPTV Simple / TVChannels: {exc}",
            xbmc.LOGERROR,
        )
        return False


def _download_subtitles() -> bool:
    """
    Trigger subtitle download, but ONLY when media playback is happening
    from plugin.video.elementum.
    """
    try:
        player = xbmc.Player()

        # 1) Must be playing video
        if not player.isPlayingVideo():
            xbmc.log(
                f"[{ADDON_ID}] _download_subtitles: no video playing, aborting.",
                xbmc.LOGDEBUG,
            )
            return False

        # 2) Must be Elementum playback
        current_path = xbmc.getInfoLabel("Player.FilenameAndPath") or ""
        if not current_path.startswith("plugin://plugin.video.elementum"):
            xbmc.log(
                f"[{ADDON_ID}] _download_subtitles: playback is not from plugin.video.elementum, aborting. Path={current_path}",
                xbmc.LOGDEBUG,
            )
            return False

        # 3) We are in Elementum playback -> trigger subtitle search
        xbmc.log(
            f"[{ADDON_ID}] _download_subtitles: Elementum playback detected, opening subtitle search window...",
            xbmc.LOGDEBUG,
        )

        xbmc.executebuiltin("ActivateWindow(subtitlesearch)")
        xbmc.log(
            f"[{ADDON_ID}] _download_subtitles: subtitle search window activated.",
            xbmc.LOGDEBUG,
        )

        xbmc.sleep(100)
        return True

    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to download subtitles: {exc}",
            xbmc.LOGERROR,
        )

        # Last resort: try the basic Kodi subtitle search
        try:
            xbmc.executebuiltin("XBMC.Subtitles.Search")
            xbmc.log(
                f"[{ADDON_ID}] _download_subtitles: fallback XBMC.Subtitles.Search triggered.",
                xbmc.LOGDEBUG,
            )
            return True
        except Exception:
            xbmc.log(
                f"[{ADDON_ID}] _download_subtitles: fallback subtitle search also failed.",
                xbmc.LOGERROR,
            )
            return False


def _get_nowplaying_string() -> str:
    """
    Build a compact 'Now Playing' string for /nowplaying endpoint.

    Examples:
    - "Idle"
    - "Elementum · Movie Name (01:23 / 02:10)"
    - "TV · Channel Name (00:15 / 00:30)"
    """
    try:
        player = xbmc.Player()

        if not (player.isPlayingVideo() or player.isPlayingAudio()):
            return "Connected · No playback"

        title = xbmc.getInfoLabel("Player.Title") or "Unknown"
        path = xbmc.getInfoLabel("Player.FilenameAndPath") or ""
        time_label = xbmc.getInfoLabel("Player.Time") or ""
        duration_label = xbmc.getInfoLabel("Player.Duration") or ""

        prefix = ""
        if path.startswith("plugin://plugin.video.elementum"):
            prefix = "Elementum · "
            # keep Kodi's title for Elementum
        elif path.startswith("pvr://"):
            # Force a clean, generic label for IPTV Simple
            prefix = "TV - "
            title = "LiveStream"

        if time_label and duration_label:
            return f"{prefix}{title} ({time_label} / {duration_label})"
        return f"{prefix}{title}"
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] _get_nowplaying_string failed: {exc}",
            xbmc.LOGERROR,
        )
        return "Idle"


# ---------------------------------------------------------------------------
# Kodi action mapping
# ---------------------------------------------------------------------------


def perform_kodi_action(key: str) -> bool:
    """
    Map key from HTTP (/nav?key=...) to Kodi Action() calls or shortcut helpers.

    Returns True if an action was performed, False if key is unknown.
    """
    key = (key or "").strip().lower()

    # Special handling for "home" – go to real Home window
    if key == "home":
        try:
            xbmc.executebuiltin("ActivateWindow(Home)")
            xbmc.log(
                f"[{ADDON_ID}] Remote key 'home' -> ActivateWindow(Home)",
                xbmc.LOGDEBUG,
            )
            return True
        except Exception as exc:
            xbmc.log(
                f"[{ADDON_ID}] Failed to activate Home window: {exc}",
                xbmc.LOGERROR,
            )
            return False

    # App shortcuts
    if key == "elem_movies":
        return _open_elementum_movies()
    if key == "elem_tv":
        return _open_elementum_tvshows()
    if key == "wnt":
        return _open_watchnixtoon2()
    if key == "iptv":
        return _open_iptv_simple()

    # Subtitle download shortcut
    if key == "subs_download":
        return _download_subtitles()

    # Navigation / playback / volume
    mapping = {
        # Navigation
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "ok": "Select",
        "select": "Select",
        "enter": "Select",
        "back": "Back",

        # Playback (transport)
        "prev": "SkipPrevious",
        "rew": "Rewind",
        "playpause": "PlayPause",
        "fwd": "FastForward",
        "next": "SkipNext",
        "stop": "Stop",

        # OSD - Use Info instead of OSD to avoid toggle behavior
        "osd": "Info",

        # Volume
        "volup": "VolumeUp",
        "voldown": "VolumeDown",
        "mute": "Mute",
    }

    action = mapping.get(key)
    if not action:
        return False

    try:
        xbmc.executebuiltin(f"Action({action})")
        xbmc.log(
            f"[{ADDON_ID}] Remote key '{key}' -> Action({action})",
            xbmc.LOGDEBUG,
        )
        return True
    except Exception as exc:
        xbmc.log(
            f"[{ADDON_ID}] Failed to perform action for key '{key}': {exc}",
            xbmc.LOGERROR,
        )
        return False


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class KronosRemoteRequestHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP handler for Kronos Remote LAN.
    """

    server_version = "KronosRemoteHTTP/1.0"

    def log_message(self, format, *args):
        """
        Override to keep HTTP noise out of Kodi logs.
        Uncomment to debug HTTP traffic.
        """
        return

    def _send_response(self, code: int, body: str,
                       content_type: str = "text/plain; charset=utf-8"):
        body_bytes = body.encode("utf-8", errors="replace")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    # ---------- GET ----------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path in ("/", "/index.html"):
            html = load_interface_html()
            self._send_response(200, html, "text/html; charset=utf-8")
            return

        if path == "/ping":
            self._send_response(200, "pong")
            return

        if path == "/nowplaying":
            text = _get_nowplaying_string()
            self._send_response(200, text, "text/plain; charset=utf-8")
            return

        # Unknown path
        self._send_response(404, "Not found")

    # ---------- POST ----------

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path == "/nav":
            qs = parse_qs(parsed.query)
            key = qs.get("key", [""])[0]
            if not key:
                self._send_response(400, "missing key param")
                return

            ok = perform_kodi_action(key)
            if ok:
                self._send_response(200, "ok")
            else:
                self._send_response(400, "unknown key")
            return

        # Unknown POST path
        self._send_response(404, "Not found")


# ---------------------------------------------------------------------------
# Service runner
# ---------------------------------------------------------------------------


class KronosRemoteService(object):
    """
    Wrapper to start/stop the HTTP server and integrate with xbmc.Monitor.
    """

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None

    def start(self) -> bool:
        """
        Start the ThreadingHTTPServer in a background thread.
        Returns True on success.
        """
        try:
            self._server = ThreadingHTTPServer(
                (self.host, self.port),
                KronosRemoteRequestHandler
            )
        except Exception as exc:
            xbmc.log(
                f"[{ADDON_ID}] Failed to bind HTTP server on {self.host}:{self.port} - {exc}",
                xbmc.LOGERROR,
            )
            self._server = None
            return False

        def _run_server():
            try:
                self._server.serve_forever()
            except Exception as exc:
                xbmc.log(
                    f"[{ADDON_ID}] HTTP server exception: {exc}",
                    xbmc.LOGERROR,
                )

        self._thread = threading.Thread(target=_run_server, daemon=True)
        self._thread.start()

        xbmc.log(
            f"[{ADDON_ID}] Kronos Remote LAN service started on {self.host}:{self.port}",
            xbmc.LOGINFO,
        )
        return True

    def stop(self):
        """
        Stop the HTTP server cleanly.
        """
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception as exc:
                xbmc.log(
                    f"[{ADDON_ID}] Error shutting down HTTP server: {exc}",
                    xbmc.LOGERROR,
                )

        xbmc.log(
            f"[{ADDON_ID}] Kronos Remote LAN service stopped",
            xbmc.LOGINFO,
        )


def run():
    """
    Entry point called by Kodi when the service starts.
    """
    monitor = xbmc.Monitor()
    service = KronosRemoteService()

    if not service.start():
        xbmc.log(
            f"[{ADDON_ID}] Kronos Remote LAN service failed to start, exiting.",
            xbmc.LOGERROR,
        )
        return

    # Keep service alive until Kodi requests abort
    while not monitor.abortRequested():
        if monitor.waitForAbort(1.0):
            break

    service.stop()


if __name__ == "__main__":
    run()
