"""Serve a folder over loopback so Studio's upload_image tool can fetch it.

upload_image takes http(s) URLs, not file paths. Run this in one terminal, pass
http://127.0.0.1:<port>/<file> to the tool for each image, then Ctrl-C. Loopback
only - nothing is exposed beyond this machine.
"""
import argparse
import functools
import http.server
import socketserver


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve generated assets to Roblox Studio's upload_image.")
    ap.add_argument("--dir", default=".", help="folder holding the images (default: current directory)")
    ap.add_argument("--port", type=int, default=8791)
    args = ap.parse_args()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=args.dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {args.dir} on http://127.0.0.1:{args.port} - Ctrl-C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
