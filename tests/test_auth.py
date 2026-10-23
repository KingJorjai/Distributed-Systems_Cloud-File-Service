import unittest

from auth import (
    RESERVED_USERNAMES,
    hash_password,
    validate_password,
    validate_username,
    verify_password,
)


class AuthTests(unittest.TestCase):
    def test_hash_round_trip(self):
        digest, salt, iterations = hash_password("correct horse")

        self.assertTrue(verify_password("correct horse", digest, salt, iterations))

    def test_wrong_password_is_rejected(self):
        digest, salt, iterations = hash_password("correct horse")

        self.assertFalse(verify_password("wrong", digest, salt, iterations))

    def test_username_validation(self):
        self.assertTrue(validate_username("alice"))
        self.assertTrue(validate_username("a_b-c1"))
        self.assertFalse(validate_username("ab"))
        self.assertFalse(validate_username("has space"))
        self.assertFalse(validate_username("bad/slash"))

    def test_password_minimum_length(self):
        self.assertFalse(validate_password("short"))
        self.assertTrue(validate_password("long-enough"))

    def test_reserved_usernames_are_rejected(self):
        for username in RESERVED_USERNAMES:
            with self.subTest(username=username):
                self.assertFalse(validate_username(username))


if __name__ == "__main__":
    unittest.main()
