from datetime import datetime
import json
import logging
from queue import Queue
import threading
from collections import defaultdict
from pathlib import Path
from watchfiles import watch, Change

from src.model import EagleFile, EagleFileID, EagleFolder, EagleFolderID, EagleRootFolderID, eagle_file_factory

logger = logging.getLogger("eagle")


class EagleRepository(threading.Thread):

    def __init__(self, library_path: Path | str):
        """
        Eagle library repository
        :param library_path: Path to Eagle library.
        """
        threading.Thread.__init__(self)

        self.library_path = Path(library_path)
        self.folders: list[EagleFolder] = []
        self.indexed_folders: dict[EagleFolderID, EagleFolder] = {}
        self.indexed_files: dict[EagleFileID, EagleFile] = {}

        self.indexed_files_by_folderid: defaultdict[EagleFolderID, set[EagleFileID]] = defaultdict(set)

        # Event to stop monitoring
        self.stop_event = threading.Event()

    def close(self):
        self.stop_event.set()

    def run(self):
        try:
            self.watchfiles()
        except Exception as e:
            logger.exception(e)

    def load(self):
        """
        load metadata from Eagle library
        """
        self.load_folders()
        self.load_files()

    def list_filenames(self, path = '/'):
        """
        list filenames in folder
        """
        files = []
        if path == '/':
            for folder in self.folders:
                files.append(folder.normalize_name())
            folder_id = EagleRootFolderID
        else:
            folder_id = self.search_folder(path)
            if folder_id is None:
                raise Exception(f"Folder not found: {path}")

            for folder in self.indexed_folders[folder_id].children:
                files.append(folder.normalize_name())

        delete_list = []
        for file_id in self.indexed_files_by_folderid.get(folder_id, []):
            file = self.indexed_files[file_id]

            if folder_id not in file.folders or file.is_deleted:
                delete_list.append((folder_id, file_id))
                continue

            files.append(file.normalize_name())

        for delete in delete_list:
            self.indexed_files_by_folderid[delete[0]] -= {delete[1]}
        return files

    def get_metadata(self, path: str) -> EagleFile | EagleFolder:
        """
        get metadata of file or folder
        """
        file_id = self.search_file(path)

        if file_id is None:
            folder_id = self.search_folder(path)
            if folder_id is None:
                raise Exception(f"File not found: {path}")
            return self.indexed_folders[folder_id]
        file = self.indexed_files[file_id]
        return file

    def get_binary(self, path: str, size, offset) -> bytes:
        """
        get binary data of file
        """
        file_id = self.search_file(path)

        if file_id is None:
            raise Exception(f"File not found: {path}")

        file = self.indexed_files[file_id]
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

    def load_folders(self):
        """
        load folders
        """
        with open(self.library_path / "metadata.json", "r") as f:
            obj = json.load(f)

        def parse_folder(folder_obj) -> EagleFolder:
            return EagleFolder(
                id=folder_obj['id'],
                name=folder_obj['name'],
                children=[parse_folder(child) for child in folder_obj.get('children', [])],
                modification_time=folder_obj.get('modificationTime', 0)
            )

        self.folders = [parse_folder(folder) for folder in obj['folders']]

        def index_folder(folder: EagleFolder):
            self.indexed_folders[folder.id] = folder
            for child in folder.children:
                index_folder(child)
        for folder in self.folders:
            index_folder(folder)

    def load_files(self):
        """
        load files
        """
        for f in (self.library_path / 'images').iterdir():
            if f.suffix != '.info':
                continue

            if not f.exists():
                logger.info(f"Skip missing metadata file: {f}")
                continue

            try:
                with open(f / 'metadata.json', 'r') as jf:
                    obj = json.load(jf)
            except Exception as e:
                logger.error(f"Skip broken metadata file: {f}")
                continue

            file = eagle_file_factory(obj)

            if file.is_deleted:
                continue

            self.indexed_files[file.id] = file
            if len(file.folders) == 0:
                self.indexed_files_by_folderid[EagleRootFolderID] |= {file.id}
            else:
                for fid in file.folders:
                    if fid is None:
                        continue
                    self.indexed_files_by_folderid[fid] |= {file.id}

    def search_file(self, path: str) -> EagleFileID | None:
        """
        Searching for files in the Eagle library
        """
        if path == '/':
            return None
        path_parts = str(path[1:]).split('/')
        file_name = path_parts[-1]
        folder_path = '/' + '/'.join(path_parts[:-1])
        folder_id = self.search_folder(folder_path)
        if folder_id is None:
            return None
        for file_id in self.indexed_files_by_folderid.get(folder_id, []):
            file = self.indexed_files[file_id]
            if file.normalize_name() == file_name:
                return file.id
        return None

    def search_folder(self, path):
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
        return inner_search_path(self.folders, path_parts)

    def watchfiles(self):
        for changes in watch(self.library_path, step=200, stop_event=self.stop_event):
            # Convert abs path to rel path
            new_changes = []
            for change in changes:
                relpath = Path(change[1]).relative_to(self.library_path.absolute())
                new_change = (change[0], relpath)
                new_changes.append(new_change)

            logger.debug("changes: %s", new_changes)
            self.process_changes(set(new_changes))

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

    def process_changes(self, changes: set[tuple[Change, str]]):
        image_ids = []
        other_change_paths = []

        # Aggregate changes
        for change in changes:
            change_path = Path(change[1])
            if change_path.parts[0] == 'images':
                file_id = EagleFileID(change_path.parts[1].replace('.info', ''))
                image_ids.append(file_id)
            else:
                other_change_paths.append(change_path)
        image_ids = list(set(image_ids))  # Remove duplicates

        # Apply images
        for image_id in image_ids:
            self.update_file_info(image_id)

        # Apply other changes
        for path in other_change_paths:
            if path == Path('metadata.json'):
                self.load_folders()

    def update_file_info(self, file_id: EagleFileID):
        """
        Update information related to changed file.
        """
        image_metadata = self.create_image_metadata_path(file_id)

        if not image_metadata.exists():
            self.indexed_files.pop(file_id, None)
            return

        with open(image_metadata, 'r') as f:
            obj = json.load(f)
        file = eagle_file_factory(obj)
        self.indexed_files[file.id] = file
        for fid in file.folders:
            self.indexed_files_by_folderid[fid] |= {file.id}
