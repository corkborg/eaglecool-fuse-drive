
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta, timezone
from watchfiles import watch, Change

from src.model import EagleFile, EagleFileID, EagleFolder, EagleFolderID, EagleRootFolderID, eagle_file_factory, eagle_folder_factory

logger = logging.getLogger("eagle")

# 監視スレッドがクラッシュした際に再起動するまでの秒数
WATCH_RETRY_INTERVAL = 5


@dataclass(frozen=True)
class RepositoryState:
    """
    ライブラリ全体のスナップショット。

    監視スレッドは新しいインスタンスを組み立ててから self._state を
    一括で差し替える。読み取り側は最初に参照をローカルに取り、
    その中だけを見ることでロックなしに一貫したデータを扱える。
    """
    folder_tree: list[EagleFolder] = field(default_factory=list)
    indexed_folders: dict[EagleFolderID, EagleFolder] = field(default_factory=dict)
    indexed_files: dict[EagleFileID, EagleFile] = field(default_factory=dict)
    indexed_files_by_folderid: dict[EagleFolderID, set[EagleFileID]] = field(default_factory=dict)
    folder_effective_time: dict[EagleFolderID, datetime] = field(default_factory=dict)


def _compute_folder_effective_times(
    folder_tree: list[EagleFolder],
    indexed_files: dict[EagleFileID, EagleFile],
    files_by_folder: dict[EagleFolderID, set[EagleFileID]],
    fallback: datetime,
) -> dict[EagleFolderID, datetime]:
    """
    フォルダごとに、自身と配下のファイル・サブフォルダを再帰的に集約した実効時刻を計算する。
    EagleRootFolderID には、トップレベルのフォルダとルート直下のファイルを集約した値が入る。
    """
    times: dict[EagleFolderID, datetime] = {}

    def folder_times(file_ids: 'set[EagleFileID] | tuple[()]') -> list[datetime]:
        result = []
        for file_id in file_ids:
            file = indexed_files.get(file_id)
            if file is not None:
                result.append(file.modification_time)
                result.append(file.last_modified)
        return result

    def visit(folder: EagleFolder) -> datetime:
        candidates = [folder.modification_time]
        candidates.extend(folder_times(files_by_folder.get(folder.id, ())))
        for child in folder.children:
            candidates.append(visit(child))
        effective = max(candidates)
        times[folder.id] = effective
        return effective

    root_candidates: list[datetime] = []
    for folder in folder_tree:
        root_candidates.append(visit(folder))
    root_candidates.extend(folder_times(files_by_folder.get(EagleRootFolderID, ())))
    times[EagleRootFolderID] = max(root_candidates) if root_candidates else fallback
    return times


class EagleRepository:

    def __init__(self, library_path: Path | str):
        """
        Eagle library repository
        :param library_path: Path to Eagle library.
        """
        self.library_path = Path(library_path)
        self._state = RepositoryState()

        # Last full refresh time
        self.latest_refresh_time = datetime.now()

        # Event to stop monitoring
        self.stop_event = threading.Event()
        self._watch_thread = threading.Thread(
            target=self._run, name="eagle-watchfiles", daemon=True)

    def start(self):
        """
        start watching library changes
        """
        self._watch_thread.start()

    def close(self):
        self.stop_event.set()
        if self._watch_thread.is_alive():
            self._watch_thread.join(timeout=WATCH_RETRY_INTERVAL * 2)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self._watchfiles()
            except Exception:
                logger.exception(
                    "File watcher crashed. Restarting in %s seconds", WATCH_RETRY_INTERVAL)
                if self.stop_event.wait(WATCH_RETRY_INTERVAL):
                    break

    def load(self):
        """
        load metadata from Eagle library
        """
        self.latest_refresh_time = datetime.now()
        folder_tree, indexed_folders = self._read_folders()
        indexed_files, files_by_folder = self._read_files()
        folder_effective_time = _compute_folder_effective_times(
            folder_tree, indexed_files, files_by_folder, datetime.now(timezone.utc))
        self._state = RepositoryState(
            folder_tree=folder_tree,
            indexed_folders=indexed_folders,
            indexed_files=indexed_files,
            indexed_files_by_folderid=files_by_folder,
            folder_effective_time=folder_effective_time,
        )

    def list_filenames(self, path='/'):
        """
        list filenames in folder
        """
        state = self._state
        if path == '/':
            folder_id = EagleRootFolderID
            child_folders = state.folder_tree
        else:
            folder_id = self.search_folder(path, state)
            if folder_id is None:
                raise FileNotFoundError(f"Folder not found: {path}")
            child_folders = state.indexed_folders[folder_id].children

        files = [folder.normalize_name() for folder in child_folders]
        for file_id in state.indexed_files_by_folderid.get(folder_id, ()):
            file = state.indexed_files.get(file_id)
            if file is None:
                continue
            files.append(file.normalize_name())
        return files

    def get_metadata(self, path: str) -> EagleFile | EagleFolder:
        """
        get metadata of file or folder
        """
        state = self._state
        file_id = self.search_file(path, state)

        if file_id is None:
            folder_id = self.search_folder(path, state)
            if folder_id is None:
                raise FileNotFoundError(f"File not found: {path}")
            return state.indexed_folders[folder_id]
        return state.indexed_files[file_id]

    def get_folder_time(self, folder_id: EagleFolderID) -> datetime:
        """
        get effective modification time of a folder (or the root, via EagleRootFolderID),
        aggregated recursively from its descendant files and subfolders
        """
        return self._state.folder_effective_time[folder_id]

    def get_binary(self, path: str, size, offset) -> bytes:
        """
        get binary data of file
        """
        state = self._state
        file_id = self.search_file(path, state)

        if file_id is None:
            raise FileNotFoundError(f"File not found: {path}")

        file = state.indexed_files[file_id]
        image_path = self.get_file_path(file)

        with open(image_path, 'rb') as f:
            f.seek(offset)
            return f.read(size)

    def get_file_path(self, file: EagleFile) -> Path:
        """
        get file path of file
        """
        if file.ext is None:
            return self.library_path / 'images' / file.folder_name() / f'{file.name}'
        return self.library_path / 'images' / file.folder_name() / f'{file.name}.{file.ext}'

    def search_file(self, path: str, state: RepositoryState | None = None) -> EagleFileID | None:
        """
        Searching for files in the Eagle library
        """
        if state is None:
            state = self._state
        if path == '/':
            return None
        path_parts = str(path[1:]).split('/')
        file_name = path_parts[-1]
        folder_path = '/' + '/'.join(path_parts[:-1])
        folder_id = self.search_folder(folder_path, state)
        if folder_id is None:
            return None
        for file_id in state.indexed_files_by_folderid.get(folder_id, ()):
            file = state.indexed_files.get(file_id)
            if file is not None and file.normalize_name() == file_name:
                return file.id
        return None

    def search_folder(self, path, state: RepositoryState | None = None) -> EagleFolderID | None:
        if state is None:
            state = self._state
        if path == '/':
            return EagleRootFolderID
        def inner_search_path(folders: list[EagleFolder], path_parts) -> EagleFolderID | None:
            part = path_parts[0]
            for folder in folders:
                if folder.normalize_name() == part:
                    if len(path_parts) == 1:
                        return folder.id
                    else:
                        return inner_search_path(folder.children, path_parts[1:])
            return None
        path_parts = str(path[1:]).split('/')
        return inner_search_path(state.folder_tree, path_parts)

    def _read_folders(self) -> tuple[list[EagleFolder], dict[EagleFolderID, EagleFolder]]:
        """
        read folder tree from metadata.json
        """
        with open(self.library_path / "metadata.json", "r") as f:
            obj = json.load(f)

        folder_tree = [eagle_folder_factory(folder) for folder in obj['folders']]

        indexed_folders: dict[EagleFolderID, EagleFolder] = {}
        def index_folder(folder: EagleFolder):
            indexed_folders[folder.id] = folder
            for child in folder.children:
                index_folder(child)
        for folder in folder_tree:
            index_folder(folder)
        return folder_tree, indexed_folders

    def _read_files(self) -> tuple[dict[EagleFileID, EagleFile], dict[EagleFolderID, set[EagleFileID]]]:
        """
        read all file metadata from images directory
        """
        indexed_files: dict[EagleFileID, EagleFile] = {}
        files_by_folder: dict[EagleFolderID, set[EagleFileID]] = {}
        for f in (self.library_path / 'images').iterdir():
            if f.suffix != '.info' or not f.is_dir():
                continue

            try:
                with open(f / 'metadata.json', 'r') as jf:
                    obj = json.load(jf)
                file = eagle_file_factory(obj)
            except Exception:
                logger.error("Skip broken metadata file: %s", f, exc_info=True)
                continue

            if file.is_deleted:
                continue

            indexed_files[file.id] = file
            for fid in self._file_folder_ids(file):
                files_by_folder.setdefault(fid, set()).add(file.id)
        return indexed_files, files_by_folder

    @staticmethod
    def _file_folder_ids(file: EagleFile) -> set[EagleFolderID]:
        """
        folders the file belongs to. Files without folders belong to root.
        """
        return file.folders if file.folders else {EagleRootFolderID}

    def _watchfiles(self):
        for changes in watch(self.library_path, step=200, stop_event=self.stop_event):
            # Convert abs path to rel path
            new_changes = []
            for change in changes:
                relpath = Path(change[1]).relative_to(self.library_path.absolute())
                new_change = (change[0], relpath)
                new_changes.append(new_change)

            logger.debug("changes: %s", new_changes)
            self.process_changes(set(new_changes))

            # 以前の実行から時間が経っている場合再度全ロードを行う
            if datetime.now() - self.latest_refresh_time > timedelta(minutes=10):
                self.load()

    def create_image_metadata_path(self, file_id: EagleFileID):
        return self.library_path / 'images' / f'{file_id}.info' / 'metadata.json'

    def extract_image_id(self, rel_path: Path) -> str | None:
        """
        extract image id from relative path.
        """
        if rel_path.parts[0] != 'images':
            return None
        if len(rel_path.parts) >= 2 and rel_path.parts[1].endswith('.info'):
            return rel_path.parts[1].replace('.info', '')
        return None

    def process_changes(self, changes: set[tuple[Change, Path]]):
        state = self._state

        # Aggregate changes
        image_ids: set[EagleFileID] = set()
        reload_folders = False
        for _, change_path in changes:
            change_path = Path(change_path)
            image_id = self.extract_image_id(change_path)
            if image_id is not None:
                image_ids.add(EagleFileID(image_id))
            elif change_path == Path('metadata.json'):
                reload_folders = True

        if not image_ids and not reload_folders:
            return

        indexed_files = dict(state.indexed_files)
        files_by_folder = {fid: set(ids) for fid, ids in state.indexed_files_by_folderid.items()}

        for image_id in image_ids:
            self._apply_file_update(image_id, indexed_files, files_by_folder)

        if reload_folders:
            folder_tree, indexed_folders = self._read_folders()
        else:
            folder_tree, indexed_folders = state.folder_tree, state.indexed_folders

        folder_effective_time = _compute_folder_effective_times(
            folder_tree, indexed_files, files_by_folder, datetime.now(timezone.utc))

        self._state = RepositoryState(
            folder_tree=folder_tree,
            indexed_folders=indexed_folders,
            indexed_files=indexed_files,
            indexed_files_by_folderid=files_by_folder,
            folder_effective_time=folder_effective_time,
        )

    def _apply_file_update(self, file_id: EagleFileID,
                           indexed_files: dict[EagleFileID, EagleFile],
                           files_by_folder: dict[EagleFolderID, set[EagleFileID]]):
        """
        Update information related to changed file.
        """
        image_metadata = self.create_image_metadata_path(file_id)

        if not image_metadata.exists():
            self._remove_file(file_id, indexed_files, files_by_folder)
            return

        try:
            with open(image_metadata, 'r') as f:
                obj = json.load(f)
            file = eagle_file_factory(obj)
        except Exception:
            logger.error("Skip broken metadata file: %s", image_metadata, exc_info=True)
            return

        if file.is_deleted:
            self._remove_file(file.id, indexed_files, files_by_folder)
            return

        # フォルダ移動に追従できるよう、旧所属を消してから登録し直す
        self._remove_file(file.id, indexed_files, files_by_folder)
        indexed_files[file.id] = file
        for fid in self._file_folder_ids(file):
            files_by_folder.setdefault(fid, set()).add(file.id)

    @staticmethod
    def _remove_file(file_id: EagleFileID,
                     indexed_files: dict[EagleFileID, EagleFile],
                     files_by_folder: dict[EagleFolderID, set[EagleFileID]]):
        indexed_files.pop(file_id, None)
        for ids in files_by_folder.values():
            ids.discard(file_id)
