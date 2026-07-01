import os
import py_compile
import tempfile
import unittest
from pathlib import Path


class StreamlitAppTests(unittest.TestCase):
    def test_streamlit_app_py_compile(self):
        project_root = Path(__file__).resolve().parents[1]
        app_path = project_root / "streamlit_app.py"

        with tempfile.TemporaryDirectory() as tmp:
            cfile = Path(tmp) / "streamlit_app.pyc"
            py_compile.compile(str(app_path), cfile=str(cfile), doraise=True)
            self.assertTrue(cfile.is_file())

    def test_data_path_is_project_root_based_when_cwd_changes(self):
        import streamlit_app

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                self.assertTrue(streamlit_app.DATA_PATH.is_absolute())
                self.assertIn("contest_xiaoshumo", str(streamlit_app.DATA_PATH))
                self.assertEqual(streamlit_app.DATA_PATH.name, "streamlit_data.json")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
