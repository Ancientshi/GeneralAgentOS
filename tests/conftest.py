import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml


@pytest.fixture
def model_server():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for delta, finish in [
                    ({"role": "assistant", "content": "Profile works."}, None),
                    ({}, "stop"),
                ]:
                    chunk = {
                        "id": "chatcmpl-test",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                    }
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                reply = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Profile works."},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                }
                data = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", requests
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def profile_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "test-only")
    monkeypatch.delenv("GAOS_API_KEY", raising=False)

    def create(**changes):
        cfg = {
            "schema_version": 1,
            "os": {"port": 7777},
            "agents": {
                "assistant": {
                    "model": "test-model",
                    "provider": "vllm",
                    "base_url": "http://127.0.0.1:1/v1",
                    "instructions": "Be helpful",
                    "storage_db": "data/test.db",
                    "telemetry": False,
                }
            },
        }
        from general_agent_os.profile import deep_merge

        deep_merge(cfg, changes)
        path = tmp_path / "profile.yaml"
        path.write_text(yaml.safe_dump(cfg))
        return path

    return create
