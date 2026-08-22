import unittest
from pathlib import Path


class NativeLauncherTests(unittest.TestCase):
    def test_launcher_uses_verified_python_runs_tests_and_binds_loopback(self):
        launcher = (Path(__file__).resolve().parents[1] / "Start-DoctorQuant.ps1").read_text(encoding="utf-8")

        self.assertIn("C:\\conda2\\python.exe", launcher)
        self.assertIn("unittest discover -s tests", launcher)
        self.assertIn("HOST=127.0.0.1", launcher)
        self.assertIn("PORT=8000", launcher)
        self.assertIn("Doctor Quant_PID=", launcher)


if __name__ == "__main__":
    unittest.main()
