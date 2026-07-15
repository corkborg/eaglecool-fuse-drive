

import os
import stat
import fuse
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import NewType

EagleFolderID = NewType('EagleFolderID', str)
EagleFileID = NewType('EagleFileID', str)
EagleRootFolderID = EagleFolderID('root')


def sanitize_filename(filename: str) -> str:
    return filename \
        .replace('/', '_')


@dataclass
class EagleFolder:
    id: EagleFolderID
    name: str
    sub_folders: list['EagleFolder']
    raw_modification_time: datetime
    files: list['EagleFile']

    def append_file(self, file: 'EagleFile'):
        self.files.append(file)


    def solve_folder(self, base_path: str) -> EagleFolderID | None:
        if base_path == '/':
            return self.id
        parts = base_path.strip('/').split('/', 1)
        if parts[0] == self.normalize_name():
            if len(parts) == 1:
                return self.id
            for folder in self.sub_folders:
                fid = folder.solve_folder(parts[1])
                if fid is not None:
                    return fid
        return None

    def solve_file(self, base_path: str) -> EagleFileID | None:
        if base_path == '/':
            return None
        parts = base_path.strip('/').split('/', 1)
        if len(parts) == 1:
            for file in self.files:
                if file.normalize_name() == parts[0]:
                    return file.id
            return None
        if parts[0] == self.normalize_name():
            for folder in self.sub_folders:
                fid = folder.solve_file(parts[1])
                if fid is not None:
                    return fid
        return None



    def normalize_name(self):
        return sanitize_filename(f'{self.name}_{self.id}')

    def to_stat(self):
        st = FSStat()
        st.st_uid =  os.getuid()
        st.st_gid =  os.getgid()
        # st.st_atime = int(self.modification_time.timestamp()) # アクセス日時
        # st.st_mtime = int(self.modification_time.timestamp())
        st.st_ctime = int(self.raw_modification_time.timestamp())
        st.st_mode = stat.S_IFDIR | 0o755
        st.st_nlink = 2
        return st


def eagle_folder_factory(obj: dict) -> EagleFolder:
    """
    Create EagleFolder from dict (parsed JSON)
    """
    return EagleFolder(
        id=EagleFolderID(obj['id']),
        name=obj['name'],
        sub_folders=[eagle_folder_factory(child) for child in obj.get('children', [])],
        raw_modification_time=datetime.fromtimestamp(obj.get('modificationTime', 0) / 1000, tz=timezone.utc),
        files=[]
    )


@dataclass
class EagleFile:
    id: EagleFileID
    name: str
    folders: set[EagleFolderID]
    ext: str | None
    is_deleted: bool
    size: int
    width: int
    height: int
    modification_time: datetime
    last_modified: datetime

    def normalize_name(self):
        return sanitize_filename(f'{self.name}_{self.id}.{self.ext}')

    def folder_name(self):
        return f'{self.id}.info'

    def to_stat(self):
        st = FSStat()
        st.st_uid =  os.getuid()
        st.st_gid =  os.getgid()
        st.st_atime = int(self.last_modified.timestamp())
        st.st_mtime = int(self.modification_time.timestamp())
        st.st_ctime = int(self.last_modified.timestamp())
        st.st_size = self.size
        st.st_mode = stat.S_IFREG | 0o444
        st.st_nlink = 1
        return st


def eagle_file_factory(obj: dict) -> EagleFile:
    """
    Create EagleFile from dict (parsed JSON)"""
    return EagleFile(
        id=obj['id'],
        name=obj['name'],
        folders={EagleFolderID(fid) for fid in obj.get('folders', []) if fid is not None},
        ext=obj.get('ext', None),
        is_deleted=obj.get('isDeleted', False),
        size=obj.get('size', 0),
        width=obj.get('width', 0),
        height=obj.get('height', 0),
        modification_time=datetime.fromtimestamp(obj.get('modificationTime', 0) / 1000, tz=timezone.utc),
        last_modified=datetime.fromtimestamp(obj.get('lastModified', 0) / 1000, tz=timezone.utc)
    )


class FSStat(fuse.Stat):
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0
