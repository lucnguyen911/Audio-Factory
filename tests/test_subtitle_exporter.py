import unittest
import tempfile
import json
from pathlib import Path

from core.subtitle_exporter import (
    SubtitleExportError,
    TranscriptSegment,
    normalize_segments,
    format_srt_timestamp,
    format_vtt_timestamp,
    export_srt,
    export_vtt,
    export_txt,
    export_json,
    export_all_subtitles
)

class TestSubtitleExporter(unittest.TestCase):

    def test_normalize_segments_dataclass(self):
        segs = [TranscriptSegment(start=1.5, end=3.2, text="Hello world", index=99)]
        norm = normalize_segments(segs)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0].start, 1.5)
        self.assertEqual(norm[0].end, 3.2)
        self.assertEqual(norm[0].text, "Hello world")
        self.assertEqual(norm[0].index, 1)

    def test_normalize_segments_dict(self):
        segs = [{"start": 0.0, "end": 2.5, "text": "  Chào các bạn  "}]
        norm = normalize_segments(segs)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0].start, 0.0)
        self.assertEqual(norm[0].end, 2.5)
        self.assertEqual(norm[0].text, "Chào các bạn")
        self.assertEqual(norm[0].index, 1)

    def test_normalize_segments_invalid_timestamps(self):
        with self.assertRaises(SubtitleExportError) as ctx:
            normalize_segments([{"start": -1.0, "end": 2.0, "text": "text"}])
        self.assertIn("cannot be negative", str(ctx.exception))
        
        with self.assertRaises(SubtitleExportError) as ctx:
            normalize_segments([{"start": 2.5, "end": 2.5, "text": "text"}])
        self.assertIn("must be strictly greater", str(ctx.exception))
        
        with self.assertRaises(SubtitleExportError) as ctx:
            normalize_segments([{"start": 3.0, "end": 2.0, "text": "text"}])
        self.assertIn("must be strictly greater", str(ctx.exception))

    def test_normalize_segments_empty_text(self):
        with self.assertRaises(SubtitleExportError) as ctx:
            normalize_segments([{"start": 0.0, "end": 1.0, "text": "   "}])
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_format_srt_timestamp(self):
        self.assertEqual(format_srt_timestamp(0.0), "00:00:00,000")
        self.assertEqual(format_srt_timestamp(1.005), "00:00:01,005")
        self.assertEqual(format_srt_timestamp(65.123), "00:01:05,123")
        self.assertEqual(format_srt_timestamp(3665.1234), "01:01:05,123")

    def test_format_vtt_timestamp(self):
        self.assertEqual(format_vtt_timestamp(0.0), "00:00:00.000")
        self.assertEqual(format_vtt_timestamp(1.005), "00:00:01.005")
        self.assertEqual(format_vtt_timestamp(65.123), "00:01:05.123")
        self.assertEqual(format_vtt_timestamp(3665.1234), "01:01:05.123")

    def test_export_srt(self):
        segs = [{"start": 1.0, "end": 2.5, "text": "Line 1"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "sub.srt"
            export_srt(segs, out_file)
            
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("1\n00:00:01,000 --> 00:00:02,500\nLine 1", content.replace("\r\n", "\n"))

    def test_export_vtt(self):
        segs = [{"start": 1.0, "end": 2.5, "text": "Line 1"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "sub.vtt"
            export_vtt(segs, out_file)
            
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("WEBVTT"))
            self.assertIn("00:00:01.000 --> 00:00:02.500", content)

    def test_export_txt(self):
        segs = [
            {"start": 1.0, "end": 2.0, "text": "First line"},
            {"start": 2.0, "end": 3.0, "text": "Second line"}
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file_no_ts = Path(tmpdir) / "text_no_ts.txt"
            export_txt(segs, out_file_no_ts, include_timestamps=False)
            content_no_ts = out_file_no_ts.read_text(encoding="utf-8")
            self.assertEqual(content_no_ts.replace("\r\n", "\n"), "First line\nSecond line")
            
            out_file_ts = Path(tmpdir) / "text_ts.txt"
            export_txt(segs, out_file_ts, include_timestamps=True)
            content_ts = out_file_ts.read_text(encoding="utf-8")
            self.assertIn("[00:00:01.000 --> 00:00:02.000] First line", content_ts)

    def test_export_json_vietnamese(self):
        segs = [{"start": 1.0, "end": 2.5, "text": "Xin chào tiếng Việt"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "sub.json"
            export_json(segs, out_file)
            
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Xin chào tiếng Việt", content)
            
            parsed = json.loads(content)
            self.assertEqual(parsed[0]["text"], "Xin chào tiếng Việt")

    def test_export_all_subtitles(self):
        segs = [{"start": 1.0, "end": 2.5, "text": "Hello"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "subtitles"
            res = export_all_subtitles(segs, out_dir, "my_video")
            
            self.assertIn("srt", res)
            self.assertIn("vtt", res)
            self.assertIn("txt", res)
            self.assertIn("json", res)
            
            for path in res.values():
                self.assertTrue(path.exists())
                self.assertEqual(path.parent, out_dir)
