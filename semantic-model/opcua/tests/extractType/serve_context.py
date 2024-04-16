import http.server
import socketserver
import argparse
import os
import signal
import sys
import socket
import threading

class SingleFileRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.file_to_serve = kwargs.pop('file_to_serve')
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/' or self.path == f'/{os.path.basename(self.file_to_serve)}':
            self.path = f'/{self.file_to_serve}'
        else:
            self.send_error(404, "File not found")
            return

        return super().do_GET()

class GracefulTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shutdown_event = threading.Event()

    def serve_forever(self):
        while not self._shutdown_event.is_set():
            self.handle_request()

    def shutdown(self):
        self._shutdown_event.set()
        super().shutdown()

def run_server(port, file_to_serve):
    handler = lambda *args, **kwargs: SingleFileRequestHandler(*args, file_to_serve=file_to_serve, **kwargs)
    
    with GracefulTCPServer(("", port), handler) as httpd:
        # Set the socket option to reuse the address
        httpd.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        def signal_handler(sig, frame):
            print("Received shutdown signal. Shutting down the server...")
            #httpd.shutdown()
            sys.exit(0)

        # Register signal handlers for SIGINT (Ctrl+C) and SIGTERM
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        print(f"Serving {file_to_serve} on port {port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.shutdown()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minimal web server to serve a single file.")
    parser.add_argument('file', help="The file to be served")
    parser.add_argument('-p', '--port', type=int, default=8000, help="Port number to serve the file on (default: 8000)")
    
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: {args.file} is not a valid file.")
        exit(1)

    run_server(args.port, args.file)
