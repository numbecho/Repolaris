import unittest
from repolaris.detection.events import detect_clinical_events, ECGEvent

class TestEventsDetection(unittest.TestCase):
    def test_detect_pause_and_qtc(self):
        # Create a mock series of 5 beats
        beats = [
            {
                "beat_index": 0,
                "time_sec": 1.0,
                "rr_sec": 0.8,
                "hr_bpm": 75.0,
                "qt_ms": 380.0,
                "qtc": {"bazett_ms": 425.0}
            },
            {
                "beat_index": 1,
                "time_sec": 1.8,
                "rr_sec": 2.6,  # Sinus pause > 2.5s
                "hr_bpm": 23.0,
                "qt_ms": 380.0,
                "qtc": {"bazett_ms": 400.0}
            },
            {
                "beat_index": 2,
                "time_sec": 4.4,
                "rr_sec": 0.8,
                "hr_bpm": 75.0,
                "qt_ms": 520.0,
                "qtc": {"bazett_ms": 535.0}  # Severe QTc prolongation > 500ms
            },
            {
                "beat_index": 3,
                "time_sec": 5.2,
                "rr_sec": 0.45,  # Tachycardia 133 BPM
                "hr_bpm": 133.3,
                "qt_ms": 300.0,
                "qtc": {"bazett_ms": 447.0}
            }
        ]

        events = detect_clinical_events(beats)
        event_types = [ev.event_type for ev in events]

        self.assertIn("PAUSE", event_types)
        self.assertIn("CRITICAL_QTC", event_types)
        self.assertIn("TACHYCARDIA", event_types)
        self.assertIn("MAX_HR", event_types)
        self.assertIn("MIN_HR", event_types)

        # Check critical pause severity
        pause_ev = [ev for ev in events if ev.event_type == "PAUSE"][0]
        self.assertEqual(pause_ev.severity, "CRITICAL")
        self.assertEqual(pause_ev.metric_value, 2.6)

        # Check critical QTc severity
        qtc_ev = [ev for ev in events if ev.event_type == "CRITICAL_QTC"][0]
        self.assertEqual(qtc_ev.severity, "CRITICAL")
        self.assertGreaterEqual(qtc_ev.metric_value, 500.0)

if __name__ == "__main__":
    unittest.main()
