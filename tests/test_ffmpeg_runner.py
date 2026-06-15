import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess

from core.ffmpeg_runner import (
    FFmpegError,
    find_executable,
    check_ffmpeg_available,
    run_command,
    run_ffmpeg,
    run_ffprobe
)

class TestFFmpegRunner(unittest.TestCase):

    def test_ffmpeg_error_fields(self):
        cmd = ["ffmpeg", "-i", "input.wav"]
        err = FFmpegError(cmd, 1, "some stdout", "some stderr", "Custom error details")
        self.assertEqual(err.cmd, cmd)
        self.assertEqual(err.returncode, 1)
        self.assertEqual(err.stdout, "some stdout")
        self.assertEqual(err.stderr, "some stderr")
        self.assertIn("Custom error details", str(err))
        self.assertIn("some stderr", str(err))

    @patch("core.ffmpeg_runner.shutil.which")
    @patch("pathlib.Path.is_file")
    def test_find_executable_local_bin(self, mock_is_file, mock_which):
        mock_is_file.return_value = True
        mock_which.return_value = None
        
        exe_path = find_executable("ffmpeg")
        self.assertIsNotNone(exe_path)
        # Check standard file pattern ends
        exe_path_str = str(exe_path).lower().replace("\\", "/")
        self.assertTrue(exe_path_str.endswith("bin/ffmpeg.exe") or exe_path_str.endswith("bin/ffmpeg"))

    @patch("core.ffmpeg_runner.shutil.which")
    @patch("pathlib.Path.is_file")
    def test_find_executable_system_path(self, mock_is_file, mock_which):
        mock_is_file.return_value = False
        mock_which.side_effect = lambda name: f"C:\\path\\to\\{name}" if "ffmpeg" in name else None
        
        exe_path = find_executable("ffmpeg")
        self.assertIsNotNone(exe_path)
        self.assertEqual(str(exe_path), "C:\\path\\to\\ffmpeg")

    @patch("core.ffmpeg_runner.shutil.which")
    @patch("pathlib.Path.is_file")
    def test_find_executable_not_found(self, mock_is_file, mock_which):
        mock_is_file.return_value = False
        mock_which.return_value = None
        
        exe_path = find_executable("nonexistent_tool")
        self.assertIsNone(exe_path)

    def test_run_command_success(self):
        # Run using current python executable to guarantee success on host system
        args = [sys.executable, "-c", "import sys; sys.stdout.write('test stdout'); sys.stderr.write('test stderr')"]
        result = run_command(args)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "test stdout")
        self.assertEqual(result.stderr, "test stderr")

    def test_run_command_timeout(self):
        args = [sys.executable, "-c", "import time; time.sleep(5)"]
        with self.assertRaises(FFmpegError) as ctx:
            run_command(args, timeout=1)
        self.assertIn("timed out", str(ctx.exception))

    def test_run_command_file_not_found(self):
        args = ["nonexistent_binary_file_abc"]
        with self.assertRaises(FFmpegError) as ctx:
            run_command(args)
        self.assertIn("Executable file not found", str(ctx.exception))

    @patch("core.ffmpeg_runner.find_executable")
    @patch("core.ffmpeg_runner.run_command")
    def test_check_ffmpeg_available_both_exist(self, mock_run_command, mock_find_executable):
        mock_find_executable.side_effect = lambda name: Path(f"/mock/path/{name}")
        
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run_command.return_value = mock_res
        
        self.assertTrue(check_ffmpeg_available())

    @patch("core.ffmpeg_runner.find_executable")
    def test_check_ffmpeg_available_missing_ffmpeg(self, mock_find_executable):
        mock_find_executable.side_effect = lambda name: Path("/mock/path/ffprobe") if name == "ffprobe" else None
        self.assertFalse(check_ffmpeg_available())

    @patch("core.ffmpeg_runner.find_executable")
    @patch("core.ffmpeg_runner.run_command")
    def test_run_ffmpeg_success(self, mock_run_command, mock_find_executable):
        mock_find_executable.return_value = Path("/mock/path/ffmpeg")
        
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "done"
        mock_res.stderr = ""
        mock_run_command.return_value = mock_res
        
        res = run_ffmpeg(["-i", "input.wav", "output.wav"])
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "done")
        mock_run_command.assert_called_once_with([str(Path("/mock/path/ffmpeg")), "-i", "input.wav", "output.wav"], timeout=None)

    @patch("core.ffmpeg_runner.find_executable")
    @patch("core.ffmpeg_runner.run_command")
    def test_run_ffmpeg_failure(self, mock_run_command, mock_find_executable):
        mock_find_executable.return_value = Path("/mock/path/ffmpeg")
        
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "FFmpeg specific error message"
        mock_run_command.return_value = mock_res
        
        with self.assertRaises(FFmpegError) as ctx:
            run_ffmpeg(["-i", "input.wav"])
        self.assertIn("FFmpeg specific error message", str(ctx.exception))

    @patch("core.ffmpeg_runner.find_executable")
    def test_run_ffmpeg_not_found(self, mock_find_executable):
        mock_find_executable.return_value = None
        with self.assertRaises(FFmpegError) as ctx:
            run_ffmpeg(["-i", "input.wav"])
        self.assertIn("ffmpeg executable not found", str(ctx.exception))
