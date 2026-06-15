import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.importer import (
    MediaImportError,
    is_supported_media,
    validate_input_file,
    probe_media,
    get_duration_seconds,
    convert_to_work_wav
)
from core.ffmpeg_runner import FFmpegError

class TestImporter(unittest.TestCase):

    def test_is_supported_media(self):
        # Supported extensions
        self.assertTrue(is_supported_media(Path("audio.mp3")))
        self.assertTrue(is_supported_media(Path("video.mp4")))
        self.assertTrue(is_supported_media(Path("AUDIO.WAV")))
        self.assertTrue(is_supported_media(Path("dir/file.flac")))
        self.assertTrue(is_supported_media(Path("file.mkv")))
        
        # Unsupported extensions
        self.assertFalse(is_supported_media(Path("file.txt")))
        self.assertFalse(is_supported_media(Path("file.png")))
        self.assertFalse(is_supported_media(Path("file.zip")))
        self.assertFalse(is_supported_media(Path("file")))

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.is_file")
    def test_validate_input_file_success(self, mock_is_file, mock_exists):
        mock_exists.return_value = True
        mock_is_file.return_value = True
        
        path = Path("test.mp3")
        resolved = validate_input_file(path)
        self.assertEqual(resolved, path)

    @patch("pathlib.Path.exists")
    def test_validate_input_file_not_exist(self, mock_exists):
        mock_exists.return_value = False
        
        with self.assertRaises(MediaImportError) as ctx:
            validate_input_file(Path("nonexistent.mp3"))
        self.assertIn("does not exist", str(ctx.exception))

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.is_file")
    def test_validate_input_file_is_directory(self, mock_is_file, mock_exists):
        mock_exists.return_value = True
        mock_is_file.return_value = False
        
        with self.assertRaises(MediaImportError) as ctx:
            validate_input_file(Path("directory.mp3"))
        self.assertIn("is not a file", str(ctx.exception))

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.is_file")
    def test_validate_input_file_unsupported(self, mock_is_file, mock_exists):
        mock_exists.return_value = True
        mock_is_file.return_value = True
        
        with self.assertRaises(MediaImportError) as ctx:
            validate_input_file(Path("test.png"))
        self.assertIn("Unsupported file format", str(ctx.exception))

    @patch("core.importer.validate_input_file")
    @patch("core.importer.run_ffprobe")
    def test_probe_media_success(self, mock_run_ffprobe, mock_validate):
        mock_validate.return_value = Path("test.mp3")
        
        mock_res = MagicMock()
        mock_res.stdout = '{"format": {"duration": "123.45"}, "streams": []}'
        mock_run_ffprobe.return_value = mock_res
        
        metadata = probe_media(Path("test.mp3"))
        self.assertEqual(metadata["format"]["duration"], "123.45")
        mock_run_ffprobe.assert_called_once()

    @patch("core.importer.validate_input_file")
    @patch("core.importer.run_ffprobe")
    def test_probe_media_ffprobe_error(self, mock_run_ffprobe, mock_validate):
        mock_validate.return_value = Path("test.mp3")
        mock_run_ffprobe.side_effect = FFmpegError(["ffprobe"], 1, "", "Corrupted file")
        
        with self.assertRaises(MediaImportError) as ctx:
            probe_media(Path("test.mp3"))
        self.assertIn("Failed to probe media file", str(ctx.exception))

    @patch("core.importer.validate_input_file")
    @patch("core.importer.run_ffprobe")
    def test_probe_media_invalid_json(self, mock_run_ffprobe, mock_validate):
        mock_validate.return_value = Path("test.mp3")
        mock_res = MagicMock()
        mock_res.stdout = "{invalid json}"
        mock_run_ffprobe.return_value = mock_res
        
        with self.assertRaises(MediaImportError) as ctx:
            probe_media(Path("test.mp3"))
        self.assertIn("Failed to parse ffprobe output", str(ctx.exception))

    @patch("core.importer.probe_media")
    def test_get_duration_seconds_format(self, mock_probe):
        mock_probe.return_value = {"format": {"duration": "60.5"}}
        duration = get_duration_seconds(Path("test.mp3"))
        self.assertEqual(duration, 60.5)

    @patch("core.importer.probe_media")
    def test_get_duration_seconds_streams(self, mock_probe):
        mock_probe.return_value = {
            "format": {},
            "streams": [{"duration": "120.25"}]
        }
        duration = get_duration_seconds(Path("test.mp3"))
        self.assertEqual(duration, 120.25)

    @patch("core.importer.probe_media")
    def test_get_duration_seconds_missing(self, mock_probe):
        mock_probe.return_value = {"format": {}, "streams": []}
        with self.assertRaises(MediaImportError) as ctx:
            get_duration_seconds(Path("test.mp3"))
        self.assertIn("Could not determine duration", str(ctx.exception))

    @patch("core.importer.validate_input_file")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.exists")
    @patch("core.importer.run_ffmpeg")
    def test_convert_to_work_wav_success(self, mock_run_ffmpeg, mock_exists, mock_mkdir, mock_validate):
        mock_validate.return_value = Path("input.mp4")
        mock_exists.return_value = False
        
        output_path = Path("out/normalized.wav")
        res_path = convert_to_work_wav(
            input_path=Path("input.mp4"),
            output_path=output_path,
            sample_rate=16000,
            channels=1,
            overwrite=True
        )
        
        self.assertEqual(res_path, output_path)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_run_ffmpeg.assert_called_once_with([
            "-y",
            "-i", "input.mp4",
            "-ar", "16000",
            "-ac", "1",
            "-acodec", "pcm_s16le",
            str(output_path)
        ])

    @patch("core.importer.validate_input_file")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.exists")
    def test_convert_to_work_wav_no_overwrite(self, mock_exists, mock_mkdir, mock_validate):
        mock_validate.return_value = Path("input.mp4")
        mock_exists.return_value = True
        
        with self.assertRaises(MediaImportError) as ctx:
            convert_to_work_wav(
                input_path=Path("input.mp4"),
                output_path=Path("out/normalized.wav"),
                overwrite=False
            )
        self.assertIn("already exists and overwrite is set to False", str(ctx.exception))
