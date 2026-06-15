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
        self.assertNotIn("compand", chain_nat)
        self.assertIn("dynaudnorm", chain_nat)
        self.assertIn("loudnorm", chain_nat)
        self.assertIn("alimiter", chain_nat)
        
        # Verify specific parameters for presets
        self.assertIn("dynaudnorm=f=250:g=7:p=0.95:m=5", chain_nat)
        self.assertIn("loudnorm=i=-16.0:tp=-1.5:lra=11.0", chain_nat)
        self.assertIn("alimiter=limit=0.89", chain_nat)
        
        opts_strong = VolumeLevelingOptions(preset="strong")
        chain_strong = build_volume_filter_chain(opts_strong)
        self.assertNotIn("compand", chain_strong)
        self.assertIn("dynaudnorm=f=200:g=11:p=0.95:m=8", chain_strong)
        self.assertIn("loudnorm=i=-16.0:tp=-1.5:lra=9.0", chain_strong)
        self.assertIn("alimiter=limit=0.89", chain_strong)
        
        opts_agg = VolumeLevelingOptions(preset="aggressive")
        chain_agg = build_volume_filter_chain(opts_agg)
        self.assertNotIn("compand", chain_agg)
        self.assertIn("dynaudnorm=f=150:g=15:p=0.95:m=10", chain_agg)
        self.assertIn("loudnorm=i=-14.0:tp=-1.2:lra=7.0", chain_agg)
        self.assertIn("alimiter=limit=0.87", chain_agg)
        
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
        self.assertNotIn("compand", call_args[4])
        self.assertIn("dynaudnorm", call_args[4])
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

    def test_level_volume_smoke(self):
        from core.ffmpeg_runner import check_ffmpeg_available, run_ffmpeg
        if not check_ffmpeg_available():
            self.skipTest("FFmpeg is not available in system PATH or local bin/ folder.")
            
        project_root = Path(__file__).resolve().parent.parent
        temp_dir = project_root / "temp_test_volume"
        temp_dir.mkdir(exist_ok=True)
        
        temp_input = temp_dir / "temp_input.wav"
        temp_output = temp_dir / "temp_output.wav"
        
        try:
            # Generate a 1-second silent mono wav audio
            run_ffmpeg([
                "-y",
                "-f", "lavfi",
                "-i", "anullsrc=r=16000:cl=mono",
                "-t", "1",
                str(temp_input)
            ])
            self.assertTrue(temp_input.exists(), "Failed to generate temporary input file for smoke test.")
            
            # Execute real volume leveling
            opts = VolumeLevelingOptions(preset="natural", overwrite=True)
            res = level_volume(temp_input, temp_output, opts)
            
            self.assertEqual(res, temp_output)
            self.assertTrue(temp_output.exists(), "Output file was not created by level_volume.")
            self.assertGreater(temp_output.stat().st_size, 0, "Output file is empty.")
            
        finally:
            # Clean up files manually
            if temp_input.exists():
                temp_input.unlink()
            if temp_output.exists():
                temp_output.unlink()
            if temp_dir.exists():
                temp_dir.rmdir()
