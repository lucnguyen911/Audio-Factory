import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import shutil

from core.pipeline import (
    PipelineError,
    PipelineOptions,
    PipelineResult,
    validate_pipeline_inputs,
    prepare_output_dirs,
    run_audio_pipeline,
    run_batch_pipeline,
    pipeline_result_to_dict
)

class TestPipeline(unittest.TestCase):

    def test_validate_pipeline_inputs_empty(self):
        with self.assertRaises(PipelineError):
            validate_pipeline_inputs([])

    @patch("core.pipeline.validate_input_file")
    def test_validate_pipeline_inputs_order(self, mock_validate):
        mock_validate.side_effect = lambda p: Path(p)
        inputs = [Path("b.wav"), Path("a.wav")]
        res = validate_pipeline_inputs(inputs)
        self.assertEqual(res, inputs)

    @patch("pathlib.Path.mkdir")
    def test_prepare_output_dirs(self, mock_mkdir):
        out = Path("my_proj")
        res = prepare_output_dirs(out)
        
        self.assertEqual(res["final"], out / "final")
        self.assertEqual(res["subtitles"], out / "subtitles")
        self.assertEqual(res["metadata"], out / "metadata")
        self.assertEqual(res["work"], out / "work")

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.clean_voice")
    @patch("core.pipeline.level_volume")
    @patch("core.pipeline.shorten_silence")
    @patch("core.pipeline.optimize_social_audio")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_basic(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_social, mock_shorten, mock_level, mock_clean, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        mock_clean.return_value = out_dir / "audio_project" / "work" / "input_cleaned.wav"
        mock_level.return_value = out_dir / "audio_project" / "work" / "input_leveled.wav"
        mock_shorten.return_value = out_dir / "audio_project" / "work" / "input_shortened.wav"
        mock_social.return_value = out_dir / "audio_project" / "work" / "input_optimized.wav"
        
        opts = PipelineOptions(
            merge_first=False,
            enable_voice_cleanup=True,
            enable_volume_leveling=True,
            enable_silence_shortening=True,
            enable_social_optimize=True,
            enable_transcription=False
        )
        
        res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
        
        # Verify result outputs
        self.assertEqual(res.working_audio, (out_dir / "audio_project" / "final" / "input_final.wav").as_posix())
        self.assertEqual(res.leveled_file, (out_dir / "audio_project" / "work" / "input_leveled.wav").as_posix())
        self.assertEqual(res.shortened_file, (out_dir / "audio_project" / "work" / "input_shortened.wav").as_posix())
        
        # Check chaining order
        mock_clean.assert_called_once_with(Path("input.wav"), out_dir / "audio_project" / "work" / "input_cleaned.wav", overwrite=True)
        mock_level.assert_called_once_with(out_dir / "audio_project" / "work" / "input_cleaned.wav", out_dir / "audio_project" / "work" / "input_leveled.wav", unittest.mock.ANY)
        mock_shorten.assert_called_once_with(out_dir / "audio_project" / "work" / "input_leveled.wav", out_dir / "audio_project" / "work" / "input_shortened.wav", unittest.mock.ANY)
        mock_social.assert_called_once_with(out_dir / "audio_project" / "work" / "input_shortened.wav", out_dir / "audio_project" / "work" / "input_optimized.wav", platform='general', overwrite=True)
        mock_copy.assert_called_once()
        mock_export_meta.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.merge_audio_files")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_merge(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_merge, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("1.wav"), Path("2.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        mock_merge.return_value = out_dir / "audio_project" / "work" / "merged.wav"
        
        opts = PipelineOptions(
            merge_first=True,
            enable_volume_leveling=False,
            enable_silence_shortening=False,
            enable_transcription=False
        )
        
        res = run_audio_pipeline([Path("1.wav"), Path("2.wav")], out_dir, opts)
        self.assertEqual(res.merged_file, (out_dir / "audio_project" / "work" / "merged.wav").as_posix())
        mock_merge.assert_called_once()
        mock_copy.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.transcribe_media")
    @patch("core.pipeline.export_all_subtitles")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_subtitle(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_export_subs, mock_transcribe, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        
        mock_transcribe.return_value = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
        mock_export_subs.return_value = {
            "srt": out_dir / "audio_project" / "subtitles" / "input.srt",
            "vtt": out_dir / "audio_project" / "subtitles" / "input.vtt"
        }
        
        opts = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=False,
            enable_silence_shortening=False,
            enable_transcription=True,
            enable_subtitle_export=True,
            language="vi"
        )
        
        res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
        self.assertEqual(res.subtitle_files["input"]["srt"], (out_dir / "audio_project" / "subtitles" / "input.srt").as_posix())
        mock_transcribe.assert_called_once()
        called_args = mock_transcribe.call_args[0]
        self.assertEqual(called_args[0], out_dir / "audio_project" / "final" / "input_final.wav")
        self.assertEqual(called_args[1].language, "vi")
        mock_export_subs.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.run_audio_pipeline")
    def test_run_batch_pipeline(self, mock_run_pipeline, mock_validate):
        mock_validate.return_value = [Path("1.wav"), Path("2.wav")]
        
        mock_result = PipelineResult(
            project_name="audio_project",
            output_dir="out/audio_project",
            input_files=["1.wav", "2.wav"],
            working_audio=["out/audio_project/final/1_final.wav", "out/audio_project/final/2_final.wav"],
            subtitle_files={
                "1": {"srt": "out/audio_project/subtitles/1.srt"},
                "2": {"srt": "out/audio_project/subtitles/2.srt"}
            },
            metadata_file="out/audio_project/metadata/project_metadata.json"
        )
        mock_run_pipeline.return_value = mock_result
        
        res = run_batch_pipeline([Path("1.wav"), Path("2.wav")], Path("out"))
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].output_dir, "out/audio_project")
        self.assertEqual(res[0].project_name, "1")
        self.assertEqual(res[0].working_audio, "out/audio_project/final/1_final.wav")
        self.assertEqual(res[1].project_name, "2")
        self.assertEqual(res[1].working_audio, "out/audio_project/final/2_final.wav")

    def test_pipeline_result_to_dict(self):
        res = PipelineResult(
            project_name="proj",
            output_dir="out",
            input_files=["in.wav"],
            working_audio="out/processed.wav"
        )
        data = pipeline_result_to_dict(res)
        self.assertEqual(data["project_name"], "proj")
        self.assertEqual(data["output_dir"], "out")

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_folder_safety_suffix(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        
        opts = PipelineOptions(
            project_name="audio_project",
            overwrite=False,
            enable_volume_leveling=False,
            enable_silence_shortening=False
        )
        
        with patch("core.pipeline.Path.exists") as mock_path_exists:
            mock_path_exists.side_effect = [True, False, False, False, False, False, False, False, False]
            res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
            
        self.assertEqual(res.project_name, "audio_project_01")
        self.assertEqual(res.output_dir, (out_dir / "audio_project_01").as_posix())

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.merge_audio_files")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_single_file_merge_skip(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_merge, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("single.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        
        opts = PipelineOptions(
            merge_first=True,
            enable_volume_leveling=False,
            enable_silence_shortening=False
        )
        
        res = run_audio_pipeline([Path("single.wav")], out_dir, opts)
        self.assertIsNone(res.merged_file)
        mock_merge.assert_not_called()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.shorten_silence")
    @patch("core.pipeline.transcribe_media")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_silence_shortening_routing(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_transcribe, mock_shorten, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        mock_shorten.return_value = out_dir / "audio_project" / "work" / "shortened.wav"
        
        opts = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=False,
            enable_silence_shortening=True,
            enable_transcription=True
        )
        
        res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
        mock_transcribe.assert_called_once()
        called_args = mock_transcribe.call_args[0]
        self.assertEqual(called_args[0], out_dir / "audio_project" / "final" / "input_final.wav")
        self.assertEqual(res.shortened_file, (out_dir / "audio_project" / "work" / "shortened.wav").as_posix())

    @patch("core.pipeline.validate_pipeline_inputs")
    def test_run_audio_pipeline_invalid_language(self, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        opts = PipelineOptions(language="invalid_language_code")
        with self.assertRaises(PipelineError):
            run_audio_pipeline([Path("input.wav")], Path("out"), opts)

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.transcribe_media")
    @patch("core.pipeline.export_project_json")
    @patch("core.pipeline.run_ffmpeg")
    @patch("shutil.copy2")
    def test_run_audio_pipeline_subtitle_word_timestamps_passed(self, mock_copy, mock_run_ffmpeg, mock_export_meta, mock_transcribe, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "final": out_dir / "audio_project" / "final",
            "subtitles": out_dir / "audio_project" / "subtitles",
            "metadata": out_dir / "audio_project" / "metadata",
            "work": out_dir / "audio_project" / "work"
        }
        
        opts = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=False,
            enable_silence_shortening=False,
            enable_transcription=True,
            enable_subtitle_export=True
        )
        
        run_audio_pipeline([Path("input.wav")], out_dir, opts)
        mock_transcribe.assert_called_once()
        called_options = mock_transcribe.call_args[0][1]
        self.assertTrue(called_options.word_timestamps)

if __name__ == "__main__":
    unittest.main()
