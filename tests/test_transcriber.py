import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.transcriber import (
    TranscriptionError,
    TranscriptionOptions,
    model_size_from_preset,
    load_whisper_model,
    transcribe_media,
    transcribe_to_dicts
)

class TestTranscriber(unittest.TestCase):

    def test_model_size_from_preset(self):
        self.assertEqual(model_size_from_preset("fast"), "base")
        self.assertEqual(model_size_from_preset("balanced"), "small")
        self.assertEqual(model_size_from_preset("accurate"), "medium")
        self.assertEqual(model_size_from_preset("best"), "large-v3")
        
        with self.assertRaises(TranscriptionError):
            model_size_from_preset("invalid_preset")

    def test_load_whisper_model_missing_library(self):
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with self.assertRaises(TranscriptionError) as ctx:
                load_whisper_model(TranscriptionOptions())
            self.assertIn("'faster-whisper' package is not installed", str(ctx.exception))

    def test_load_whisper_model_success(self):
        mock_model_cls = MagicMock()
        mock_model_instance = MagicMock()
        mock_model_cls.return_value = mock_model_instance
        
        # Inject mock faster_whisper module into sys.modules
        mock_module = MagicMock()
        mock_module.WhisperModel = mock_model_cls
        
        with patch.dict("sys.modules", {"faster_whisper": mock_module}):
            opts = TranscriptionOptions(model_size="tiny", device="cpu", compute_type="int8")
            res = load_whisper_model(opts)
            self.assertEqual(res, mock_model_instance)
            mock_model_cls.assert_called_once_with("tiny", device="cpu", compute_type="int8")

    @patch("core.transcriber.load_whisper_model")
    @patch("core.transcriber.validate_input_file")
    @patch("faster_whisper.BatchedInferencePipeline", create=True)
    def test_transcribe_media_success(self, mock_batched, mock_validate, mock_load):
        mock_validate.return_value = Path("input.wav")
        
        seg1 = MagicMock()
        seg1.start = 0.5
        seg1.end = 2.0
        seg1.text = " Hello world "
        
        seg2 = MagicMock()
        seg2.start = 2.0
        seg2.end = 3.5
        seg2.text = "   "
        
        seg3 = MagicMock()
        seg3.start = 3.5
        seg3.end = 5.0
        seg3.text = "Another segment"
        
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.transcribe.return_value = ([seg1, seg2, seg3], None)
        mock_batched.return_value = mock_pipeline_instance
        
        res = transcribe_media(Path("input.wav"))
        
        self.assertEqual(len(res), 2)
        
        self.assertEqual(res[0].index, 1)
        self.assertEqual(res[0].start, 0.5)
        self.assertEqual(res[0].end, 2.0)
        self.assertEqual(res[0].text, "Hello world")
        
        self.assertEqual(res[1].index, 2)
        self.assertEqual(res[1].start, 3.5)
        self.assertEqual(res[1].end, 5.0)
        self.assertEqual(res[1].text, "Another segment")
        
        mock_pipeline_instance.transcribe.assert_called_once_with(
            "input.wav",
            language=None,
            beam_size=5,
            vad_filter=True,
            word_timestamps=False,
            batch_size=8
        )

    @patch("core.transcriber.load_whisper_model")
    @patch("core.transcriber.validate_input_file")
    @patch("faster_whisper.BatchedInferencePipeline", create=True)
    def test_transcribe_media_with_language(self, mock_batched, mock_validate, mock_load):
        mock_validate.return_value = Path("input.wav")
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.transcribe.return_value = ([], None)
        mock_batched.return_value = mock_pipeline_instance
        
        opts = TranscriptionOptions(language="vi")
        transcribe_media(Path("input.wav"), opts)
        
        mock_pipeline_instance.transcribe.assert_called_once_with(
            "input.wav",
            language="vi",
            beam_size=5,
            vad_filter=True,
            word_timestamps=False,
            batch_size=8
        )

    @patch("core.transcriber.transcribe_media")
    def test_transcribe_to_dicts(self, mock_transcribe):
        from core.subtitle_exporter import TranscriptSegment
        mock_transcribe.return_value = [
            TranscriptSegment(start=1.0, end=2.0, text="Hello", index=1, words=[{"word": "Hello", "start": 1.0, "end": 2.0}])
        ]
        
        res = transcribe_to_dicts(Path("input.wav"))
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["index"], 1)
        self.assertEqual(res[0]["start"], 1.0)
        self.assertEqual(res[0]["end"], 2.0)
        self.assertEqual(res[0]["text"], "Hello")
        self.assertEqual(res[0]["words"], [{"word": "Hello", "start": 1.0, "end": 2.0}])

    @patch("core.transcriber.load_whisper_model")
    @patch("core.transcriber.validate_input_file")
    @patch("faster_whisper.BatchedInferencePipeline", create=True)
    def test_transcribe_media_word_timestamps(self, mock_batched, mock_validate, mock_load):
        mock_validate.return_value = Path("input.wav")
        
        mock_word1 = MagicMock()
        mock_word1.word = "Hello"
        mock_word1.start = 0.5
        mock_word1.end = 1.2
        mock_word1.probability = 0.9
        
        mock_word2 = MagicMock()
        mock_word2.word = "world"
        mock_word2.start = 1.3
        mock_word2.end = 2.0
        mock_word2.probability = 0.95
        
        seg1 = MagicMock()
        seg1.start = 0.5
        seg1.end = 2.0
        seg1.text = "Hello world"
        seg1.words = [mock_word1, mock_word2]
        
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.transcribe.return_value = ([seg1], None)
        mock_batched.return_value = mock_pipeline_instance
        
        opts = TranscriptionOptions(word_timestamps=True)
        res = transcribe_media(Path("input.wav"), opts)
        
        self.assertEqual(len(res), 1)
        self.assertIsNotNone(res[0].words)
        self.assertEqual(len(res[0].words), 2)
        self.assertEqual(res[0].words[0]["word"], "Hello")
        self.assertEqual(res[0].words[0]["start"], 0.5)
        self.assertEqual(res[0].words[0]["end"], 1.2)

    @patch("core.transcriber.load_whisper_model")
    @patch("core.transcriber.validate_input_file")
    @patch("faster_whisper.BatchedInferencePipeline", create=True)
    def test_transcribe_media_speed_remapping(self, mock_batched, mock_validate, mock_load):
        mock_validate.return_value = Path("input.wav")
        
        mock_word1 = MagicMock()
        mock_word1.word = "Hello"
        mock_word1.start = 1.0
        mock_word1.end = 2.0
        
        seg1 = MagicMock()
        seg1.start = 1.0
        seg1.end = 3.0
        seg1.text = "Hello"
        seg1.words = [mock_word1]
        
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.transcribe.return_value = ([seg1], None)
        mock_batched.return_value = mock_pipeline_instance
        
        with patch("core.ffmpeg_runner.run_ffmpeg") as mock_ffmpeg, \
             patch("tempfile.mkstemp") as mock_mkstemp, \
             patch("os.close") as mock_close, \
             patch("os.unlink") as mock_unlink:
            mock_mkstemp.return_value = (0, "temp.wav")
            
            opts = TranscriptionOptions(asr_audio_speed=0.5, word_timestamps=True)
            res = transcribe_media(Path("input.wav"), opts)
            
            self.assertEqual(res[0].start, 0.5)
            self.assertEqual(res[0].end, 1.5)
            self.assertEqual(res[0].words[0]["start"], 0.5)
            self.assertEqual(res[0].words[0]["end"], 1.0)

    @patch("core.transcriber.load_whisper_model")
    @patch("core.transcriber.validate_input_file")
    @patch("faster_whisper.BatchedInferencePipeline", create=True)
    def test_transcribe_media_speed_remapping_above_one(self, mock_batched, mock_validate, mock_load):
        mock_validate.return_value = Path("input.wav")
        
        mock_word1 = MagicMock()
        mock_word1.word = "Hello"
        mock_word1.start = 1.0
        mock_word1.end = 2.0
        
        seg1 = MagicMock()
        seg1.start = 1.0
        seg1.end = 3.0
        seg1.text = "Hello"
        seg1.words = [mock_word1]
        
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.transcribe.return_value = ([seg1], None)
        mock_batched.return_value = mock_pipeline_instance
        
        with patch("core.ffmpeg_runner.run_ffmpeg") as mock_ffmpeg, \
             patch("tempfile.mkstemp") as mock_mkstemp, \
             patch("os.close") as mock_close, \
             patch("os.unlink") as mock_unlink:
            mock_mkstemp.return_value = (0, "temp.wav")
            
            opts = TranscriptionOptions(asr_audio_speed=1.5, word_timestamps=True)
            res = transcribe_media(Path("input.wav"), opts)
            
            self.assertEqual(res[0].start, 1.5)
            self.assertEqual(res[0].end, 4.5)
            self.assertEqual(res[0].words[0]["start"], 1.5)
            self.assertEqual(res[0].words[0]["end"], 3.0)

    @patch("core.transcriber.load_whisper_model")
    @patch("core.transcriber.validate_input_file")
    @patch("faster_whisper.BatchedInferencePipeline", create=True)
    def test_transcribe_media_languages(self, mock_batched, mock_validate, mock_load):
        mock_validate.return_value = Path("input.wav")
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.transcribe.return_value = ([], None)
        mock_batched.return_value = mock_pipeline_instance
        
        for lang in ["zh", "en", "vi", "ja", "ko", "ru", "fr", "es", "Tiếng Việt", "English", "auto"]:
            opts = TranscriptionOptions(language=lang)
            transcribe_media(Path("input.wav"), opts)
            
        opts = TranscriptionOptions(language="invalid_lang")
        with self.assertRaises(TranscriptionError):
            transcribe_media(Path("input.wav"), opts)
