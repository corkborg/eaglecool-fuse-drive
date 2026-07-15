from pathlib import Path
from typing import cast
import unittest
from unittest.mock import patch

from watchfiles import Change

from src.eagle_repository import EagleRepository
from src.model import EagleFile, EagleFileID, EagleFolder, EagleFolderID, eagle_file_factory


class TestClass(unittest.TestCase):

    def setUp(self) -> None:
        self.repo = EagleRepository("./test.library")
        self.repo.load()

    def test01(self):
        fs = self.repo.list_files("/folder_MF7X2TP5LYADS")
        names = [f.normalize_name() for f in fs]
        self.assertIn("pink_gif_MF7X1TY7F0LWI.gif", names)
        self.assertIn("orangepng_MF7X11V2AM3EP.png", names)

    def test_get_binary01(self):
        r = self.repo.get_binary("/folder_MF7X2TP5LYADS/orangepng_MF7X11V2AM3EP.png", 100, 0)
        self.assertEqual(len(r), 100)

    def test_get_binary02(self):
        r = self.repo.get_binary("/text_MF7X2MAQ0AQ13.txt", 100, 0)
        self.assertEqual(r, b'Eagle Cool drive\n')

    def test_search_file01(self):
        r = self.repo.search_file("/samefolder_MF7X5W2L2ZJ34/skygreen_MF7XAA9RBND19.png")
        self.assertEqual(r, "MF7XAA9RBND19")

    def testsearch_file02(self):
        r = self.repo.search_file("/aaaa_bbbb/bbbbb.png")
        self.assertIsNone(r)

    def testsearch_file03(self):
        r = self.repo.search_file("/")
        self.assertIsNone(r)

    def test_get_metadata01(self):
        """
        get metadata of file
        """
        r = self.repo.get_metadata("/folder_MF7X2TP5LYADS/orangepng_MF7X11V2AM3EP.png")
        r = cast(EagleFile, r)
        self.assertIsInstance(r, EagleFile)
        self.assertEqual(r.id, "MF7X11V2AM3EP")
        self.assertEqual(r.name, "orangepng")
        self.assertEqual(r.folders, {"MF7X2TP5LYADS"})
        self.assertEqual(r.ext, "png")
        self.assertEqual(r.size, 3026)
        self.assertEqual(r.width, 66)
        self.assertEqual(r.height, 65)

    def test_get_metadata02(self):
        """
        get metadata of folder
        """
        r = self.repo.get_metadata("/folder_MF7X2TP5LYADS")
        self.assertIsInstance(r, EagleFolder)
        self.assertEqual(r.id, "MF7X2TP5LYADS")
        self.assertEqual(r.name, "folder")

    def test_extract_image_id_from_path01(self):
        r = self.repo.extract_image_id(
            Path('images') / 'FILEID.info'
        )
        self.assertEqual(r, 'FILEID')

    def test_extract_image_id_from_path02(self):
        r = self.repo.extract_image_id(
            Path('bbbb') / 'FILEID.info'
        )
        self.assertIsNone(r)

    def test_extract_image_id_from_path03(self):
        r = self.repo.extract_image_id(
            Path('images') / 'FILEID'
        )
        self.assertIsNone(r)

    def test_extract_image_id_from_path04(self):
        r = self.repo.extract_image_id(Path('images'))
        self.assertIsNone(r)

    def test_process_changes_ignores_non_image_paths(self):
        """
        images ディレクトリ自体の変更で落ちない
        """
        self.repo.process_changes({(Change.modified, Path('images'))})
        self.repo.process_changes({(Change.modified, Path('tags.json'))})

    def test_process_changes_removes_deleted_file(self):
        """
        削除されたファイルが索引とフォルダから消える
        """
        folder = self.repo._state.indexed_folders[EagleFolderID("MF7X2TP5LYADS")]
        fake = eagle_file_factory({
            'id': 'FAKEID123', 'name': 'fake', 'ext': 'png',
            'folders': ['MF7X2TP5LYADS'],
        })
        self.repo._state.indexed_files[EagleFileID("FAKEID123")] = fake
        folder.append_file(fake)
        self.repo.process_changes({
            (Change.deleted, Path('images') / 'FAKEID123.info' / 'metadata.json')
        })
        self.assertNotIn("FAKEID123", self.repo._state.indexed_files)
        names = [f.normalize_name() for f in self.repo.list_files("/folder_MF7X2TP5LYADS")]
        self.assertNotIn("fake_FAKEID123.png", names)
        self.assertIn("orangepng_MF7X11V2AM3EP.png", names)

    def test_process_changes_reloads_folders(self):
        """
        metadata.json の変更でフォルダツリーを再構築してもファイルが残る
        """
        self.repo.process_changes({(Change.modified, Path('metadata.json'))})
        names = [f.normalize_name() for f in self.repo.list_files("/")]
        self.assertIn("text_MF7X2MAQ0AQ13.txt", names)
        names = [f.normalize_name() for f in self.repo.list_files("/folder_MF7X2TP5LYADS")]
        self.assertIn("orangepng_MF7X11V2AM3EP.png", names)

    def test_list_files_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.repo.list_files("/no_such_folder")

    def test_get_metadata_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.repo.get_metadata("/no_such_folder/no_such_file.png")


