import unittest

from src.model import eagle_file_factory


class TestEagleFile(unittest.TestCase):

    def test_normalize_name(self):
        file = eagle_file_factory({'id': 'X1', 'name': 'photo', 'ext': 'png'})
        self.assertEqual(file.normalize_name(), 'photo_X1.png')

    def test_normalize_name_without_ext(self):
        file = eagle_file_factory({'id': 'X1', 'name': 'noext'})
        self.assertEqual(file.normalize_name(), 'noext_X1')

    def test_to_stat_converts_milliseconds_to_seconds(self):
        file = eagle_file_factory({
            'id': 'X1',
            'name': 'photo',
            'ext': 'png',
            'modificationTime': 1700000000000,
            'lastModified': 1700000001000,
        })
        st = file.to_stat()
        self.assertEqual(st.st_mtime, 1700000000)
        self.assertEqual(st.st_atime, 1700000001)
        self.assertEqual(st.st_ctime, 1700000001)
