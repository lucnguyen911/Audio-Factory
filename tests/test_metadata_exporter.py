import unittest
import tempfile
import json
import csv
from pathlib import Path

from core.metadata_exporter import (
    MetadataExportError,
    AudioChunkMetadata,
    ProjectMetadata,
    normalize_chunk_metadata,
    project_metadata_to_dict,
    export_project_json,
    export_chunks_json,
    export_chunks_csv,
    build_project_metadata
)

class TestMetadataExporter(unittest.TestCase):

    def test_normalize_chunk_metadata_dataclass(self):
        chunks = [AudioChunkMetadata(index=1, text="Hello", start=0.0, end=2.0, file="001.wav")]
        norm = normalize_chunk_metadata(chunks)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0].index, 1)
        self.assertEqual(norm[0].text, "Hello")

    def test_normalize_chunk_metadata_dict(self):
        chunks = [{"index": 2, "text": "  Chào các bạn  ", "start": 1.0, "end": 3.5, "file": "002.wav", "source_segment_indexes": [1, 2]}]
        norm = normalize_chunk_metadata(chunks)
        self.assertEqual(len(norm), 1)
        self.assertEqual(norm[0].index, 2)
        self.assertEqual(norm[0].text, "Chào các bạn")
        self.assertEqual(norm[0].source_segment_indexes, [1, 2])

    def test_normalize_chunk_metadata_invalid(self):
        with self.assertRaises(MetadataExportError):
            normalize_chunk_metadata([{"index": 0, "text": "Hello", "start": 0.0, "end": 2.0, "file": "001.wav"}])
        with self.assertRaises(MetadataExportError):
            normalize_chunk_metadata([{"index": 1, "text": "Hello", "start": 2.0, "end": 2.0, "file": "001.wav"}])
        with self.assertRaises(MetadataExportError):
            normalize_chunk_metadata([{"index": 1, "text": "   ", "start": 0.0, "end": 2.0, "file": "001.wav"}])
        with self.assertRaises(MetadataExportError):
            normalize_chunk_metadata([{"index": 1, "text": "Hello", "start": 0.0, "end": 2.0, "file": "   "}])

    def test_project_metadata_to_dict(self):
        chunk = AudioChunkMetadata(index=1, text="Hi", start=0.0, end=1.0, file="001.wav")
        meta = ProjectMetadata(
            project_name="TestProj",
            input_files=["in.mp3"],
            output_dir="out",
            created_at="2026-06-16T00:00:00Z",
            processing_options={"preset": "natural"},
            chunks=[chunk],
            subtitle_files={"srt": "out/sub.srt"},
            merged_file="out/merged.wav",
            cleaned_file=None
        )
        
        data = project_metadata_to_dict(meta)
        self.assertEqual(data["project_name"], "TestProj")
        self.assertEqual(data["chunks"][0]["text"], "Hi")
        self.assertEqual(data["subtitle_files"]["srt"], "out/sub.srt")

    def test_export_project_json_vietnamese(self):
        chunk = AudioChunkMetadata(index=1, text="Tiếng Việt có dấu", start=0.0, end=1.0, file="001.wav")
        meta = ProjectMetadata(
            project_name="Dự án test",
            input_files=["in.mp3"],
            output_dir="out",
            created_at="2026-06-16T00:00:00Z",
            processing_options={},
            chunks=[chunk]
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "project.json"
            export_project_json(meta, out_file)
            
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Tiếng Việt có dấu", content)
            self.assertIn("Dự án test", content)

    def test_export_chunks_json(self):
        chunks = [{"index": 1, "text": "Hello", "start": 0.0, "end": 2.0, "file": "001.wav"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "chunks.json"
            export_chunks_json(chunks, out_file)
            
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            parsed = json.loads(content)
            self.assertEqual(parsed[0]["text"], "Hello")

    def test_export_chunks_csv(self):
        chunks = [{"index": 1, "text": "Tiếng Việt", "start": 1.5, "end": 4.0, "file": "001.wav", "source_segment_indexes": [1]}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "chunks.csv"
            export_chunks_csv(chunks, out_file)
            
            self.assertTrue(out_file.exists())
            
            with open(out_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ["index", "start", "end", "duration", "text", "file", "source_segment_indexes"])
            self.assertEqual(rows[1][0], "1")
            self.assertEqual(rows[1][1], "1.5")
            self.assertEqual(rows[1][2], "4.0")
            self.assertEqual(rows[1][3], "2.5")
            self.assertEqual(rows[1][4], "Tiếng Việt")
            self.assertEqual(rows[1][5], "001.wav")
            self.assertEqual(rows[1][6], "[1]")

    def test_build_project_metadata(self):
        chunks = [{"index": 1, "text": "Hello", "start": 0.0, "end": 1.0, "file": "001.wav"}]
        meta = build_project_metadata(
            project_name="MyProj",
            input_files=[Path("in1.wav"), "in2.mp3"],
            output_dir=Path("out"),
            chunks=chunks,
            processing_options={"level": True},
            subtitle_files={"srt": Path("out/sub.srt")}
        )
        
        self.assertEqual(meta.project_name, "MyProj")
        self.assertEqual(meta.input_files, ["in1.wav", "in2.mp3"])
        self.assertEqual(meta.output_dir, "out")
        self.assertGreater(len(meta.created_at), 0)
        self.assertEqual(meta.processing_options, {"level": True})
        self.assertEqual(meta.chunks[0].text, "Hello")
        self.assertEqual(meta.subtitle_files["srt"], "out/sub.srt")
