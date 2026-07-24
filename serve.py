import http.server
import socketserver
import os

PORT = 80
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        # Check file extension to decide which headers to add
        path = self.path.split("?")[0].lower()
        if path.endswith(".html") or path.endswith("/") or path.endswith(".htm"):
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # suppress request logs

with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"elixir static server running at http://localhost:{PORT}")
    print("COEP/COOP/CORP headers enabled for SharedArrayBuffer support")
    httpd.serve_forever()
