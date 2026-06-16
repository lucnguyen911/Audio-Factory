import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

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
        
        self.assertEqual(res["merged"], out / "merged")
        self.assertEqual(res["processed"], out / "processed")
        self.assertEqual(res["subtitles"], out / "subtitles")
        self.assertEqual(res["chunks"], out / "chunks")
        self.assertEqual(res["metadata"], out / "metadata")
        self.assertEqual(mock_mkdir.call_count, 5)

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.level_volume")
    @patch("core.pipeline.shorten_silence")
    @patch("core.pipeline.export_project_json")
    def test_run_audio_pipeline_basic(self, mock_export_meta, mock_shorten, mock_level, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "merged": out_dir / "merged",
            "processed": out_dir / "processed",
            "subtitles": out_dir / "subtitles",
            "chunks": out_dir / "chunks",
            "metadata": out_dir / "metadata"
        }
        mock_level.return_value = out_dir / "processed" / "leveled.wav"
        mock_shorten.return_value = out_dir / "processed" / "processed.wav"
        
        opts = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=True,
            enable_silence_shortening=True,
            enable_transcription=False
        )
        
        res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
        
        self.assertEqual(res.working_audio, (out_dir / "processed" / "processed.wav").as_posix())
        self.assertEqual(res.leveled_file, (out_dir / "processed" / "leveled.wav").as_posix())
        self.assertEqual(res.shortened_file, (out_dir / "processed" / "processed.wav").as_posix())
        mock_level.assert_called_once()
        mock_shorten.assert_called_once()
        mock_export_meta.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.merge_audio_files")
    @patch("core.pipeline.export_project_json")
    def test_run_audio_pipeline_merge(self, mock_export_meta, mock_merge, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("1.wav"), Path("2.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "merged": out_dir / "merged",
            "processed": out_dir / "processed",
            "subtitles": out_dir / "subtitles",
            "chunks": out_dir / "chunks",
            "metadata": out_dir / "metadata"
        }
        mock_merge.return_value = out_dir / "merged" / "merged.wav"
        
        opts = PipelineOptions(
            merge_first=True,
            enable_volume_leveling=False,
            enable_silence_shortening=False,
            enable_transcription=False
        )
        
        res = run_audio_pipeline([Path("1.wav"), Path("2.wav")], out_dir, opts)
        self.assertEqual(res.merged_file, (out_dir / "merged" / "merged.wav").as_posix())
        mock_merge.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.transcribe_media")
    @patch("core.pipeline.export_all_subtitles")
    @patch("core.pipeline.export_project_json")
    def test_run_audio_pipeline_subtitle(self, mock_export_meta, mock_export_subs, mock_transcribe, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "merged": out_dir / "merged",
            "processed": out_dir / "processed",
            "subtitles": out_dir / "subtitles",
            "chunks": out_dir / "chunks",
            "metadata": out_dir / "metadata"
        }
        
        mock_transcribe.return_value = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
        mock_export_subs.return_value = {"srt": "out/subtitles/subtitles.srt", "vtt": "out/subtitles/subtitles.vtt"}
        
        opts = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=False,
            enable_silence_shortening=False,
            enable_transcription=True,
            enable_subtitle_export=True,
            language="vi"
        )
        
        res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
        self.assertEqual(res.subtitle_files["srt"], "out/subtitles/subtitles.srt")
        mock_transcribe.assert_called_once()
        called_args = mock_transcribe.call_args[0]
        self.assertEqual(called_args[0], Path("input.wav"))
        self.assertEqual(called_args[1].language, "vi")
        mock_export_subs.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.prepare_output_dirs")
    @patch("core.pipeline.transcribe_media")
    @patch("core.pipeline.split_segments_by_sentence")
    @patch("core.pipeline.cut_audio_by_sentences")
    @patch("core.pipeline.export_project_json")
    def test_run_audio_pipeline_split_cut(self, mock_export_meta, mock_cut, mock_split, mock_transcribe, mock_dirs, mock_validate):
        mock_validate.return_value = [Path("input.wav")]
        out_dir = Path("out")
        mock_dirs.return_value = {
            "merged": out_dir / "merged",
            "processed": out_dir / "processed",
            "subtitles": out_dir / "subtitles",
            "chunks": out_dir / "chunks",
            "metadata": out_dir / "metadata"
        }
        
        mock_transcribe.return_value = [{"start": 0.0, "end": 1.0, "text": "Hello"}]
        mock_split.return_value = [{"index": 1, "start": 0.0, "end": 1.0, "text": "Hello"}]
        mock_cut.return_value = [{"index": 1, "start": 0.0, "end": 1.0, "text": "Hello", "file": "001.wav"}]
        
        opts = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=False,
            enable_silence_shortening=False,
            enable_transcription=True,
            enable_sentence_split=True,
            enable_audio_cutting=True
        )
        
        res = run_audio_pipeline([Path("input.wav")], out_dir, opts)
        self.assertEqual(res.chunks[0]["file"], "001.wav")
        mock_split.assert_called_once()
        mock_cut.assert_called_once()

    @patch("core.pipeline.validate_pipeline_inputs")
    @patch("core.pipeline.run_audio_pipeline")
    def test_run_batch_pipeline(self, mock_run_pipeline, mock_validate):
        mock_validate.return_value = [Path("1.wav"), Path("2.wav")]
        mock_run_pipeline.side_effect = lambda paths, out, opt: PipelineResult(
            project_name=opt.project_name,
            output_dir=out.as_posix(),
            input_files=[p.as_posix() for p in paths]
        )
        
        res = run_batch_pipeline([Path("1.wav"), Path("2.wav")], Path("out"))
        self.assertEqual(len(res), 2)
        self.assertEqual(res[0].output_dir, "out/1")
        self.assertEqual(res[1].output_dir, "out/2")

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
