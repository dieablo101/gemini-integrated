"""Lightweight multi-instance HTTP & Server-Sent Events (SSE) daemon.

Zero external dependencies: uses Python standard library only.
Supports running multiple isolated servers concurrently on different ports
(e.g., Wingman on 8888, Inspector on 8889).
"""

from __future__ import annotations

import errno
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import queue
import socket
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.parse


class WebAppletHandler(BaseHTTPRequestHandler):
    """Custom request handler dispatching to registered routes and SSE streams."""

    # Silence default console logging of every HTTP GET/POST request
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def handle(self) -> None:
        """Wraps request handling loop to catch client disconnects cleanly."""
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        except OSError as exc:
            if exc.errno in (errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED, errno.ENOTCONN):
                pass
            else:
                raise

    def finish(self) -> None:
        """Ensures socket flush on disconnect does not raise unhandled exceptions."""
        try:
            if not self.wfile.closed:
                try:
                    self.wfile.flush()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            super().finish()
        except Exception:
            pass

    @property
    def engine(self) -> WebAppletEngine:
        return self.server.engine  # type: ignore

    def do_OPTIONS(self) -> None:
        """Permissive CORS pre-flight support for local node browsers."""
        try:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.end_headers()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
            self.close_connection = True

    def do_GET(self) -> None:
        try:
            self.engine.record_client_activity(self.client_address[0])
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            # 1. Check SSE stream route
            if path == self.engine.sse_path:
                self._handle_sse_stream()
                return

            # 2. Match exact registered GET routes
            handler = self.engine.get_routes.get(path)
            if handler:
                self._execute_route_handler(handler, query, None)
                return

            # 3. Match prefix route handlers
            for prefix, p_handler in self.engine.prefix_get_routes.items():
                if path.startswith(prefix):
                    self._execute_route_handler(p_handler, query, None)
                    return

            # 4. Default 404
            self.send_response(HTTPStatus.NOT_FOUND)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Path not found: {path}"}).encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            self.close_connection = True
        except OSError as exc:
            if exc.errno in (errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED, errno.ENOTCONN):
                self.close_connection = True
            else:
                raise

    def do_POST(self) -> None:
        try:
            self.engine.record_client_activity(self.client_address[0])
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
            body: Any = {}
            if body_bytes:
                try:
                    body = json.loads(body_bytes.decode("utf-8"))
                except Exception:
                    body = body_bytes

            handler = self.engine.post_routes.get(path)
            if handler:
                self._execute_route_handler(handler, query, body)
                return

            for prefix, p_handler in self.engine.prefix_post_routes.items():
                if path.startswith(prefix):
                    self._execute_route_handler(p_handler, query, body)
                    return

            self.send_response(HTTPStatus.NOT_FOUND)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"POST path not found: {path}"}).encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            self.close_connection = True
        except OSError as exc:
            if exc.errno in (errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED, errno.ENOTCONN):
                self.close_connection = True
            else:
                raise

    def _execute_route_handler(self, handler: Callable[..., Any], query: Dict[str, List[str]], body: Any) -> None:
        try:
            res = handler(self, query, body) if body is not None else handler(self, query)
            if res is None:
                return  # Handler wrote response directly

            status_code = HTTPStatus.OK
            content_type = "application/json"
            data_bytes = b""

            if isinstance(res, tuple):
                status_code = res[0]
                payload = res[1]
                if len(res) > 2:
                    content_type = res[2]
            else:
                payload = res

            if isinstance(payload, str):
                if content_type == "application/json":
                    content_type = "text/html; charset=utf-8" if payload.strip().startswith("<") else "text/plain"
                data_bytes = payload.encode("utf-8")
            elif isinstance(payload, bytes):
                data_bytes = payload
            elif isinstance(payload, dict) or isinstance(payload, list):
                content_type = "application/json"
                data_bytes = json.dumps(payload).encode("utf-8")

            self.send_response(status_code)
            self._send_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data_bytes)))
            self.end_headers()
            self.wfile.write(data_bytes)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            self.close_connection = True
            return
        except OSError as exc:
            if exc.errno in (errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED, errno.ENOTCONN):
                self.close_connection = True
                return
            raise
        except Exception as exc:
            try:
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
                self.close_connection = True

    def _handle_sse_stream(self) -> None:
        """Streams Server-Sent Events (SSE) to connected browser tab."""
        self.close_connection = True
        try:
            self.send_response(HTTPStatus.OK)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
            return

        client_q: queue.Queue[Tuple[str, str]] = queue.Queue(maxsize=100)
        self.engine.register_sse_client(client_q)
        try:
            # Send initial connected greeting event
            init_msg = f"event: connected\ndata: {json.dumps({'time': time.time(), 'status': 'connected'})}\n\n"
            self.wfile.write(init_msg.encode("utf-8"))
            self.wfile.flush()

            while self.engine.is_running and not self.close_connection:
                try:
                    event_type, event_data = client_q.get(timeout=2.0)
                    chunk = f"event: {event_type}\ndata: {event_data}\n\n"
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Send periodic keepalive comment
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.close_connection = True
            self.engine.unregister_sse_client(client_q)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")


class CustomThreadingHTTPServer(ThreadingHTTPServer):
    """Subclass holding reference to WebAppletEngine and allowing port reuse."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: Tuple[str, int], RequestHandlerClass: Any, engine: WebAppletEngine) -> None:
        self.engine = engine
        super().__init__(server_address, RequestHandlerClass)

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Suppresses normal client network disconnections without dumping tracebacks to stderr."""
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type in (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            return
        if isinstance(exc_val, OSError) and exc_val.errno in (
            errno.ECONNRESET,
            errno.EPIPE,
            errno.ECONNABORTED,
            errno.ENOTCONN,
            errno.ETIMEDOUT,
        ):
            return
        super().handle_error(request, client_address)


class Port80RedirectHandler(BaseHTTPRequestHandler):
    """Bounces any port 80 requests to the target WebApplet port (e.g. 8888)."""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass
        except OSError as exc:
            if exc.errno in (errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED, errno.ENOTCONN):
                pass
            else:
                raise

    def finish(self) -> None:
        try:
            if not self.wfile.closed:
                try:
                    self.wfile.flush()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            super().finish()
        except Exception:
            pass

    def do_GET(self) -> None:
        try:
            host_hdr = self.headers.get("Host", "127.0.0.1").split(":")[0]
            target_port = getattr(self.server, "target_port", 8888)
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"http://{host_hdr}:{target_port}{self.path}")
            self.end_headers()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, OSError):
            self.close_connection = True

    def do_POST(self) -> None:
        self.do_GET()


class Port80RedirectServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    target_port: int = 8888

    def handle_error(self, request: Any, client_address: Any) -> None:
        """Suppresses normal client network disconnections without dumping tracebacks to stderr."""
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type in (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            return
        if isinstance(exc_val, OSError) and exc_val.errno in (
            errno.ECONNRESET,
            errno.EPIPE,
            errno.ECONNABORTED,
            errno.ENOTCONN,
            errno.ETIMEDOUT,
        ):
            return
        super().handle_error(request, client_address)


class WebAppletEngine:
    """Multi-instance capable WebApplet HTTP/SSE runtime.

    Can be instantiated multiple times simultaneously with different ports.
    """

    def __init__(
        self,
        name: str = "webapplet",
        host: str = "0.0.0.0",
        port: int = 8888,
        sse_path: str = "/events",
        enable_port_80_redirect: bool = True,
    ) -> None:
        self.name = name
        self.host = host
        self.port = port
        self.sse_path = sse_path
        self.enable_port_80_redirect = enable_port_80_redirect

        self.get_routes: Dict[str, Callable[..., Any]] = {}
        self.post_routes: Dict[str, Callable[..., Any]] = {}
        self.prefix_get_routes: Dict[str, Callable[..., Any]] = {}
        self.prefix_post_routes: Dict[str, Callable[..., Any]] = {}

        self._sse_clients: List[queue.Queue[Tuple[str, str]]] = []
        self._sse_lock = threading.Lock()
        self._server: Optional[CustomThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port_80_server: Optional[Port80RedirectServer] = None
        self._port_80_thread: Optional[threading.Thread] = None
        self.is_running = False

        self._last_client_seen: float = 0.0
        self._active_ips: Dict[str, float] = {}
        self._client_state_callbacks: List[Callable[[bool, int], None]] = []

    def register_get(self, path: str, handler: Callable[..., Any], prefix: bool = False) -> None:
        if prefix:
            self.prefix_get_routes[path] = handler
        else:
            self.get_routes[path] = handler

    def register_post(self, path: str, handler: Callable[..., Any], prefix: bool = False) -> None:
        if prefix:
            self.prefix_post_routes[path] = handler
        else:
            self.post_routes[path] = handler

    def on_client_state_change(self, callback: Callable[[bool, int], None]) -> None:
        """Registers listener invoked when browser connection state changes."""
        self._client_state_callbacks.append(callback)

    def record_client_activity(self, ip: str) -> None:
        """Records timestamp of active client interaction."""
        now = time.time()
        was_active = self.is_client_active()
        self._last_client_seen = now
        self._active_ips[ip] = now
        if not was_active:
            self._notify_state_change()

    def register_sse_client(self, q: queue.Queue[Tuple[str, str]]) -> None:
        with self._sse_lock:
            self._sse_clients.append(q)
            self._last_client_seen = time.time()
        self._notify_state_change()

    def unregister_sse_client(self, q: queue.Queue[Tuple[str, str]]) -> None:
        with self._sse_lock:
            if q in self._sse_clients:
                self._sse_clients.remove(q)
        self._notify_state_change()

    def _notify_state_change(self) -> None:
        is_active = self.is_client_active()
        count = self.get_active_client_count()
        for cb in self._client_state_callbacks:
            try:
                cb(is_active, count)
            except Exception:
                pass

    def get_active_client_count(self) -> int:
        """Returns number of active SSE connections plus recent REST clients."""
        with self._sse_lock:
            sse_count = len(self._sse_clients)
        now = time.time()
        # Clean IPs older than 15s
        recent_ips = [ip for ip, ts in self._active_ips.items() if now - ts < 15.0]
        return max(sse_count, len(recent_ips))

    def is_client_active(self, window_seconds: float = 12.0) -> bool:
        """Returns True if a browser has visited or maintained an SSE connection recently."""
        with self._sse_lock:
            if len(self._sse_clients) > 0:
                return True
        return (time.time() - self._last_client_seen) < window_seconds

    def broadcast_event(self, event_type: str, data: Any) -> int:
        """Dispatches an SSE event to all connected browser tabs."""
        payload_str = json.dumps(data) if not isinstance(data, str) else data
        with self._sse_lock:
            count = len(self._sse_clients)
            for q in list(self._sse_clients):
                try:
                    q.put_nowait((event_type, payload_str))
                except queue.Full:
                    pass
        return count

    def start(self) -> bool:
        """Starts the multi-threaded HTTP server in a background daemon thread."""
        if self.is_running:
            return True
        try:
            self._server = CustomThreadingHTTPServer((self.host, self.port), WebAppletHandler, self)
            self.port = self._server.server_address[1]  # Update in case port 0 was passed
            self.is_running = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name=f"webapplet-{self.name}-{self.port}",
                daemon=True,
            )
            self._thread.start()

            # Attempt to launch port 80 redirect if privileged / available (e.g. root in iSH)
            if self.enable_port_80_redirect and self.port != 80 and self.port != 0:
                try:
                    s80 = Port80RedirectServer((self.host, 80), Port80RedirectHandler)
                    s80.target_port = self.port
                    self._port_80_server = s80
                    t80 = threading.Thread(
                        target=s80.serve_forever,
                        name=f"webapplet-port80-redirect-{self.port}",
                        daemon=True,
                    )
                    self._port_80_thread = t80
                    t80.start()
                except Exception:
                    self._port_80_server = None
                    self._port_80_thread = None

            return True
        except Exception as exc:
            self.is_running = False
            return False

    def stop(self) -> None:
        """Gracefully shuts down the server and cleans up threads."""
        self.is_running = False
        if self._port_80_server:
            try:
                self._port_80_server.shutdown()
                self._port_80_server.server_close()
            except Exception:
                pass
            self._port_80_server = None
            self._port_80_thread = None

        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=1.0)
