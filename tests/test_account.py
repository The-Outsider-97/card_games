"""Adapter tests of SLAI AuthService's public session contract.

The fake is used to test persistence and token/refresh integration independently
of optional SLAI auth dependencies; full runtime auth is tested separately.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

try:
    from applications.tools.database import Database
    from app.service import CardGamesService
except ImportError:
    Database = None


class AuthContract:
    def __init__(self):
        self.accounts = {}
        self.active = set()
        self.valid_refresh = set()
        self.counter = 0

    def sign_up(self, name, password):
        if name in self.accounts:
            raise ValueError("Account exists")
        self.accounts[name] = password
        return name

    def _session(self, name):
        self.counter += 1
        access = f"access-{self.counter}"
        refresh = f"refresh-{self.counter}"
        self.active.add(access)
        self.valid_refresh.add(refresh)
        return SimpleNamespace(access=SimpleNamespace(token=access, user_id=name),
                               refresh=SimpleNamespace(token=refresh, user_id=name))

    def log_in_with_refresh(self, name, password):
        if self.accounts.get(name) != password:
            raise ValueError("Invalid credentials")
        return self._session(name)

    def rotate_refresh_token(self, refresh):
        if refresh not in self.valid_refresh:
            raise ValueError("Invalid refresh")
        self.valid_refresh.remove(refresh)
        return self._session("alice")

    def is_token_valid(self, token):
        return token in self.active

    def log_out(self, token):
        self.active.discard(token)

    def revoke_token(self, token):
        self.valid_refresh.discard(token)


@unittest.skipIf(Database is None, "Requires SLAI applications/tools Database")
class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = CardGamesService(Path(self.temp.name))
        self.service.auth = AuthContract()
        self.service.auth_status = "ready"

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def test_signup_login_profile_refresh_rotation_logout(self):
        self.service.signup("alice", "DoNotUseInProduction123!")
        access, refresh, _ = self.service.login("alice", "DoNotUseInProduction123!")
        self.assertEqual(self.service.account(access)["owner"], "alice")
        self.assertEqual(self.service.profile("alice", {"display_name": "Alice", "avatar": "suit"})["avatar"], "suit")
        self.assertEqual(self.service.profile("alice")["display_name"], "Alice")
        new_access, new_refresh, _ = self.service.refresh(refresh)
        self.assertNotEqual(access, new_access)
        self.assertNotEqual(refresh, new_refresh)
        self.assertEqual(self.service.account(access)["status"], "guest")
        self.assertEqual(self.service.account(new_access)["status"], "signed-in")
        with self.assertRaises(ValueError):
            self.service.refresh(refresh)
        self.service.logout(new_access, new_refresh)
        self.assertEqual(self.service.account(new_access)["status"], "guest")

    def test_reject_invalid_account_profile(self):
        for patch in ({"avatar": "../../../../secrets"}, {"display_name": ""}, {"display_name": "\r"}):
            with self.assertRaises(ValueError):
                self.service.profile("alice", patch)
        self.assertEqual(self.service.profile("guest"), {"display_name": "Guest", "avatar": "initials"})


if __name__ == "__main__":
    unittest.main()
