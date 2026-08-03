from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from watchfiles import Change

from src.eagle_repository import EagleRepository, _compute_folder_effective_times
from src.model import (
    EagleFile,
    EagleFileID,
    EagleFolder,
    EagleFolderID,
    EagleRootFolderID,
    eagle_file_factory,
    eagle_folder_factory,
)


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

    def test_process_changes_ignores_non_image_paths(self):
        """
        images ディレクトリ自体の変更で落ちない
        """
        self.repo.process_changes({(Change.modified, Path('images'))})
        self.repo.process_changes({(Change.modified, Path('tags.json'))})

    def test_process_changes_removes_deleted_file_from_folder_index(self):
        """
        削除されたファイルのIDがフォルダ索引からも消える
        """
        folder_id = EagleFolderID("MF7X2TP5LYADS")
        self.repo._state.indexed_files_by_folderid[folder_id].add(EagleFileID("FAKEID123"))
        self.repo.process_changes({
            (Change.deleted, Path('images') / 'FAKEID123.info' / 'metadata.json')
        })
        self.assertNotIn(
            "FAKEID123", self.repo._state.indexed_files_by_folderid[folder_id])
        # 索引が壊れていても readdir 相当が KeyError にならないこと
        fs = self.repo.list_filenames("/folder_MF7X2TP5LYADS")
        self.assertIn("orangepng_MF7X11V2AM3EP.png", fs)

    def test_list_filenames_ignores_dangling_file_id(self):
        """
        索引に残った不明なIDを無視して一覧を返せる
        """
        folder_id = EagleFolderID("MF7X2TP5LYADS")
        self.repo._state.indexed_files_by_folderid[folder_id].add(EagleFileID("DANGLING"))
        fs = self.repo.list_filenames("/folder_MF7X2TP5LYADS")
        self.assertIn("orangepng_MF7X11V2AM3EP.png", fs)

    def test_process_changes_reloads_folders(self):
        """
        metadata.json の変更でフォルダツリーを再読込する
        """
        self.repo.process_changes({(Change.modified, Path('metadata.json'))})
        fs = self.repo.list_filenames("/")
        self.assertIn("text_MF7X2MAQ0AQ13.txt", fs)
        fs = self.repo.list_filenames("/folder_MF7X2TP5LYADS")
        self.assertIn("orangepng_MF7X11V2AM3EP.png", fs)

    def test_list_filenames_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.repo.list_filenames("/no_such_folder")

    def test_get_metadata_not_found(self):
        with self.assertRaises(FileNotFoundError):
            self.repo.get_metadata("/no_such_folder/no_such_file.png")

    def test_get_folder_time_reflects_direct_child_file(self):
        """
        フォルダ自身の modificationTime より、直下ファイルの時刻が新しければそちらを使う
        """
        folder_time = self.repo.get_folder_time(EagleFolderID("MF7X2TP5LYADS"))
        # orangepng の lastModified (1757142190311ms) がフォルダ自身の
        # modificationTime (1757142167513ms) より新しく、これが実効時刻になる
        self.assertEqual(folder_time, datetime.fromtimestamp(1757142190311 / 1000, tz=timezone.utc))

    def test_get_folder_time_propagates_through_nested_folders(self):
        """
        孫階層のファイル時刻が祖先フォルダの実効時刻にも再帰的に伝播する
        """
        sub_folder_time = self.repo.get_folder_time(EagleFolderID("MF7X4W2XB8DTM"))
        parent_folder_time = self.repo.get_folder_time(EagleFolderID("MF7X4JQBHM2E7"))
        # light blue の lastModified (1757142268882ms) は sub folder / nested_folder
        # いずれの自己の modificationTime よりも新しく、両階層に伝播するはず
        expected = datetime.fromtimestamp(1757142268882 / 1000, tz=timezone.utc)
        self.assertEqual(sub_folder_time, expected)
        self.assertEqual(parent_folder_time, expected)

    def test_get_folder_time_root_reflects_descendants(self):
        """
        ルート直下のファイル/トップレベルフォルダを再帰集約した時刻になる
        """
        root_time = self.repo.get_folder_time(EagleRootFolderID)
        # blue (root 直下ファイル) の lastModified がライブラリ全体で最も新しい
        self.assertEqual(root_time, datetime.fromtimestamp(1757142569154 / 1000, tz=timezone.utc))


class TestComputeFolderEffectiveTimes(unittest.TestCase):
    """
    _compute_folder_effective_times を、実ファイルに依存しない小さなツリーで直接検証する。
    """

    def setUp(self) -> None:
        self.fallback = datetime.fromtimestamp(0, tz=timezone.utc)
        self.tree = [eagle_folder_factory({
            'id': 'P', 'name': 'parent', 'modificationTime': 1000,
            'children': [
                {'id': 'C', 'name': 'child', 'modificationTime': 2000, 'children': []},
            ],
        })]

    def test_recurses_across_multiple_levels(self):
        file = eagle_file_factory({'id': 'F', 'name': 'f', 'modificationTime': 9000, 'lastModified': 9000})
        indexed_files = {EagleFileID('F'): file}
        files_by_folder = {EagleFolderID('C'): {EagleFileID('F')}}

        times = _compute_folder_effective_times(self.tree, indexed_files, files_by_folder, self.fallback)

        expected = datetime.fromtimestamp(9000 / 1000, tz=timezone.utc)
        self.assertEqual(times[EagleFolderID('C')], expected)
        # 孫にあたるファイルの時刻が、直下に何も持たない祖先フォルダにも伝播する
        self.assertEqual(times[EagleFolderID('P')], expected)

    def test_recomputes_from_scratch_instead_of_mutating(self):
        """
        フォルダの生の modification_time を書き換えない設計により、ファイルが
        取り除かれた後の再計算では実効時刻がフォルダ自身の時刻まで正しく戻る。
        """
        file = eagle_file_factory({'id': 'F', 'name': 'f', 'modificationTime': 9000, 'lastModified': 9000})
        indexed_files = {EagleFileID('F'): file}
        files_by_folder = {EagleFolderID('C'): {EagleFileID('F')}}
        _compute_folder_effective_times(self.tree, indexed_files, files_by_folder, self.fallback)

        # 同じ self.tree インスタンスに対して、ファイルなしで再計算する
        times_after_removal = _compute_folder_effective_times(self.tree, {}, {}, self.fallback)

        self.assertEqual(
            times_after_removal[EagleFolderID('C')],
            datetime.fromtimestamp(2000 / 1000, tz=timezone.utc))
        self.assertEqual(
            times_after_removal[EagleFolderID('P')],
            datetime.fromtimestamp(2000 / 1000, tz=timezone.utc))


