import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HardeningInteractionCoverageTests(unittest.TestCase):
    def test_ui_binds_snapshot_identity_command_center_and_reproducibility_export(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        for token in ('id="snapshotIdentity"', 'id="incidentCommandCenter"', 'id="exportReceipt"', 'id="counterfactualCards"'):
            self.assertIn(token, html)
        for token in ('/api/investigation/replay', '/api/incident-command', '/api/reproducibility-receipt', 'snapshot_id', 'local-only/read-only'):
            self.assertIn(token, javascript)

    def test_ui_uses_replay_endpoint_for_selected_loss_consistency(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        selected_loss = javascript[javascript.index('async function diagnoseSelectedLoss'):javascript.index('function renderIncidentTimeline')]
        self.assertIn("/api/investigation/replay", selected_loss)
        self.assertNotIn("'/api/analyse'", selected_loss)


if __name__ == "__main__": unittest.main()
