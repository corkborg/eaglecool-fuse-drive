import json
from pathlib import Path
import logging

from src.model import EagleFile, EagleFileID, EagleFolder, EagleFolderID, EagleRootFolderID

logger = logging.getLogger("eagle")
logger.setLevel(logging.INFO)


class EagleRepository:

    def __init__(self, library_path: Path | str):
        """
        Eagle library repository
        :param library_path: Path to Eagle library.
        """
        self.library_path = Path(library_path)
        self.folders: list[EagleFolder] = []
        self.indexed_folders: dict[EagleFolderID, EagleFolder] = {}
        self.indexed_files: dict[EagleFileID, EagleFile] = {}

        self.indexed_files_by_folderid: dict[EagleFolderID, list[EagleFileID]] = {}

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
        else:
            folder_id = self.search_folder(path)
            if folder_id is None:
                raise Exception(f"Folder not found: {path}")

            for folder in self.indexed_folders[folder_id].children:
                files.append(folder.normalize_name())

            for file_id in self.indexed_files_by_folderid.get(folder_id, []):
                file = self.indexed_files[file_id]
                files.append(file.normalize_name())
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
            return self.library_path / 'images' / file.folder_name() / f'{file.name}
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
                modificationTime=folder_obj.get('modificationTime', 0)
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

            file = EagleFile(
                id=obj['id'],
                name=obj['name'],
                folders=[EagleFolderID(fid) for fid in obj.get('folders', [])],
                ext=obj.get('ext', None),
                size=obj.get('size', 0),
                width=obj.get('width', 0),
                height=obj.get('height', 0),
                modificationTime=obj.get('modificationTime', 0),
                lastModified=obj.get('lastModified', 0)
            )
            self.indexed_files[file.id] = file
            if len(file.folders) == 0:
                self.indexed_files_by_folderid[EagleRootFolderID] = self.indexed_files_by_folderid.get(EagleRootFolderID, []) + [file.id]
            else:
                for fid in file.folders:
                    self.indexed_files_by_folderid[fid] = self.indexed_files_by_folderid.get(fid, []) + [file.id]

    def search_file(self, path: str) -> EagleFileID | None:
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