import unittest
import numpy as np

from repolaris.detection.classifier import (
    BeatClass,
    RhythmPattern,
    BeatFeatures,
    ClassifiedBeat,
    classify_heartbeat,
    detect_rhythm_patterns,
    classify_all_beats,
    compute_median_template,
)
from repolaris.detection.annotations import ECGAnnotation, AnnotationManager
from repolaris.utils.signal import generate_synthetic_ecg


class TestClassifierAndAnnotations(unittest.TestCase):
    def test_classify_normal_beat(self):
        feat = BeatFeatures(
            pre_rr_sec=0.85,
            post_rr_sec=0.85,
            pre_rr_ratio=1.0,
            post_rr_ratio=1.0,
            compensatory_ratio=1.0,
            qrs_duration_ms=85.0,
            qrs_peak_to_peak_mv=1.2,
            qrs_energy=10.0,
            template_correlation=0.98,
            polarity=1,
        )
        b_class, conf, rationale = classify_heartbeat(feat)
        self.assertEqual(b_class, BeatClass.NORMAL)
        self.assertGreater(conf, 0.8)

    def test_classify_pvc_beat(self):
        # Premature, wide QRS, low template correlation, compensatory pause
        feat = BeatFeatures(
            pre_rr_sec=0.55,
            post_rr_sec=1.15,
            pre_rr_ratio=0.65,
            post_rr_ratio=1.35,
            compensatory_ratio=1.0,
            qrs_duration_ms=135.0,
            qrs_peak_to_peak_mv=1.8,
            qrs_energy=25.0,
            template_correlation=0.35,
            polarity=-1,
        )
        b_class, conf, rationale = classify_heartbeat(feat)
        self.assertEqual(b_class, BeatClass.PVC)
        self.assertGreaterEqual(conf, 0.85)

    def test_classify_pac_beat(self):
        # Premature, narrow normal QRS, high correlation, incomplete pause
        feat = BeatFeatures(
            pre_rr_sec=0.60,
            post_rr_sec=0.90,
            pre_rr_ratio=0.72,
            post_rr_ratio=1.05,
            compensatory_ratio=0.88,
            qrs_duration_ms=80.0,
            qrs_peak_to_peak_mv=1.1,
            qrs_energy=9.0,
            template_correlation=0.92,
            polarity=1,
        )
        b_class, conf, rationale = classify_heartbeat(feat)
        self.assertEqual(b_class, BeatClass.PAC)
        self.assertGreaterEqual(conf, 0.80)

    def test_rhythm_patterns_couplet_and_bigeminy(self):
        # Synthetic sequence: N, V, V, N, V, N, V
        dummy_feat = BeatFeatures(0.8, 0.8, 1.0, 1.0, 1.0, 85.0, 1.0, 1.0, 0.95, 1)
        beats = [
            ClassifiedBeat(0, 500, 1.0, BeatClass.NORMAL, RhythmPattern.NORMAL_SINUS, 0.9, dummy_feat, ""),
            ClassifiedBeat(1, 1000, 2.0, BeatClass.PVC, RhythmPattern.ISOLATED_ECTOPIC, 0.9, dummy_feat, ""),
            ClassifiedBeat(2, 1300, 2.6, BeatClass.PVC, RhythmPattern.ISOLATED_ECTOPIC, 0.9, dummy_feat, ""),
            ClassifiedBeat(3, 1900, 3.8, BeatClass.NORMAL, RhythmPattern.NORMAL_SINUS, 0.9, dummy_feat, ""),
            ClassifiedBeat(4, 2300, 4.6, BeatClass.PVC, RhythmPattern.ISOLATED_ECTOPIC, 0.9, dummy_feat, ""),
            ClassifiedBeat(5, 2900, 5.8, BeatClass.NORMAL, RhythmPattern.NORMAL_SINUS, 0.9, dummy_feat, ""),
            ClassifiedBeat(6, 3300, 6.6, BeatClass.PVC, RhythmPattern.ISOLATED_ECTOPIC, 0.9, dummy_feat, ""),
        ]
        result = detect_rhythm_patterns(beats)
        self.assertEqual(result[1].rhythm_pattern, RhythmPattern.COUPLET)
        self.assertEqual(result[2].rhythm_pattern, RhythmPattern.COUPLET)
        self.assertEqual(result[4].rhythm_pattern, RhythmPattern.BIGEMINY)
        self.assertEqual(result[6].rhythm_pattern, RhythmPattern.BIGEMINY)

    def test_annotation_manager(self):
        mgr = AnnotationManager()
        mgr.add_annotation(sample=100, timestamp_sec=0.2, label="N")
        mgr.add_annotation(sample=500, timestamp_sec=1.0, label="V", sublabel="PVC")

        self.assertEqual(len(mgr), 2)
        v_list = mgr.get_by_label("V")
        self.assertEqual(len(v_list), 1)
        self.assertEqual(v_list[0].sample, 500)

        # Physician manual override
        override = mgr.override_beat_label(sample=105, new_label="S", reviewer="Dr. Smith", notes="Reclassified to PAC")
        self.assertIsNotNone(override)
        self.assertTrue(override.is_manual_override)
        self.assertEqual(override.label, "S")
        self.assertEqual(override.author, "Dr. Smith")

        # Check summary
        summ = mgr.summary()
        self.assertEqual(summ["total_annotations"], 2)
        self.assertEqual(summ["manual_overrides"], 1)

        # Serialization round-trip
        dict_list = mgr.to_dict_list()
        restored_mgr = AnnotationManager.from_dict_list(dict_list)
        self.assertEqual(len(restored_mgr), 2)
        self.assertEqual(restored_mgr.annotations[0].label, "S")

        # PhysioNet table export
        table = mgr.to_physionet_table()
        self.assertIn("Dr. Smith", table)
        self.assertIn("[OVERRIDE]", table)


if __name__ == "__main__":
    unittest.main()
