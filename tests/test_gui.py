import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from ui.main_window import (
    MainWindow, LANGUAGE_MAP, FORMAT_MAP, PLATFORM_MAP,
    DropZoneFrame, _SUPPORTED_EXTS
)

# Ensure QApplication exists for UI tests
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestGUI(unittest.TestCase):

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_ui_initial_defaults(self):
        # Default options check
        self.assertFalse(self.window.chk_merge.isChecked())
        self.assertFalse(self.window.chk_voice.isChecked())
        self.assertTrue(self.window.chk_volume.isChecked())
        self.assertTrue(self.window.chk_silence.isChecked())
        self.assertTrue(self.window.chk_social.isChecked())
        self.assertFalse(self.window.chk_sub.isChecked())

        # Output format default
        self.assertEqual(self.window.combo_out_format.currentText(), ".wav (WAV - Kh\u00f4ng n\u00e9n)")

        # Subtitle panel must be collapsed/hidden by default
        self.assertTrue(self.window.sub_section.content_panel.isHidden())

    def test_auto_sub_panel_toggles(self):
        # 1. Auto Subtitle OFF hides subtitle settings
        self.window.chk_sub.setChecked(False)
        self.assertTrue(self.window.sub_section.content_panel.isHidden())

        # 2. Auto Subtitle ON shows subtitle settings
        self.window.chk_sub.setChecked(True)
        self.assertFalse(self.window.sub_section.content_panel.isHidden())

        # Toggle back to OFF
        self.window.chk_sub.setChecked(False)
        self.assertTrue(self.window.sub_section.content_panel.isHidden())

    def test_social_platform_dropdown_visibility(self):
        # 3. Social Optimize OFF hides platform dropdown
        self.window.chk_social.setChecked(False)
        self.assertTrue(self.window.card_social.dropdown_widget.isHidden())

        # 4. Social Optimize ON shows platform dropdown
        self.window.chk_social.setChecked(True)
        self.assertFalse(self.window.card_social.dropdown_widget.isHidden())

    def test_feature_toggles_mapping(self):
        # 5. Feature toggles map correctly to pipeline options
        self.window.input_paths_list = [Path("file1.wav")]
        self.window.txt_output.setText("output_dir")
        self.window.txt_project_name.setText("proj_name")

        self.window.chk_merge.setChecked(True)
        self.window.chk_voice.setChecked(True)
        self.window.chk_volume.setChecked(False)
        self.window.chk_silence.setChecked(False)
        self.window.chk_social.setChecked(True)
        self.window.card_social.combo_platform.setCurrentText("TikTok / Instagram Reels")

        self.window.chk_sub.setChecked(True)
        self.window.combo_lang.setCurrentText("Ti\u1ebfng Anh (English)")
        self.window.combo_model.setCurrentText("medium")
        self.window.combo_speed.setCurrentText("0.9")
        self.window.combo_batch.setCurrentText("4")
        self.window.combo_format.setCurrentText("vertical")
        self.window.combo_lines.setCurrentText("3")

        called_options = self.window.get_pipeline_options()

        self.assertTrue(called_options.merge_first)
        self.assertTrue(called_options.enable_voice_cleanup)
        self.assertFalse(called_options.enable_volume_leveling)
        self.assertFalse(called_options.enable_silence_shortening)
        self.assertTrue(called_options.enable_social_optimize)
        self.assertEqual(called_options.social_platform, "tiktok_instagram")
        self.assertTrue(called_options.enable_transcription)
        self.assertEqual(called_options.language, "en")
        self.assertEqual(called_options.whisper_model, "medium")
        self.assertEqual(called_options.asr_audio_speed, 0.9)
        self.assertEqual(called_options.batch_size, 4)
        self.assertEqual(called_options.target_video_format, "vertical")
        self.assertEqual(called_options.subtitle_lines, 3)

    def test_language_dropdown_mappings(self):
        # 6. Language labels map correctly to backend codes
        for i in range(self.window.combo_lang.count()):
            label = self.window.combo_lang.itemText(i)
            self.assertIn(label, LANGUAGE_MAP)
            code = LANGUAGE_MAP[label]
            if label == "Tự động nhận diện":
                self.assertIsNone(code)
            else:
                self.assertIn(code, ["zh", "en", "vi", "ja", "ko", "ru", "fr", "es"])

    def test_output_format_mapping(self):
        # 7. Output format dropdown maps correctly
        self.window.input_paths_list = [Path("file1.wav")]
        self.window.txt_output.setText("output_dir")
        self.window.txt_project_name.setText("proj_name")

        for display_text, format_code in FORMAT_MAP.items():
            self.window.combo_out_format.setCurrentText(display_text)
            called_options = self.window.get_pipeline_options()
            self.assertEqual(called_options.output_format, format_code)

    def test_file_ordering_preserves_and_changes(self):
        # 8. File ordering logic preserves selected order
        p1 = Path("first.wav")
        p2 = Path("second.wav")
        p3 = Path("third.wav")
        self.window.input_paths_list = [p1, p2, p3]

        # Sync to table
        self.window.update_file_table()
        self.assertEqual(self.window.table.rowCount(), 3)
        self.assertEqual(self.window.table.item(0, 1).text(), "\U0001f3b5  first.wav")
        self.assertEqual(self.window.table.item(1, 1).text(), "\U0001f3b5  second.wav")
        self.assertEqual(self.window.table.item(2, 1).text(), "\U0001f3b5  third.wav")

        # 9. Move up/down changes order
        self.window.table.setCurrentCell(1, 1)
        self.window.move_up()
        self.assertEqual(self.window.input_paths_list, [p2, p1, p3])
        self.assertEqual(self.window.table.item(0, 1).text(), "\U0001f3b5  second.wav")

        self.window.table.setCurrentCell(1, 1)
        self.window.move_down()
        self.assertEqual(self.window.input_paths_list, [p2, p3, p1])
        self.assertEqual(self.window.table.item(2, 1).text(), "\U0001f3b5  first.wav")

        # Test handle_row_move (simulating drag-and-drop row move)
        self.window.handle_row_move(2, 0)
        self.assertEqual(self.window.input_paths_list, [p1, p2, p3])
        self.assertEqual(self.window.table.item(0, 1).text(), "\U0001f3b5  first.wav")

    def test_clear_log(self):
        # 10. Clear log clears log
        self.window.txt_logs.setText("Sample Log Message\nAnother line")
        self.window.clear_logs()
        self.assertEqual(self.window.txt_logs.toPlainText(), "")

    @patch("PySide6.QtWidgets.QMessageBox.critical")
    def test_start_validation_missing_inputs(self, mock_critical):
        # 11. Start validation fails clearly if input files are missing
        self.window.input_paths_list = []
        self.window.txt_output.setText("output_dir")
        self.window.txt_project_name.setText("proj_name")

        self.window.start_processing()
        mock_critical.assert_called_once()
        self.assertIn("đầu vào trống", mock_critical.call_args[0][2])

    @patch("PySide6.QtWidgets.QMessageBox.critical")
    def test_start_validation_missing_output(self, mock_critical):
        # 12. Start validation fails clearly if output folder is missing
        self.window.input_paths_list = [Path("file1.wav")]
        self.window.txt_output.setText("")
        self.window.txt_project_name.setText("proj_name")

        self.window.start_processing()
        mock_critical.assert_called_once()
        self.assertIn("thư mục đầu ra", mock_critical.call_args[0][2])

    @patch("PySide6.QtWidgets.QMessageBox.critical")
    def test_start_validation_missing_project_name(self, mock_critical):
        # 13. Start validation fails clearly if project name is missing
        self.window.input_paths_list = [Path("file1.wav")]
        self.window.txt_output.setText("output_dir")
        self.window.txt_project_name.setText("")

        self.window.start_processing()
        mock_critical.assert_called_once()
        self.assertIn("Tên dự án", mock_critical.call_args[0][2])

    # ── New tests for Section 1 & 2 enhancements ─────────────────────────────

    def test_section1_controls_exist(self):
        """Section 1 must have all required controls."""
        self.assertIsNotNone(self.window.btn_add_files)
        self.assertIsNotNone(self.window.btn_remove_selected)
        self.assertIsNotNone(self.window.btn_move_up)
        self.assertIsNotNone(self.window.btn_move_down)
        self.assertEqual(self.window.table.columnCount(), 5)
        self.assertIsNotNone(self.window.drop_zone)
        self.assertIsInstance(self.window.drop_zone, DropZoneFrame)
        self.assertIsNotNone(self.window.lbl_sum_count)
        self.assertIsNotNone(self.window.lbl_sum_duration)
        self.assertIsNotNone(self.window.lbl_sum_size)

    def test_section2_controls_exist(self):
        """Section 2 must have all required controls."""
        self.assertIsNotNone(self.window.txt_output)
        self.assertIsNotNone(self.window.btn_browse_output)
        self.assertIsNotNone(self.window.txt_project_name)
        self.assertIsNotNone(self.window.combo_out_format)
        self.assertEqual(self.window.txt_project_name.text(), "audio_project")

    def test_add_files_from_paths_deduplication(self):
        """add_files_from_paths should add new files and ignore duplicates."""
        p1 = Path("audio_a.wav")
        p2 = Path("audio_b.mp3")
        self.window.input_paths_list = [p1]

        self.window.add_files_from_paths([p1, p2])

        self.assertEqual(len(self.window.input_paths_list), 2)
        self.assertIn(p1, self.window.input_paths_list)
        self.assertIn(p2, self.window.input_paths_list)

    def test_add_files_from_paths_updates_table(self):
        """add_files_from_paths must update the file table."""
        paths = [Path("drop_a.wav"), Path("drop_b.mp3")]
        self.window.add_files_from_paths(paths)

        self.assertEqual(len(self.window.input_paths_list), 2)
        self.assertEqual(self.window.table.rowCount(), 2)

    def test_add_files_from_paths_sets_project_name(self):
        """add_files_from_paths auto-sets project name when field is default."""
        self.window.txt_project_name.setText("audio_project")
        self.window.add_files_from_paths([Path("my_recording.wav")])

        self.assertEqual(self.window.txt_project_name.text(), "my_recording")

    def test_add_files_from_paths_preserves_custom_project_name(self):
        """add_files_from_paths must NOT overwrite a custom project name."""
        self.window.txt_project_name.setText("my_custom_project")
        self.window.add_files_from_paths([Path("some_file.wav")])

        self.assertEqual(self.window.txt_project_name.text(), "my_custom_project")

    def test_drop_zone_supported_extensions(self):
        """_SUPPORTED_EXTS must cover all expected audio/video types."""
        expected = {".wav", ".mp3", ".m4a", ".flac", ".ogg",
                    ".mp4", ".mkv", ".avi", ".mov"}
        self.assertEqual(_SUPPORTED_EXTS, expected)

    def test_output_format_dropdown_all_options(self):
        """Output format dropdown must contain all 5 expected entries."""
        items = [self.window.combo_out_format.itemText(i)
                 for i in range(self.window.combo_out_format.count())]
        self.assertIn(".wav (WAV - Kh\u00f4ng n\u00e9n)", items)
        self.assertIn(".mp3 (MP3 - N\u00e9n ph\u1ed5 bi\u1ebfn)", items)
        self.assertIn(".m4a (M4A - AAC)", items)
        self.assertIn(".flac (FLAC - Kh\u00f4ng n\u00e9n)", items)
        self.assertIn(".ogg (OGG - Vorbis)", items)
        self.assertEqual(len(items), 5)


if __name__ == "__main__":
    unittest.main()
