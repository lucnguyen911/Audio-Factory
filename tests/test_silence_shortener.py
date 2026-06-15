import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.silence_shortener import (
    SilenceShortenerError,
    SilenceShortenerOptions,
    validate_preset,
    options_from_preset,
    build_silenceremove_filter,
    shorten_silence,
    shorten_silence_batch
)

class TestSilenceShortener(unittest.TestCase):

    def test_validate_preset(self):
        self.assertEqual(validate_preset("natural"), "natural")
        self.assertEqual(validate_preset("FAST"), "fast")
        self.assertEqual(validate_preset("hard"), "hard")
        
        with self.assertRaises(SilenceShortenerError):
            validate_preset("invalid_preset")

    def test_options_from_preset(self):
        opts_nat = options_from_preset("natural")
        opts_fast = options_from_preset("fast")
        opts_hard = options_from_preset("hard")
        
        self.assertNotEqual(opts_nat.keep_silence_duration, opts_fast.keep_silence_duration)
        self.assertNotEqual(opts_fast.min_silence_duration, opts_hard.min_silence_duration)
        self.assertEqual(opts_nat.preset, "natural")
        self.assertEqual(opts_fast.preset, "fast")
        self.assertEqual(opts_hard.preset, "hard")

    def test_build_silenceremove_filter(self):
        opts = SilenceShortenerOptions(
            silence_threshold_db=-30.0,
            min_silence_duration=0.5,
            keep_silence_duration=0.2,
            trim_start=True,
            trim_end=True,
            process_middle=True
        )
        
        filter_str = build_silenceremove_filter(opts)
        self.assertGreater(len(filter_str), 0)
        self.assertTrue(filter_str.startswith("silenceremove="))
        self.assertIn("start_periods=1", filter_str)
        self.assertIn("stop_periods=-1", filter_str)
        self.assertIn("stop_silence=0.2", filter_str)
        self.assertIn("-30.0dB", filter_str)

    @patch("core.silence_shortener.validate_input_file")
    @patch("pathlib.Path.exists")
    def test_shorten_silence_no_overwrite(self, mock_exists, mock_validate):
        mock_validate.return_value = Path("input.mp3")
        mock_exists.return_value = True
        
        with self.assertRaises(SilenceShortenerError) as ctx:
            shorten_silence(
                input_path=Path("input.mp3"),
                output_path=Path("output.mp3"),
                options=SilenceShortenerOptions(overwrite=False)
            )
        self.assertIn("already exists and overwrite is False", str(ctx.exception))

    @patch("core.silence_shortener.validate_input_file")
    @patch("pathlib.Path.exists")
    @patch("core.silence_shortener.run_ffmpeg")
    def test_shorten_silence_success(self, mock_run_ffmpeg, mock_exists, mock_validate):
        mock_validate.return_value = Path("input.wav")
        mock_exists.return_value = False
        
        out_path = Path("out/output.wav")
        res = shorten_silence(
            input_path=Path("input.wav"),
            output_path=out_path,
            options=SilenceShortenerOptions(preset="fast", overwrite=True)
        )
        
        self.assertEqual(res, out_path)
        mock_run_ffmpeg.assert_called_once()
        
        call_args = mock_run_ffmpeg.call_args[0][0]
        self.assertEqual(call_args[0], "-y")
        self.assertEqual(call_args[1], "-i")
        self.assertEqual(call_args[2], "input.wav")
        self.assertEqual(call_args[3], "-af")
        self.assertTrue(call_args[4].startswith("silenceremove="))
        self.assertIn("-c:a", call_args)
        self.assertEqual(call_args[call_args.index("-c:a") + 1], "pcm_s16le")

    @patch("core.silence_shortener.shorten_silence")
    def test_shorten_silence_batch(self, mock_shorten):
        mock_shorten.side_effect = lambda inp, out, opt: out
        
        inputs = [Path("speech1.mp3"), Path("speech2.wav")]
        out_dir = Path("out_dir")
        
        res = shorten_silence_batch(inputs, out_dir)
        self.assertEqual(len(res), 2)
        
        self.assertEqual(res[0], out_dir / "speech1_shortened.mp3")
        self.assertEqual(res[1], out_dir / "speech2_shortened.wav")
