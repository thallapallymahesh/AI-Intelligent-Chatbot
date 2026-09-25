import os
import tempfile
import unittest

from backend import database
from backend.chat_memory import RECENT_MESSAGE_LIMIT, SYSTEM_MESSAGE, build_chat_messages


class ChatMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.temporary_directory.name, "test.db")
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temporary_directory.cleanup()

    def test_recent_messages_are_isolated_by_chat_and_ordered(self):
        first_chat_id = database.create_chat("First chat")
        second_chat_id = database.create_chat("Second chat")

        for index in range(8):
            database.add_message(first_chat_id, "user", f"first-{index}")
            database.add_message(second_chat_id, "user", f"second-{index}")

        first_chat_messages = database.get_recent_messages(
            first_chat_id,
            RECENT_MESSAGE_LIMIT,
        )
        second_chat_messages = database.get_recent_messages(
            second_chat_id,
            RECENT_MESSAGE_LIMIT,
        )

        self.assertEqual(
            first_chat_messages,
            [
                ("user", "first-2"),
                ("user", "first-3"),
                ("user", "first-4"),
                ("user", "first-5"),
                ("user", "first-6"),
                ("user", "first-7"),
            ],
        )
        self.assertEqual(
            second_chat_messages,
            [
                ("user", "second-2"),
                ("user", "second-3"),
                ("user", "second-4"),
                ("user", "second-5"),
                ("user", "second-6"),
                ("user", "second-7"),
            ],
        )

    def test_context_uses_only_selected_chat_history(self):
        selected_history = [
            ("user", "Question from selected chat"),
            ("assistant", "Answer from selected chat"),
        ]

        messages = build_chat_messages(
            selected_history,
            "Current selected-chat question",
            "Document excerpt",
        )

        self.assertEqual(messages[0], SYSTEM_MESSAGE)
        self.assertEqual(messages[1]["content"], "Question from selected chat")
        self.assertEqual(messages[2]["content"], "Answer from selected chat")
        self.assertIn("Current selected-chat question", messages[3]["content"])
        self.assertNotIn("another chat", str(messages))

    def test_new_chat_context_has_no_saved_messages(self):
        messages = build_chat_messages([], "First question", "")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], SYSTEM_MESSAGE)
        self.assertIn("First question", messages[1]["content"])

    def test_zero_message_limit_returns_no_history(self):
        chat_id = database.create_chat("Empty limit")
        database.add_message(chat_id, "user", "Stored message")

        self.assertEqual(database.get_recent_messages(chat_id, 0), [])

    def test_saved_sources_are_returned_with_the_assistant_message(self):
        chat_id = database.create_chat("Sources")
        database.add_message(chat_id, "assistant", "Document answer", '[{"filename":"guide.pdf","chunk":0}]')

        messages = database.get_messages_with_sources(chat_id)

        self.assertEqual(messages[0]["content"], "Document answer")
        self.assertEqual(messages[0]["sources"][0]["filename"], "guide.pdf")


if __name__ == "__main__":
    unittest.main()
