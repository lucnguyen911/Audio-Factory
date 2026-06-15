import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.merger import (
    AudioMergeError,
    MergeOptions,
    validate_merge_inputs,
    create_silence_file,
    build_concat_list_file,
    merge_audio_files
)

class TestMerger(unittest.TestCase):

    def test_validate_merge_inputs_empty(self):
        with self.assertRaises(AudioMergeError) as ctx:
            validate_merge_inputs([])
        self.assertIn("empty", str(ctx.exception))

    @patch("core.merger.validate_input_file")
    def test_validate_merge_inputs_preserves_order(self, mock_validate):
        mock_validate.side_effect = lambda p: Path(p)
        
        inputs = [Path("file_c.wav"), Path("file_a.wav"), Path("file_b.wav")]
        validated = validate_merge_inputs(inputs)
        self.assertEqual(validated, inputs)

    @patch("core.merger.validate_input_file")
    @patch("pathlib.Path.exists")
    def test_merge_audio_files_no_overwrite(self, mock_exists, mock_validate):
        mock_validate.side_effect = lambda p: Path(p)
        mock_exists.return_value = True
        
        with self.assertRaises(AudioMergeError) as ctx:
            merge_audio_files(
                input_paths=[Path("file_a.wav")],
                output_path=Path("out.wav"),
                options=MergeOptions(overwrite=False)
            )
        self.assertIn("already exists and overwrite is False", str(ctx.exception))

    def test_build_concat_list_file(self):
        temp_list_file = Path("temp_list.txt")
        if temp_list_file.exists():
            temp_list_file.unlink()
            
        inputs = [Path("dir/file_a.wav"), Path("dir/file_b.wav"), Path("dir/file'with'quote.wav")]
        
        try:
            build_concat_list_file(inputs, temp_list_file)
            self.assertTrue(temp_list_file.exists())
            
            content = temp_list_file.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            self.assertEqual(len(lines), 3)
            self.assertTrue(lines[0].startswith("file '"))
            self.assertTrue(lines[0].endswith("dir/file_a.wav'"))
            self.assertIn("file'\\''with'\\''quote.wav", lines[2])
        finally:
            if temp_list_file.exists():
                temp_list_file.unlink()

    @patch("core.merger.run_ffmpeg")
    def test_create_silence_file(self, mock_run_ffmpeg):
        with self.assertRaises(AudioMergeError):
            create_silence_file(Path("silence.wav"), duration_seconds=0.0)
            
        out_path = Path("silence.wav")
        create_silence_file(out_path, duration_seconds=2.5, sample_rate=16000, channels=1)
        
        mock_run_ffmpeg.assert_called_once_with([
            "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=16000:cl=mono",
            "-t", "2.500000",
            str(out_path)
        ])

    @patch("core.merger.validate_merge_inputs")
    @patch("pathlib.Path.exists")
    @patch("core.merger.create_silence_file")
    @patch("core.merger.run_ffmpeg")
    def test_merge_audio_files_success(self, mock_run_ffmpeg, mock_create_silence, mock_exists, mock_validate):
        mock_validate.return_value = [Path("a.wav"), Path("b.wav")]
        mock_exists.return_value = False
        
        out_path = Path("output.mp3")
        res = merge_audio_files(
            input_paths=[Path("a.wav"), Path("b.wav")],
            output_path=out_path,
            options=MergeOptions(gap_seconds=1.5, sample_rate=22050, channels=2, overwrite=True)
        )
        
        self.assertEqual(res, out_path)
        mock_create_silence.assert_called_once()
        
        mock_run_ffmpeg.assert_called_once()
        call_args = mock_run_ffmpeg.call_args[0][0]
        
        self.assertEqual(call_args[0], "-y")
        self.assertEqual(call_args[1], "-f")
        self.assertEqual(call_args[2], "concat")
        self.assertEqual(call_args[3], "-safe")
        self.assertEqual(call_args[4], "0")
        self.assertEqual(call_args[5], "-i")
        self.assertIn("-c:a", call_args)
        self.assertIn("libmp3lame", call_args)
        self.assertIn("-ar", call_args)
        self.assertIn("22050", call_args)
        self.assertIn("-ac", call_args)
        self.assertIn("2", call_args)
