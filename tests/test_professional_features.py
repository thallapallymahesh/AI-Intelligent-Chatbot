import os
import tempfile
import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import database
from backend import auth
from backend import main
from backend.main import enforce_user_limit


class ProfessionalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.temporary_directory.name, "features.db")
        database.init_db()
        main.app.dependency_overrides[auth.current_user] = lambda: auth.AuthenticatedUser(
            id="local-test-owner", email="tester@example.com"
        )
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        database.DB_PATH = self.original_db_path
        self.temporary_directory.cleanup()

    def test_archive_hides_chat_from_recent_list_and_restore_reveals_it(self):
        chat_id = database.create_chat("Project plan")
        self.assertEqual(len(database.get_chats(archived=False)), 1)
        database.set_chat_archived(chat_id, True)
        self.assertEqual(database.get_chats(archived=False), [])
        self.assertEqual(database.get_chats(archived=True)[0][0], chat_id)
        database.set_chat_archived(chat_id, False)
        self.assertEqual(database.get_chats(archived=False)[0][0], chat_id)

    def test_feedback_can_only_attach_to_assistant_messages(self):
        chat_id = database.create_chat("Feedback")
        database.add_message(chat_id, "user", "Question")
        database.add_message(chat_id, "assistant", "Answer")
        conn = database.get_connection()
        user_id, assistant_id = [row[0] for row in conn.execute(
            "SELECT id FROM messages WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()]
        conn.close()
        self.assertFalse(database.set_message_feedback(chat_id, user_id, 1))
        self.assertTrue(database.set_message_feedback(chat_id, assistant_id, 1))
        messages = database.get_messages_with_sources(chat_id)
        self.assertEqual(messages[1]["feedback"], 1)

    def test_regeneration_helper_removes_only_trailing_assistant_message(self):
        chat_id = database.create_chat("Regenerate")
        database.add_message(chat_id, "user", "Question")
        database.add_message(chat_id, "assistant", "Old answer")
        database.delete_last_assistant_message(chat_id)
        self.assertEqual(database.get_messages(chat_id), [("user", "Question")])

    def test_api_usage_limit_returns_retryable_429(self):
        owner = f"rate-limit-test-{id(self)}"
        enforce_user_limit(owner, "chat", limit=1, window_seconds=60)
        with self.assertRaises(HTTPException) as error:
            enforce_user_limit(owner, "chat", limit=1, window_seconds=60)
        self.assertEqual(error.exception.status_code, 429)

    def test_generation_stop_is_limited_to_own_generation(self):
        from threading import Event
        foreign_event = Event()
        main._generation_events["foreign"] = ("other-user", foreign_event)
        denied = self.client.post("/api/chat/stop", json={"generation_id": "foreign"})
        self.assertEqual(denied.status_code, 404)
        self.assertFalse(foreign_event.is_set())
        own_event = Event()
        main._generation_events["mine"] = ("local-test-owner", own_event)
        accepted = self.client.post("/api/chat/stop", json={"generation_id": "mine"})
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(own_event.is_set())
        main._generation_events.pop("foreign", None)
        main._generation_events.pop("mine", None)

    def test_chat_title_rename_archive_export_feedback_and_regeneration(self):
        chat_id = self.client.post("/api/new-chat").json()["chat_id"]
        with mock.patch.object(main, "search_documents", return_value=[]), mock.patch.object(
            main, "stream_chat", return_value=iter(["First answer"])
        ):
            response = self.client.post("/api/chat", json={"chat_id": chat_id, "message": "First question"})
            self.assertEqual(response.status_code, 200)
            self.assertIn('"sources": []', response.text)
            detail = self.client.get(f"/api/chats/{chat_id}").json()
            self.assertEqual(detail["messages"][1]["content"], "First answer")
            self.assertEqual(self.client.get("/api/chats").json()["chats"][0]["title"], "First question")
            message_id = detail["messages"][1]["id"]
            self.assertEqual(self.client.patch(f"/api/chats/{chat_id}", json={"title": "Research"}).status_code, 200)
            self.assertEqual(self.client.get("/api/chats").json()["chats"][0]["title"], "Research")
            self.assertEqual(self.client.patch(f"/api/chats/{chat_id}", json={"archived": True}).status_code, 200)
            self.assertEqual(self.client.get("/api/chats").json()["chats"], [])
            self.assertEqual(self.client.get("/api/chats?archived=true").json()["chats"][0]["id"], chat_id)
            self.assertEqual(self.client.patch(f"/api/chats/{chat_id}", json={"archived": False}).status_code, 200)
            self.assertEqual(self.client.patch(
                f"/api/chats/{chat_id}/messages/{message_id}/feedback", json={"feedback": 1}
            ).status_code, 200)
            export = self.client.get("/api/chats/export").json()
            self.assertEqual(export["chats"][0]["messages"][1]["content"], "First answer")
            self.assertEqual(export["chats"][0]["messages"][1]["feedback"], 1)
            self.client.post("/api/chat", json={"chat_id": chat_id, "message": "First question", "regenerate": True})
            self.assertEqual(len(self.client.get(f"/api/chats/{chat_id}").json()["messages"]), 2)
            for action, expected in (("summary", "Summarize"), ("key_points", "key points"), ("quiz", "quiz")):
                ai = mock.Mock(return_value=iter(["Action answer"]))
                with mock.patch.object(main, "search_documents", return_value=[]), mock.patch.object(main, "stream_chat", ai):
                    result = self.client.post("/api/chat", json={
                        "chat_id": chat_id, "message": f"Run {action}", "action": action,
                    })
                self.assertEqual(result.status_code, 200)
                self.assertIn(expected.lower(), ai.call_args.args[0][-1]["content"].lower())
            self.assertEqual(self.client.delete(f"/api/chats/{chat_id}").status_code, 200)
            self.assertEqual(self.client.get("/api/chats").json()["chats"], [])

    def test_document_list_remove_and_account_delete(self):
        chat_id = self.client.post("/api/new-chat").json()["chat_id"]
        with mock.patch.object(main, "index_document", return_value={"chunks": 1}), mock.patch.object(
            main, "remove_document_chunks"
        ) as remove_chunks:
            response = self.client.post("/api/upload", data={"chat_id": chat_id},
                                        files={"file": ("note.txt", b"A small document.", "text/plain")})
            self.assertEqual(response.status_code, 200, response.text)
            docs = self.client.get(f"/api/chats/{chat_id}/documents").json()["documents"]
            self.assertEqual(docs[0]["filename"], "note.txt")
            self.assertEqual(self.client.delete(
                f"/api/chats/{chat_id}/documents/{docs[0]['id']}"
            ).status_code, 200)
            remove_chunks.assert_called_once()
        self.client.post("/api/new-chat")
        self.assertEqual(self.client.delete("/api/account").status_code, 200)
        self.assertEqual(self.client.get("/api/chats").json()["chats"], [])


if __name__ == "__main__":
    unittest.main()
