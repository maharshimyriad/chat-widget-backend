import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cors import add_cors_middleware
from app.main import app
from app.routes import chat as chat_route, session as session_route


class FakeRemoteApp:
    def __init__(self, fail_first_query=False, fail_after_output=False):
        self.created_sessions = []
        self.queries = []
        self.fail_first_query = fail_first_query
        self.fail_after_output = fail_after_output

    async def async_create_session(self, user_id, state):
        session_id = f"session-{len(self.created_sessions) + 1}"
        self.created_sessions.append((user_id, state, session_id))
        return {"id": session_id}

    async def async_stream_query(self, message, user_id, session_id, run_config):
        self.queries.append((message, user_id, session_id))
        if self.fail_first_query:
            self.fail_first_query = False
            raise RuntimeError("session not found")
        yield {"content": {"parts": [{"text": "Answer"}]}, "partial": True}
        if self.fail_after_output:
            self.fail_after_output = False
            raise RuntimeError("session not found")

    async def async_get_session(self, user_id, session_id):
        return {
            "events": [
                {"author": "user", "content": {"role": "user", "parts": [{"text": "Question"}]}},
                {"author": "assistant", "content": {"parts": [{"text": "Answer"}, {"text": "hidden", "thought": True}]}},
            ]
        }


def parse_events(stream):
    events = []
    for block in stream.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields and "data" in fields:
            events.append((fields["event"], json.loads(fields["data"])))
    return events


class ChatSessionContractTests(unittest.TestCase):
    def setUp(self):
        self.remote_app = FakeRemoteApp()
        self.remote_patch = patch.object(chat_route, "get_remote_app", return_value=self.remote_app)
        self.history_remote_patch = patch.object(session_route, "get_remote_app", return_value=self.remote_app)
        self.remote_patch.start()
        self.history_remote_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.history_remote_patch.stop()
        self.remote_patch.stop()

    def send(self, session_id=None):
        return self.client.post(
            "/chat",
            json={
                "user_id": "client-a:stable-user",
                "environment_id": "dam",
                "message": "Question",
                "session_id": session_id,
            },
        )

    def test_cors_allows_unregistered_embedding_origin_without_credentials(self):
        cors_app = FastAPI()
        cors_app.post("/chat")(lambda: {"ok": True})
        add_cors_middleware(cors_app, "*")
        response = TestClient(cors_app).options(
            "/chat",
            headers={
                "Origin": "https://new-customer.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "*")
        self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_unset_cors_origins_rejects_browser_origin(self):
        cors_app = FastAPI()
        cors_app.post("/chat")(lambda: {"ok": True})
        with patch.dict(os.environ, {}, clear=True):
            add_cors_middleware(cors_app)
        response = TestClient(cors_app).post(
            "/chat",
            headers={"Origin": "http://localhost:5173"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "This site is not authorized to use the chat widget.",
        )
        self.assertEqual(response.headers.get("access-control-allow-origin"), "*")

    def test_cors_can_switch_to_an_exact_origin_allowlist(self):
        cors_app = FastAPI()
        cors_app.post("/chat")(lambda: {"ok": True})
        add_cors_middleware(cors_app, "https://approved.example, https://another.example")
        client = TestClient(cors_app)
        allowed = client.options(
            "/chat",
            headers={
                "Origin": "https://approved.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        denied_preflight = client.options(
            "/chat",
            headers={
                "Origin": "https://unlisted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        denied_request = client.post("/chat", headers={"Origin": "https://unlisted.example"})

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "*")
        self.assertEqual(denied_preflight.status_code, 200)
        self.assertEqual(denied_request.status_code, 403)
        self.assertEqual(denied_request.json()["detail"], "This site is not authorized to use the chat widget.")
        self.assertEqual(denied_request.headers.get("access-control-allow-origin"), "*")
        self.assertNotIn("access-control-allow-credentials", allowed.headers)
        client.close()

    def test_cors_origin_file_reloads_without_restarting_app(self):
        with TemporaryDirectory() as directory:
            origins_file = Path(directory) / "allowed-origins.txt"
            origins_file.write_text("https://first.example\n", encoding="utf-8")
            cors_app = FastAPI()
            cors_app.post("/chat")(lambda: {"ok": True})
            with patch.dict(
                os.environ,
                {"CORS_ALLOWED_ORIGINS_FILE": str(origins_file)},
                clear=True,
            ):
                add_cors_middleware(cors_app)
            client = TestClient(cors_app)

            first_allowed = client.post("/chat", headers={"Origin": "https://first.example"})
            origins_file.write_text("https://second.example\n", encoding="utf-8")
            second_allowed = client.post("/chat", headers={"Origin": "https://second.example"})
            first_denied = client.post("/chat", headers={"Origin": "https://first.example"})

            self.assertEqual(first_allowed.status_code, 200)
            self.assertEqual(second_allowed.status_code, 200)
            self.assertEqual(first_denied.status_code, 403)
            self.assertEqual(
                first_denied.json()["detail"],
                "This site is not authorized to use the chat widget.",
            )
            client.close()

    def test_reuses_widget_session_across_messages(self):
        first = self.send()
        first_events = parse_events(first.text)
        session_id = first_events[0][1]["session_id"]

        second = self.send(session_id)
        second_events = parse_events(second.text)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual([event for event, _ in first_events], ["session", "message", "done"])
        self.assertEqual(second_events[0], ("session", {"session_id": session_id}))
        self.assertEqual(len(self.remote_app.created_sessions), 1)
        self.assertEqual([query[2] for query in self.remote_app.queries], [session_id, session_id])
        self.assertEqual(self.remote_app.created_sessions[0][1], {"product_id": "dam"})

    def test_replaces_missing_session_before_output_and_retries_once(self):
        self.remote_app.fail_first_query = True

        response = self.send("expired-session")
        events = parse_events(response.text)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event for event, _ in events], ["session", "session", "message", "done"])
        self.assertEqual(events[0][1]["session_id"], "expired-session")
        self.assertEqual(events[1][1]["session_id"], "session-1")
        self.assertEqual([query[2] for query in self.remote_app.queries], ["expired-session", "session-1"])

    def test_history_reads_text_from_agent_engine_session(self):
        response = self.client.get(
            "/history",
            params={
                "user_id": "client-a:stable-user",
                "environment_id": "dam",
                "session_id": "session-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["messages"],
            [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"},
            ],
        )

    def test_does_not_retry_after_agent_output(self):
        self.remote_app.fail_after_output = True

        response = self.send()
        events = parse_events(response.text)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event for event, _ in events], ["session", "message", "error"])
        self.assertEqual(len(self.remote_app.created_sessions), 1)
        self.assertEqual(len(self.remote_app.queries), 1)


if __name__ == "__main__":
    unittest.main()