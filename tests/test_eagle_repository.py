from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock, Mock

from src.eagle_repository import EagleRepository
from src.model import EagleFile, EagleFolder, EagleFolderID


class TestClass(unittest.TestCase):

    def setUp(self) -> None:
        self.repo = EagleRepository("./test.library")
        self.repo.load()

    def test01(self):
        fs = self.repo.list_filenames("/folder_MF7X2TP5LYADS")
        self.assertIn("pink_gif_MF7X1TY7F0LWI.gif", fs)
        self.assertIn("orangepng_MF7X11V2AM3EP.png", fs)

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


