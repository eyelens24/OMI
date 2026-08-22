import unittest
from pathlib import Path

class EvidenceLedgerUiContractTests(unittest.TestCase):
    def test_primary_ui_has_ledger_surface_and_receipt_drawer(self):
        html = (Path(__file__).resolve().parents[1] / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Decision Receipt', html)
        self.assertIn('ledgerPath', html)
        self.assertIn('ledgerReceipt', html)
        self.assertIn('loadCompleteLedgerDemo', html)
