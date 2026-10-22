"""Flask/WSGI entrypoint with bounded backpressure for the shared HTTP adapter."""

import queue
import threading
from io import BytesIO

from flask import Flask, Response, request, send_from_directory
from werkzeug.datastructures import Headers

from .hosted import ROOT, HostedHandler


class Writer:
    def __init__(self):
        self.chunks = queue.Queue(maxsize=8)
        self.closed = threading.Event()

    def write(self, raw):
        while not self.closed.is_set():
            try:
                self.chunks.put(raw, timeout=0.2)
                return len(raw)
            except queue.Full:
                continue
        raise BrokenPipeError

    def flush(self):
        pass


def create_app(handler_type=HostedHandler, public_root=None):
    app = Flask(__name__, static_folder=None)
    public_root = public_root or ROOT / "public"

    @app.route("/api/<path:path>", methods=["GET", "POST"])
    def api(path):
        adapter = object.__new__(handler_type)
        adapter.path = request.full_path.rstrip("?")
        adapter.headers = Headers(request.headers)
        adapter.rfile = BytesIO(request.get_data(cache=False))
        writer = Writer()
        adapter.wfile = writer
        headers_ready = threading.Event()
        finished = threading.Event()
        metadata = {"status": 200, "headers": []}
        adapter.send_response = lambda status, message=None: metadata.update(status=status)
        adapter.send_header = lambda name, value: metadata["headers"].append((name, value))
        adapter.end_headers = headers_ready.set

        def execute():
            try:
                (adapter.do_POST if request_method == "POST" else adapter.do_GET)()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                finished.set()
                headers_ready.set()

        request_method = request.method
        worker = threading.Thread(target=execute, daemon=True)
        worker.start()
        if not headers_ready.wait(timeout=120):
            writer.closed.set()
            return {"error": "Request preparation timed out; no automatic retry was made."}, 504

        def stream():
            try:
                while not finished.is_set() or not writer.chunks.empty():
                    try:
                        yield writer.chunks.get(timeout=0.2)
                    except queue.Empty:
                        continue
            finally:
                writer.closed.set()
                worker.join(timeout=100)

        return Response(
            stream(),
            status=metadata["status"],
            headers=metadata["headers"],
            direct_passthrough=True,
        )

    @app.get("/")
    def index():
        return send_from_directory(public_root, "index.html")

    @app.get("/<path:path>")
    def static_file(path):
        return send_from_directory(public_root, path)

    return app
