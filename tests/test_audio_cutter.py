import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.audio_cutter import (
    AudioCutError,
    AudioCutOptions,
    validate_filename_mode,
    sanitize_filename_text,
    build_output_filename,
    normalize_cut_segments,
    cut_audio_segment,
    cut_audio_by_sentences
)
from core.sentence_splitter import SentenceSegment

class TestAudioCutter(unittest.TestCase):

    def test_validate_filename_mode(self):
        self.assertEqual(validate_filename_mode("index"), "index")
        self.assertEqual(validate_filename_mode("index_text"), "index_text")
        self.assertEqual(validate_filename_mode("INDEX_TIME"), "index_time")
        
        with self.assertRaises(AudioCutError):
            validate_filename_mode("invalid_mode")

    def test_sanitize_filename_text(self):
        text = '  Tôi thích: "Đà Lạt" & <Hồ Xuân Hương> / hoặc\\? * '
        sanitized = sanitize_filename_text(text, max_words=4)
        self.assertEqual(sanitized, "tôi-thích-đà-lạt")
        
        self.assertEqual(sanitize_filename_text(' : " < > / \\ | ? * '), "untitled")

    def test_build_output_filename(self):
        sent = SentenceSegment(index=5, start=1.234, end=5.678, text="Hello Việt Nam")
        
        opts_idx = AudioCutOptions(filename_mode="index", output_format="wav")
        self.assertEqual(build_output_filename(sent, opts_idx), "005.wav")
        
        opts_txt = AudioCutOptions(filename_mode="index_text", output_format="mp3", max_words_in_filename=2)
        self.assertEqual(build_output_filename(sent, opts_txt), "005_hello-việt.mp3")
        
        opts_time = AudioCutOptions(filename_mode="index_time", output_format="m4a")
        self.assertEqual(build_output_filename(sent, opts_time), "005_1.23-5.68.m4a")

    def test_normalize_cut_segments_dataclass(self):
        segs = [SentenceSegment(index=1, start=0.5, end=3.0, text="text")]
        norm = normalize_cut_segments(segs)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0].index, 1)
        self.assertEqual(norm[0].start, 0.5)

    def test_normalize_cut_segments_dict(self):
        segs = [{"index": 2, "start": 1.0, "end": 2.5, "text": "text"}]
        norm = normalize_cut_segments(segs)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0].index, 2)
        self.assertEqual(norm[0].start, 1.0)

    def test_normalize_cut_segments_invalid(self):
        with self.assertRaises(AudioCutError):
            normalize_cut_segments([{"index": 1, "start": 3.0, "end": 2.0, "text": "text"}])
            
        with self.assertRaises(AudioCutError):
            normalize_cut_segments([{"index": 0, "start": 1.0, "end": 2.0, "text": "text"}])

    @patch("pathlib.Path.exists")
    def test_cut_audio_segment_no_overwrite(self, mock_exists):
        mock_exists.return_value = True
        
        with self.assertRaises(AudioCutError) as ctx:
            cut_audio_segment(
                input_path=Path("input.wav"),
                output_path=Path("output.wav"),
                start=1.0,
                end=2.0,
                overwrite=False
            )
        self.assertIn("already exists and overwrite is set to False", str(ctx.exception))

    @patch("pathlib.Path.exists")
    @patch("core.audio_cutter.run_ffmpeg")
    def test_cut_audio_segment_success(self, mock_run_ffmpeg, mock_exists):
        mock_exists.return_value = False
        
        out_path = Path("out/001.wav")
        res = cut_audio_segment(
            input_path=Path("input.wav"),
            output_path=out_path,
            start=1.0,
            end=2.5,
            overwrite=True
        )
        
        self.assertEqual(res, out_path)
        mock_run_ffmpeg.assert_called_once()
        
        call_args = mock_run_ffmpeg.call_args[0][0]
        self.assertEqual(call_args[0], "-y")
        self.assertEqual(call_args[1], "-i")
        self.assertEqual(call_args[2], "input.wav")
        self.assertEqual(call_args[3], "-ss")
        self.assertEqual(call_args[4], "1.000000")
        self.assertEqual(call_args[5], "-to")
        self.assertEqual(call_args[6], "2.500000")
        self.assertIn("-c:a", call_args)
        self.assertEqual(call_args[call_args.index("-c:a") + 1], "pcm_s16le")

    @patch("core.audio_cutter.validate_input_file")
    @patch("pathlib.Path.mkdir")
    @patch("core.audio_cutter.cut_audio_segment")
    def test_cut_audio_by_sentences(self, mock_cut_seg, mock_mkdir, mock_validate):
        mock_validate.return_value = Path("input.wav")
        mock_cut_seg.side_effect = lambda inp, out, start, end, overwrite: out
        
        sentences = [
            {"index": 1, "start": 1.0, "end": 3.0, "text": "Sentence one"},
            {"index": 2, "start": 3.5, "end": 6.0, "text": "Sentence two"}
        ]
        
        opts = AudioCutOptions(
            padding_before=0.1,
            padding_after=0.2,
            filename_mode="index_text",
            output_format="mp3"
        )
        
        out_dir = Path("chunks")
        metadata = cut_audio_by_sentences(Path("input.wav"), sentences, out_dir, opts)
        
        self.assertEqual(len(metadata), 2)
        self.assertEqual(metadata[0]["index"], 1)
        self.assertEqual(metadata[0]["file"], "001_sentence-one.mp3")
        self.assertEqual(metadata[1]["index"], 2)
        self.assertEqual(metadata[1]["file"], "002_sentence-two.mp3")
        
        mock_cut_seg.assert_any_call(
            Path("input.wav"),
            out_dir / "001_sentence-one.mp3",
            start=0.9,
            end=3.2,
            overwrite=True
        )
