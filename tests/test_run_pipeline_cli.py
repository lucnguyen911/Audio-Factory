import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Ensure project root is in path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.run_pipeline import parse_arguments, main
from core.pipeline import PipelineError, PipelineResult, PipelineOptions


class TestRunPipelineCLI(unittest.TestCase):

    def test_parse_arguments_defaults(self):
        args = parse_arguments(["--input", "file1.wav", "file2.wav"])
        self.assertEqual(args.input, ["file1.wav", "file2.wav"])
        self.assertEqual(args.output, "output/cli_run")
        self.assertFalse(args.merge_first)
        self.assertFalse(args.volume)
        self.assertFalse(args.silence)
        self.assertFalse(args.transcribe)
        self.assertFalse(args.subtitles)
        self.assertFalse(args.split_sentences)
        self.assertFalse(args.cut_audio)
        self.assertEqual(args.project_name, "audio_project")
        self.assertEqual(args.merge_gap, 0.0)
        self.assertEqual(args.volume_preset, "natural")
        self.assertEqual(args.silence_preset, "natural")
        self.assertEqual(args.transcription_preset, "balanced")
        self.assertIsNone(args.language)
        self.assertEqual(args.output_format, "wav")
        self.assertFalse(args.no_overwrite)
        self.assertFalse(args.batch)

    def test_parse_arguments_custom(self):
        args = parse_arguments([
            "--input", "a.wav",
            "--output", "my_out",
            "--merge-first",
            "--volume",
            "--silence",
            "--transcribe",
            "--subtitles",
            "--split-sentences",
            "--cut-audio",
            "--project-name", "custom_project",
            "--merge-gap", "2.5",
            "--volume-preset", "strong",
            "--silence-preset", "fast",
            "--transcription-preset", "best",
            "--language", "vi",
            "--output-format", "mp3",
            "--no-overwrite",
            "--batch"
        ])
        
        self.assertEqual(args.input, ["a.wav"])
        self.assertEqual(args.output, "my_out")
        self.assertTrue(args.merge_first)
        self.assertTrue(args.volume)
        self.assertTrue(args.silence)
        self.assertTrue(args.transcribe)
        self.assertTrue(args.subtitles)
        self.assertTrue(args.split_sentences)
        self.assertTrue(args.cut_audio)
        self.assertEqual(args.project_name, "custom_project")
        self.assertEqual(args.merge_gap, 2.5)
        self.assertEqual(args.volume_preset, "strong")
        self.assertEqual(args.silence_preset, "fast")
        self.assertEqual(args.transcription_preset, "best")
        self.assertEqual(args.language, "vi")
        self.assertEqual(args.output_format, "mp3")
        self.assertTrue(args.no_overwrite)
        self.assertTrue(args.batch)

    @patch("scripts.run_pipeline.run_audio_pipeline")
    @patch("scripts.run_pipeline.parse_arguments")
    @patch("sys.exit")
    def test_main_single_success(self, mock_exit, mock_parse, mock_run_audio):
        # Setup mocks
        mock_args = MagicMock()
        mock_args.input = ["file.wav"]
        mock_args.output = "output/test"
        mock_args.merge_first = False
        mock_args.volume = True
        mock_args.silence = True
        mock_args.transcribe = True
        mock_args.subtitles = True
        mock_args.split_sentences = True
        mock_args.cut_audio = True
        mock_args.project_name = "test_proj"
        mock_args.merge_gap = 1.0
        mock_args.volume_preset = "aggressive"
        mock_args.silence_preset = "hard"
        mock_args.transcription_preset = "fast"
        mock_args.language = "vi"
        mock_args.output_format = "wav"
        mock_args.no_overwrite = False
        mock_args.batch = False
        
        mock_parse.return_value = mock_args
        
        mock_result = PipelineResult(
            project_name="test_proj",
            output_dir="output/test",
            input_files=["file.wav"],
            working_audio="output/test/processed/processed.wav",
            subtitle_files={"srt": "output/test/subtitles/subtitles.srt"},
            chunks=[{"file": "chunk1.wav"}],
            metadata_file="output/test/metadata/project_metadata.json"
        )
        mock_run_audio.return_value = mock_result
        
        # Run main
        main()
        
        # Verify run_audio_pipeline was called with mapped options
        mock_run_audio.assert_called_once()
        called_args, called_kwargs = mock_run_audio.call_args
        
        self.assertEqual(called_args[0], [Path("file.wav")])
        self.assertEqual(called_args[1], Path("output/test"))
        
        opts: PipelineOptions = called_args[2]
        self.assertEqual(opts.project_name, "test_proj")
        self.assertTrue(opts.enable_volume_leveling)
        self.assertTrue(opts.enable_silence_shortening)
        self.assertTrue(opts.enable_transcription)
        self.assertTrue(opts.enable_subtitle_export)
        self.assertTrue(opts.enable_sentence_split)
        self.assertTrue(opts.enable_audio_cutting)
        self.assertEqual(opts.volume_preset, "aggressive")
        self.assertEqual(opts.silence_preset, "hard")
        self.assertEqual(opts.transcription_preset, "fast")
        self.assertEqual(opts.language, "vi")
        self.assertTrue(opts.overwrite)
        
        # Check success exit
        mock_exit.assert_called_once_with(0)

    @patch("scripts.run_pipeline.run_batch_pipeline")
    @patch("scripts.run_pipeline.parse_arguments")
    @patch("sys.exit")
    def test_main_batch_success(self, mock_exit, mock_parse, mock_run_batch):
        # Setup mocks
        mock_args = MagicMock()
        mock_args.input = ["file1.wav", "file2.wav"]
        mock_args.output = "output/test"
        mock_args.merge_first = False
        mock_args.volume = False
        mock_args.silence = False
        mock_args.transcribe = False
        mock_args.subtitles = False
        mock_args.split_sentences = False
        mock_args.cut_audio = False
        mock_args.project_name = "test_proj"
        mock_args.merge_gap = 0.0
        mock_args.volume_preset = "natural"
        mock_args.silence_preset = "natural"
        mock_args.transcription_preset = "balanced"
        mock_args.language = None
        mock_args.output_format = "wav"
        mock_args.no_overwrite = True
        mock_args.batch = True
        
        mock_parse.return_value = mock_args
        
        mock_result1 = PipelineResult(
            project_name="test_proj_file1",
            output_dir="output/test/file1",
            input_files=["file1.wav"],
            working_audio="output/test/file1/processed/processed.wav"
        )
        mock_result2 = PipelineResult(
            project_name="test_proj_file2",
            output_dir="output/test/file2",
            input_files=["file2.wav"],
            working_audio="output/test/file2/processed/processed.wav"
        )
        
        mock_run_batch.return_value = [mock_result1, mock_result2]
        
        # Run main
        main()
        
        # Verify run_batch_pipeline call
        mock_run_batch.assert_called_once()
        called_args, _ = mock_run_batch.call_args
        self.assertEqual(called_args[0], [Path("file1.wav"), Path("file2.wav")])
        self.assertEqual(called_args[1], Path("output/test"))
        
        opts: PipelineOptions = called_args[2]
        self.assertFalse(opts.overwrite)
        self.assertIsNone(opts.language)
        
        mock_exit.assert_called_once_with(0)

    @patch("scripts.run_pipeline.run_audio_pipeline")
    @patch("scripts.run_pipeline.parse_arguments")
    @patch("sys.exit")
    def test_main_pipeline_error(self, mock_exit, mock_parse, mock_run_audio):
        mock_args = MagicMock()
        mock_args.input = ["file.wav"]
        mock_args.batch = False
        mock_parse.return_value = mock_args
        
        # Force PipelineError
        mock_run_audio.side_effect = PipelineError("Some validation failed")
        
        # Run main
        main()
        
        # Check error exit code 1
        mock_exit.assert_called_once_with(1)

    @patch("scripts.run_pipeline.run_audio_pipeline")
    @patch("scripts.run_pipeline.parse_arguments")
    @patch("sys.exit")
    def test_main_unexpected_error(self, mock_exit, mock_parse, mock_run_audio):
        mock_args = MagicMock()
        mock_args.input = ["file.wav"]
        mock_args.batch = False
        mock_parse.return_value = mock_args
        
        # Force general Exception
        mock_run_audio.side_effect = RuntimeError("Disk failure")
        
        # Run main
        main()
        
        # Check error exit code 1
        mock_exit.assert_called_once_with(1)
