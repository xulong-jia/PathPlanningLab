import importlib
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout


class PackageImportTest(unittest.TestCase):
    def test_package_import_has_no_side_effects(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            module = importlib.import_module("path_planning")

        self.assertEqual(module.__version__, "0.1.0")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
