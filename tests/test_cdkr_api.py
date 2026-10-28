import os
import socket
import time
import unittest
from unittest import mock

from cdkr import api

from cdkr_helpers import MockBackend

ACCOUNT_A = "acct-aaaa"
ACCOUNT_B = "acct-bbbb"


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.backend = MockBackend()
        self.api = api.Api(self.backend.url, timeout=5)
        self.token = self.api.bind(ACCOUNT_A, "a@example.com")["binding_token"]

    def tearDown(self):
        self.backend.stop()

    def redeem(self, cdk, account=ACCOUNT_A, token=None):
        return self.api.redeem(token or self.token, cdk, account)

    def assertHttpError(self, status, code, fn, *args):
        with self.assertRaises(api.HttpError) as ctx:
            fn(*args)
        self.assertEqual((ctx.exception.status, ctx.exception.code), (status, code))
        return ctx.exception

    def test_bind_returns_token_for_account(self):
        binding = self.api.bind(ACCOUNT_B, "b@example.com")
        self.assertTrue(binding["binding_token"].startswith("cdkb_"))
        self.assertEqual(binding["account"]["chatgpt_account_id"], ACCOUNT_B)

    def test_valid_cdk_succeeds_once_then_replays(self):
        first = self.redeem("TEST-OK01")
        self.assertEqual((first["status"], first["replayed"]), ("succeeded", False))
        self.assertTrue(first["product"])
        again = self.redeem("TEST-OK01")
        self.assertEqual((again["status"], again["replayed"]), ("succeeded", True))
        self.assertEqual(again["redemption_id"], first["redemption_id"])

    def test_cdk_used_by_another_account_conflicts(self):
        self.redeem("TEST-OK02")
        other = self.api.bind(ACCOUNT_B, "b@example.com")["binding_token"]
        self.assertHttpError(409, "cdk_already_redeemed", self.redeem, "TEST-OK02", ACCOUNT_B, other)

    def test_invalid_expired_and_failed_cdks(self):
        self.assertHttpError(400, "cdk_invalid", self.redeem, "NOPE-0000")
        self.assertHttpError(410, "cdk_expired", self.redeem, "TEST-EXPD")
        err = self.assertHttpError(422, "fulfillment_failed", self.redeem, "TEST-FAIL")
        self.assertTrue(err.message)

    def test_processing_then_succeeded_on_poll(self):
        first = self.redeem("TEST-PROC")
        self.assertEqual(first["status"], "processing")
        polls = [self.api.get_redemption(self.token, first["redemption_id"])["status"] for _ in range(2)]
        self.assertEqual(polls, ["processing", "succeeded"])

    def test_timeout_is_unknown_and_retry_is_idempotent(self):
        self.backend.state.slow_seconds = 1.0
        slow = api.Api(self.backend.url, timeout=0.3)
        with self.assertRaises(api.Unknown):
            slow.redeem(self.token, "TEST-SLOW", ACCOUNT_A)
        time.sleep(1.2)
        again = self.redeem("TEST-SLOW")
        self.assertEqual((again["status"], again["replayed"]), ("succeeded", True))
        self.assertEqual(self.backend.state.consumed("TEST-SLOW"), 1)

    def test_expired_binding_is_401(self):
        self.backend.post("/_mock/expire-bindings")
        self.assertHttpError(401, "binding_invalid", self.redeem, "TEST-OK03")

    def test_binding_for_other_account_is_403(self):
        self.assertHttpError(403, "account_mismatch", self.redeem, "TEST-OK03", ACCOUNT_B)

    def test_server_error_and_rate_limit(self):
        self.backend.post("/_mock/fail-next", {"status": 503})
        self.assertHttpError(503, "server_error", self.redeem, "TEST-OK03")
        self.backend.post("/_mock/fail-next", {"status": 429, "retry_after": 7})
        self.assertEqual(self.assertHttpError(429, "rate_limited", self.redeem, "TEST-OK03").retry_after, 7)

    def test_redirects_are_never_followed(self):
        # urllib would copy the Authorization header to any Location, plain http included.
        elsewhere = MockBackend()
        self.addCleanup(elsewhere.stop)
        for status in (301, 302, 303, 307, 308):
            self.backend.state.fail_next = {"status": status, "location": elsewhere.url + "/v1/redemptions"}
            with self.assertRaises(api.Unknown, msg=status):  # the POST may already have been processed
                self.redeem("TEST-OK03")
        rid = self.redeem("TEST-PROC")["redemption_id"]
        self.backend.state.fail_next = {"status": 302, "location": elsewhere.url + "/v1/redemptions/x"}
        with self.assertRaises(api.BadResponse):
            self.api.get_redemption(self.token, rid)
        self.assertEqual(elsewhere.state.paths, [])
        self.assertEqual(elsewhere.state.authorizations, [])

    def test_refused_connection_is_not_sent(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with self.assertRaises(api.NotSent):
            api.Api(f"http://127.0.0.1:{port}", timeout=2).redeem(self.token, "TEST-OK04", ACCOUNT_A)

    def test_cdk_and_token_stay_out_of_urls(self):
        self.redeem("TEST-OK05")
        self.assertTrue(self.backend.state.paths)
        for path in self.backend.state.paths:
            self.assertNotIn("TEST-OK05", path)
            self.assertNotIn(self.token, path)
        self.assertTrue(all(h.startswith("codex-cdk-recharge/") for h in self.backend.state.client_headers))

    def test_local_backend_bypasses_proxy(self):
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
                                          "NO_PROXY": ""}):
            self.assertIn("binding_token", api.Api(self.backend.url).bind(ACCOUNT_B, "b@example.com"))

    def test_plain_http_only_for_local_hosts(self):
        for url in ["http://127.0.0.1:18787", "http://localhost:1", "https://pay.example.com"]:
            api.Api(url)
        for url in ["http://pay.example.com", "ftp://x", "", "pay.example.com", "https://pay.example.com:abc"]:
            with self.assertRaises(api.InsecureUrl, msg=url):
                api.Api(url)

    def test_errors_never_carry_the_cdk(self):
        for cdk in ["NOPE-SECRET-1", "TEST-EXPD"]:
            try:
                self.redeem(cdk)
            except api.ApiError as exc:
                self.assertNotIn(cdk, repr(exc) + str(exc))


if __name__ == "__main__":
    unittest.main()
