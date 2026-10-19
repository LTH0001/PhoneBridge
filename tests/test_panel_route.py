"""Source integration checks; executable routing behavior is tested in Java."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PanelRouteIntegrationTests(unittest.TestCase):
    def source(self, name):
        return (ROOT/'android/app/src'/name).read_text(encoding='utf-8')

    def test_service_marks_actual_control_channels(self):
        source = self.source('BridgeService.java')
        for marker in ('panelRoute.activate(s,"usb")', 'panelRoute.activate(socket,"wireless")',
                       'panelRoute.activate(output,"accessory")', 'panelRoute.deactivate(socket)',
                       'panelRoute.deactivate(output)', '"control_transport",panelTransport()'):
            self.assertIn(marker, source)

    def test_requests_and_artwork_share_actual_route(self):
        source = self.source('PanelConnection.java')
        self.assertIn('service.panelTransport()', source)
        self.assertEqual(source.count('String transport=route();'), 2)
        self.assertNotIn('if(AccessoryLink.active())return', source)
        self.assertIn('code==401', source)
        self.assertIn('PanelRoute.choose(', source)

    def test_dashboard_does_not_hide_null_exception_as_disconnection(self):
        source = self.source('DashboardActivity.java')
        self.assertIn('PanelRoute.errorMessage(error)', source)
        self.assertNotIn('connection.setText("等待电脑连接")', source)
