import asyncio
import unittest
from unittest import mock

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend import auth, supabase_store


class AuthenticationTests(unittest.TestCase):
    def test_missing_bearer_token_is_denied(self):
        with mock.patch.object(supabase_store, "configured", return_value=True):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(auth.current_user(None))
        self.assertEqual(error.exception.status_code, 401)

    def test_supabase_token_is_verified_and_user_id_comes_from_provider(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="opaque-token")
        with mock.patch.object(supabase_store, "configured", return_value=True), mock.patch.object(
            supabase_store, "verify_access_token", return_value={
                "id": "verified-user-id", "email": "person@example.com",
                "user_metadata": {"name": "Person"},
            },
        ) as verify:
            user = asyncio.run(auth.current_user(credentials))
        verify.assert_called_once_with("opaque-token")
        self.assertEqual(user.id, "verified-user-id")
        self.assertEqual(user.email, "person@example.com")

    def test_missing_supabase_configuration_fails_closed(self):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="anything")
        with mock.patch.object(supabase_store, "configured", return_value=False), mock.patch.dict(
            "os.environ", {"LOCAL_DEV_AUTH": "false"}, clear=False
        ):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(auth.current_user(credentials))
        self.assertEqual(error.exception.status_code, 503)

    def test_chat_lookup_always_filters_by_verified_owner(self):
        with mock.patch.object(supabase_store, "_request", return_value=[{"id": "chat-id"}]) as request:
            row = supabase_store.get_chat("verified-user-id", "chat-id")
        self.assertEqual(row["id"], "chat-id")
        self.assertEqual(request.call_args.kwargs["params"]["owner_id"], "eq.verified-user-id")
        self.assertEqual(request.call_args.kwargs["params"]["id"], "eq.chat-id")


if __name__ == "__main__":
    unittest.main()
