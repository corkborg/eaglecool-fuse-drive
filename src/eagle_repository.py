
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


def _make_root_folder(sub_folders: list[EagleFolder] | None = None,
                      modification_time: datetime | None = None) -> EagleFolder:
    """
    ライブラリ全体を包む合成ルートフォルダを作る
    """
    return EagleFolder(
        id=EagleRootFolderID,
        name='root',
        sub_folders=sub_folders if sub_folders is not None else [],
        raw_modification_time=modification_time or datetime.fromtimestamp(0, tz=timezone.utc),
        files=[],
    )


@dataclass(frozen=True)
class RepositoryState:
    """
    ライブラリ全体のスナップショット。

    監視スレッドは新しいインスタンスを組み立ててから self._state を
    一括で差し替える。読み取り側は最初に参照をローカルに取り、
    その中だけを見ることでロックなしに一貫したデータを扱える。
    """
    root_folder: EagleFolder = field(default_factory=_make_root_folder)
    indexed_folders: dict[EagleFolderID, EagleFolder] = field(default_factory=dict)
    indexed_files: dict[EagleFileID, EagleFile] = field(default_factory=dict)


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
        indexed_files = self._read_files()
        self._state = self._build_state(indexed_files)

    def list_files(self, path='/') -> list[EagleFile | EagleFolder]:
        """
        list files and folders in folder
        """
        state = self._state
        folder_id = state.root_folder.solve_folder(path)
        if folder_id is None:
            raise FileNotFoundError(f"Folder not found: {path}")
        folder = state.indexed_folders[folder_id]
        return [*folder.sub_folders, *folder.files]

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
        return state.root_folder.solve_file(path)

    def search_folder(self, path, state: RepositoryState | None = None) -> EagleFolderID | None:
        if state is None:
            state = self._state
        return state.root_folder.solve_folder(path)

    def _build_state(self, indexed_files: dict[EagleFileID, EagleFile]) -> RepositoryState:
        """
        フォルダツリーを構築し、各ファイルを所属フォルダにぶら下げて
        新しいスナップショットを作る
        """
        root_folder, indexed_folders = self._read_folders()

        for file in indexed_files.values():
            for folder_id in self._file_folder_ids(file):
                folder = indexed_folders.get(folder_id)
                if folder is None:
                    logger.warning("Folder not found: %s for file %s", folder_id, file.id)
                    continue
                folder.append_file(file)

        return RepositoryState(
            root_folder=root_folder,
            indexed_folders=indexed_folders,
            indexed_files=indexed_files,
        )

    def _read_folders(self) -> tuple[EagleFolder, dict[EagleFolderID, EagleFolder]]:
        """
        read folder tree from metadata.json
        """
        with open(self.library_path / "metadata.json", "r") as f:
            obj = json.load(f)

        root_folder = _make_root_folder(
            sub_folders=[eagle_folder_factory(folder) for folder in obj['folders']],
            modification_time=datetime.fromtimestamp(obj.get('modificationTime', 0) / 1000, tz=timezone.utc),
        )

        indexed_folders: dict[EagleFolderID, EagleFolder] = {}
        def index_folder(folder: EagleFolder):
            indexed_folders[folder.id] = folder
            for child in folder.sub_folders:
                index_folder(child)
        index_folder(root_folder)
        return root_folder, indexed_folders

    def _read_files(self) -> dict[EagleFileID, EagleFile]:
        """
        read all file metadata from images directory
        """
        indexed_files: dict[EagleFileID, EagleFile] = {}
        for f in (self.library_path / 'images').iterdir():
            if f.suffix != '.info' or not f.is_dir():
                continue

            try:
                with open(f / 'metadata.json', 'r') as jf:
                    obj = json.load(jf)
            except Exception:
                logger.error("Skip broken metadata file: %s", f, exc_info=True)
                continue

            file = eagle_file_factory(obj)

            if file.is_deleted:
                continue

            indexed_files[file.id] = file
        return indexed_files

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
        folders_changed = False
        for _, change_path in changes:
            change_path = Path(change_path)
            image_id = self.extract_image_id(change_path)
            if image_id is not None:
                image_ids.add(EagleFileID(image_id))
            elif change_path == Path('metadata.json'):
                folders_changed = True

        if not image_ids and not folders_changed:
            return

        # 変更のあったファイルだけディスクから読み直し、
        # フォルダグラフは丸ごと作り直してスナップショットを差し替える
        indexed_files = dict(state.indexed_files)
        for image_id in image_ids:
            self._apply_file_update(image_id, indexed_files)

        self._state = self._build_state(indexed_files)

    def _apply_file_update(self, file_id: EagleFileID,
                           indexed_files: dict[EagleFileID, EagleFile]):
        """
        Update information related to changed file.
        """
        image_metadata = self.create_image_metadata_path(file_id)

        if not image_metadata.exists():
            indexed_files.pop(file_id, None)
            return

        try:
            with open(image_metadata, 'r') as f:
                obj = json.load(f)
        except Exception:
            logger.error("Skip broken metadata file: %s", image_metadata, exc_info=True)
            return

        file = eagle_file_factory(obj)

        if file.is_deleted:
            indexed_files.pop(file.id, None)
            return

        indexed_files[file.id] = file
