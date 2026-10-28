import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cdkr import vault


@unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
class VaultTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cdkr-vault-"))
        self.path = self.tmp / "sub" / "binding.bin"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_round_trip_without_plaintext_on_disk(self):
        data = {"binding_token": "cdkb_SECRET123", "email": "a@example.com"}
        vault.save(self.path, data)
        self.assertEqual(vault.load(self.path), data)
        raw = self.path.read_bytes()
        for needle in (b"cdkb_SECRET123", b"a@example.com", "cdkb_SECRET123".encode("utf-16-le")):
            self.assertNotIn(needle, raw)

    def test_missing_or_tampered_file_loads_as_none(self):
        self.assertIsNone(vault.load(self.path))
        vault.save(self.path, {"binding_token": "x"})
        raw = bytearray(self.path.read_bytes())
        raw[-5] ^= 0xFF
        self.path.write_bytes(bytes(raw))
        self.assertIsNone(vault.load(self.path))
        self.path.write_bytes(b"garbage")
        self.assertIsNone(vault.load(self.path))

    def test_clear_removes_file(self):
        vault.save(self.path, {"binding_token": "x"})
        vault.clear(self.path)
        self.assertFalse(self.path.exists())
        vault.clear(self.path)  # idempotent

    def test_clear_never_raises_when_the_file_cannot_be_removed(self):
        self.path.mkdir(parents=True)  # unlink() on a directory fails like a locked file
        vault.clear(self.path)


if __name__ == "__main__":
    unittest.main()
