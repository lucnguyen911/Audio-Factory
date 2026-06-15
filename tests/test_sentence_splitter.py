import unittest
from core.sentence_splitter import (
    SentenceSplitError,
    SentenceSegment,
    SentenceSplitOptions,
    is_sentence_ending,
    normalize_text,
    split_text_into_sentences,
    split_segments_by_sentence,
    sentences_to_dicts
)

class TestSentenceSplitter(unittest.TestCase):

    def test_is_sentence_ending(self):
        self.assertTrue(is_sentence_ending("Hello."))
        self.assertTrue(is_sentence_ending("How are you?"))
        self.assertTrue(is_sentence_ending("Stop!"))
        self.assertTrue(is_sentence_ending("Waiting..."))
        self.assertTrue(is_sentence_ending("Chờ chút…"))
        
        self.assertFalse(is_sentence_ending("Hello"))
        self.assertFalse(is_sentence_ending("Comma, list"))
        self.assertFalse(is_sentence_ending("   "))

    def test_normalize_text(self):
        self.assertEqual(normalize_text("  hello   world  "), "hello world")
        self.assertEqual(normalize_text("  Xin   chào   Việt   Nam  "), "Xin chào Việt Nam")

    def test_split_text_into_sentences(self):
        text = "Chào bạn! Hôm nay thế nào? Tôi vẫn ổn..."
        res = split_text_into_sentences(text)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0], "Chào bạn!")
        self.assertEqual(res[1], "Hôm nay thế nào?")
        self.assertEqual(res[2], "Tôi vẫn ổn...")

    def test_split_segments_by_sentence_punctuation(self):
        segs = [
            {"start": 0.0, "end": 1.5, "text": "Hôm nay tôi đi học."},
            {"start": 2.0, "end": 3.5, "text": "Trời rất đẹp."}
        ]
        res = split_segments_by_sentence(segs)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].index, 1)
        self.assertEqual(res[0].text, "Hôm nay tôi đi học.")
        self.assertEqual(res[1].index, 2)
        self.assertEqual(res[1].text, "Trời rất đẹp.")

    def test_split_segments_by_sentence_pause(self):
        segs = [
            {"start": 0.0, "end": 1.0, "text": "Tôi nói câu này"},
            {"start": 2.0, "end": 3.0, "text": "sau đó dừng lại"}
        ]
        res = split_segments_by_sentence(segs)
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].text, "Tôi nói câu này")
        self.assertEqual(res[1].text, "sau đó dừng lại")

    def test_split_segments_by_sentence_merge_short(self):
        segs = [
            {"start": 0.0, "end": 0.5, "text": "Chào."},
            {"start": 0.6, "end": 1.1, "text": "Bạn."}
        ]
        res = split_segments_by_sentence(segs, SentenceSplitOptions(min_sentence_duration=1.2))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].text, "Chào. Bạn.")
        self.assertEqual(res[0].start, 0.0)
        self.assertEqual(res[0].end, 1.1)

    def test_split_segments_by_sentence_force_split_long(self):
        segs = [
            {"start": 0.0, "end": 15.0, "text": "Tôi thích đi du lịch ở Đà Lạt, và ăn nhiều món ngon."}
        ]
        res = split_segments_by_sentence(segs, SentenceSplitOptions(max_sentence_duration=10.0, force_split_long_segments=True))
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].text, "Tôi thích đi du lịch ở Đà Lạt,")
        self.assertEqual(res[1].text, "và ăn nhiều món ngon.")
        self.assertLess(res[0].end, 10.0)
        self.assertGreater(res[0].end, 5.0)

    def test_sentences_to_dicts(self):
        sents = [
            SentenceSegment(index=1, start=0.0, end=2.0, text="Hello", source_segment_indexes=[1])
        ]
        dicts = sentences_to_dicts(sents)
        self.assertEqual(len(dicts), 1)
        self.assertEqual(dicts[0]["index"], 1)
        self.assertEqual(dicts[0]["start"], 0.0)
        self.assertEqual(dicts[0]["end"], 2.0)
        self.assertEqual(dicts[0]["text"], "Hello")
        self.assertEqual(dicts[0]["source_segment_indexes"], [1])
