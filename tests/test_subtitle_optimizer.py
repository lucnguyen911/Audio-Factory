import unittest
from core.subtitle_optimizer import optimize_subtitles, SubtitleOptimizerError

class TestSubtitleOptimizer(unittest.TestCase):

    def setUp(self):
        self.raw_segments = [
            {"start": 0.0, "end": 2.0, "text": "tôi đi chợ."},
            {"start": 2.0, "end": 4.0, "text": "Tôi mua rau."}
        ]

    def test_default_options_resolve(self):
        # Default should resolve to horizontal, 1 line
        res = optimize_subtitles(self.raw_segments, video_format="horizontal", max_lines=1)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0]["text"], "tôi đi chợ.")
        self.assertEqual(res[1]["text"], "Tôi mua rau.")

    def test_invalid_layout_preset(self):
        with self.assertRaises(SubtitleOptimizerError):
            optimize_subtitles(self.raw_segments, video_format="invalid", max_lines=1)
        with self.assertRaises(SubtitleOptimizerError):
            optimize_subtitles(self.raw_segments, video_format="horizontal", max_lines=4)

    def test_horizontal_vs_vertical_1_line(self):
        # Long text to trigger splitting
        long_seg = [{"start": 0.0, "end": 10.0, "text": "tôi đi xe đạp đi chợ và mua thêm rất nhiều rau xanh tươi ngon"}]
        
        # Horizontal + 1 line allows up to 42 chars / 8 words per cue
        res_h = optimize_subtitles(long_seg, video_format="horizontal", max_lines=1)
        # Vertical + 1 line allows up to 32 chars / 6 words per cue
        res_v = optimize_subtitles(long_seg, video_format="vertical", max_lines=1)
        
        # Vertical should produce more cues since limits are tighter
        self.assertGreaterEqual(len(res_v), len(res_h))
        
        # Validate that no cue contains newlines (max_lines=1)
        for cue in res_h:
            self.assertNotIn("\n", cue["text"])
        for cue in res_v:
            self.assertNotIn("\n", cue["text"])

    def test_max_lines_honored(self):
        long_seg = [{"start": 0.0, "end": 10.0, "text": "đây là một câu cực kỳ dài để kiểm tra tính năng xuống dòng của hệ thống tối ưu hóa phụ đề của chúng ta"}]
        
        # 1 line
        res_1 = optimize_subtitles(long_seg, video_format="horizontal", max_lines=1)
        for cue in res_1:
            self.assertEqual(len(cue["text"].split("\n")), 1)
            
        # 2 lines
        res_2 = optimize_subtitles(long_seg, video_format="horizontal", max_lines=2)
        for cue in res_2:
            self.assertLessEqual(len(cue["text"].split("\n")), 2)
            
        # 3 lines
        res_3 = optimize_subtitles(long_seg, video_format="horizontal", max_lines=3)
        for cue in res_3:
            self.assertLessEqual(len(cue["text"].split("\n")), 3)

    def test_anti_orphan_cue_and_line(self):
        # Test that we avoid a 1-word cue at the end by merging if it fits
        seg = [{"start": 0.0, "end": 3.0, "text": "tôi đi chợ mua rau quả và cá"}]
        # Under horizontal 1 line, target is 36 chars, max 42 chars, max 8 words
        # "tôi đi chợ mua rau quả và cá" has 8 words, total 28 chars.
        # It fits in a single cue, so it should not split.
        res = optimize_subtitles(seg, video_format="horizontal", max_lines=1)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["text"], "tôi đi chợ mua rau quả và cá")

    def test_no_split_sentence_punctuation_broken(self):
        # "tôi đi chợ. Tôi mua rau." should remain split nicely at the period boundary, not in a broken manner
        res = optimize_subtitles(self.raw_segments, video_format="horizontal", max_lines=1)
        self.assertEqual(res[0]["text"], "tôi đi chợ.")
        self.assertEqual(res[1]["text"], "Tôi mua rau.")

    def test_phrase_level_splits(self):
        # Long sentence split at a conjunction (e.g., "và", "nhưng", etc.)
        seg = [{"start": 0.0, "end": 8.0, "text": "tôi đi xe đạp đi chợ và tôi mua thêm rau"}]
        # Let's check where it splits when target_chars_per_line or max_words_per_cue is exceeded.
        res = optimize_subtitles(seg, video_format="vertical", max_lines=1)
        # Verify split occurred at "và" or nearby phrase boundary
        texts = [c["text"] for c in res]
        has_va_split = any(t.startswith("và") for t in texts)
        self.assertTrue(has_va_split, f"Expected split at conjunction 'và', got: {texts}")

    def test_word_timestamps_accuracy(self):
        # Test word-based timing vs proportional timing
        seg = [{
            "start": 0.0,
            "end": 4.0,
            "text": "one two three four",
            "words": [
                {"word": "one", "start": 0.5, "end": 1.0},
                {"word": "two", "start": 1.2, "end": 1.8},
                {"word": "three", "start": 2.0, "end": 2.8},
                {"word": "four", "start": 3.0, "end": 3.5}
            ]
        }]
        res = optimize_subtitles(seg, video_format="vertical", max_lines=1)
        self.assertEqual(len(res), 2)
        # First cue "one two three"
        self.assertEqual(res[0]["start"], 0.5)
        self.assertEqual(res[0]["end"], 2.8)
        self.assertEqual(res[0]["text"], "one two three")
        # Second cue "four"
        self.assertEqual(res[1]["start"], 3.0)
        self.assertEqual(res[1]["end"], 3.5)
        self.assertEqual(res[1]["text"], "four")

    def test_anti_orphan_merging_updates_end_time(self):
        # Test that when orphan word is merged, the end time matches that last word's end time
        # Ensure total duration is <= 3.5 seconds to avoid splitting based on duration
        seg = [{
            "start": 0.0,
            "end": 4.0,
            "text": "one two three four five",
            "words": [
                {"word": "one", "start": 0.5, "end": 1.0},
                {"word": "two", "start": 1.2, "end": 1.8},
                {"word": "three", "start": 2.0, "end": 2.5},
                {"word": "four", "start": 2.6, "end": 3.0},
                {"word": "five", "start": 3.1, "end": 3.5}
            ]
        }]
        res = optimize_subtitles(seg, video_format="horizontal", max_lines=1)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["start"], 0.5)
        self.assertEqual(res[0]["end"], 3.5)

    def test_overlap_prevention_and_min_duration(self):
        # Test zero/short duration cues and overlapping cues by forcing a split using a sentence ending punctuation
        seg = [
            {"start": 0.0, "end": 0.1, "text": "short."},
            {"start": 0.2, "end": 0.4, "text": "overlap here"}
        ]
        res = optimize_subtitles(seg, video_format="horizontal", max_lines=1)
        self.assertEqual(len(res), 2)
        
        # Check minimum duration (0.3s)
        self.assertGreaterEqual(round(res[0]["end"] - res[0]["start"], 3), 0.3)
        self.assertGreaterEqual(round(res[1]["end"] - res[1]["start"], 3), 0.3)
        
        # Check no overlap: res[0]["end"] <= res[1]["start"]
        self.assertLessEqual(res[0]["end"], res[1]["start"])

    def test_zero_duration_repaired_and_clamped(self):
        # First cue has zero duration: start 0.5, end 0.5
        # Second cue starts at 0.7, ends at 1.5
        seg = [
            {"start": 0.5, "end": 0.5, "text": "zero duration."},
            {"start": 0.7, "end": 1.5, "text": "next cue"}
        ]
        res = optimize_subtitles(seg, video_format="horizontal", max_lines=1)
        self.assertEqual(len(res), 2)
        
        # Check first cue is repaired: end > start
        self.assertGreater(res[0]["end"], res[0]["start"])
        # Check it is clamped safely to not exceed next cue start (0.7)
        self.assertLessEqual(res[0]["end"], res[1]["start"])
        self.assertEqual(res[0]["end"], 0.7)

if __name__ == "__main__":
    unittest.main()
