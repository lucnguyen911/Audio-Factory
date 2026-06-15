import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.volume_leveler import (
    VolumeLevelingError,
    VolumeLevelingOptions,
    validate_preset,
    build_volume_filter_chain,
    level_volume,
    level_volume_batch
)

class TestVolumeLeveler(unittest.TestCase):

    def test_validate_preset(self):
        self.assertEqual(validate_preset("natural"), "natural")
        self.assertEqual(validate_preset("STRONG"), "strong")
        self.assertEqual(validate_preset("aggressive"), "aggressive")
        
        with self.assertRaises(VolumeLevelingError):
            validate_preset("invalid_preset")

    def test_build_volume_filter_chain(self):
        opts = VolumeLevelingOptions()
        
        chain_nat = build_volume_filter_chain(opts)
        self.assertGreater(len(chain_nat), 0)
        self.assertIn("compand", chain_nat)
        self.assertIn("loudnorm", chain_nat)
        self.assertIn("alimiter", chain_nat)
        
        opts_strong = VolumeLevelingOptions(preset="strong")
        chain_strong = build_volume_filter_chain(opts_strong)
        
        opts_agg = VolumeLevelingOptions(preset="aggressive")
        chain_agg = build_volume_filter_chain(opts_agg)
        
        self.assertNotEqual(chain_nat, chain_strong)
        self.assertNotEqual(chain_strong, chain_agg)

    @patch("core.volume_leveler.validate_input_file")
    @patch("pathlib.Path.exists")
    def test_level_volume_no_overwrite(self, mock_exists, mock_validate):
        mock_validate.return_value = Path("input.mp3")
        mock_exists.return_value = True
        
        with self.assertRaises(VolumeLevelingError) as ctx:
            level_volume(
                input_path=Path("input.mp3"),
                output_path=Path("output.mp3"),
                options=VolumeLevelingOptions(overwrite=False)
            )
        self.assertIn("already exists and overwrite is False", str(ctx.exception))

    @patch("core.volume_leveler.validate_input_file")
    @patch("pathlib.Path.exists")
    @patch("core.volume_leveler.run_ffmpeg")
    def test_level_volume_success(self, mock_run_ffmpeg, mock_exists, mock_validate):
        mock_validate.return_value = Path("input.wav")
        mock_exists.return_value = False
        
        out_path = Path("out/output.wav")
        res = level_volume(
            input_path=Path("input.wav"),
            output_path=out_path,
            options=VolumeLevelingOptions(preset="strong", sample_rate=44100, channels=2, overwrite=True)
        )
        
        self.assertEqual(res, out_path)
        mock_run_ffmpeg.assert_called_once()
        
        call_args = mock_run_ffmpeg.call_args[0][0]
        self.assertEqual(call_args[0], "-y")
        self.assertEqual(call_args[1], "-i")
        self.assertEqual(call_args[2], "input.wav")
        self.assertEqual(call_args[3], "-af")
        self.assertIn("compand", call_args[4])
        self.assertIn("-ar", call_args)
        self.assertEqual(call_args[call_args.index("-ar") + 1], "44100")
        self.assertIn("-ac", call_args)
        self.assertEqual(call_args[call_args.index("-ac") + 1], "2")
        self.assertIn("-c:a", call_args)
        self.assertEqual(call_args[call_args.index("-c:a") + 1], "pcm_s16le")

    @patch("core.volume_leveler.level_volume")
    def test_level_volume_batch(self, mock_level_volume):
        mock_level_volume.side_effect = lambda inp, out, opt: out
        
        inputs = [Path("audio1.mp3"), Path("audio2.wav")]
        out_dir = Path("out_dir")
        
        res = level_volume_batch(inputs, out_dir)
        self.assertEqual(len(res), 2)
        
        self.assertEqual(res[0], out_dir / "audio1_leveled.mp3")
        self.assertEqual(res[1], out_dir / "audio2_leveled.wav")
