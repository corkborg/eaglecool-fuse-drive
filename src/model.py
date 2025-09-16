
import os
import stat
import fuse
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
    children: list['EagleFolder']
    modification_time: int

    def normalize_name(self):
        return sanitize_filename(f'{self.name}_{self.id}')

    def to_stat(self):
        st = FSStat()
        st.st_uid =  os.getuid()
        st.st_gid =  os.getgid()
        st.st_atime = self.modification_time
        st.st_mtime = self.modification_time
        #st.st_ctime = self.modificationTime
        st.st_mode = stat.S_IFDIR | 0o755
        st.st_nlink = 2
        return st


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
    modification_time: int
    last_modified: int

    def normalize_name(self):
        return sanitize_filename(f'{self.name}_{self.id}.{self.ext}')

    def folder_name(self):
        return f'{self.id}.info'

    def to_stat(self):
        st = FSStat()
        st.st_uid =  os.getuid()
        st.st_gid =  os.getgid()
        st.st_atime = self.last_modified
        st.st_mtime = self.modification_time
        st.st_ctime = self.last_modified
        st.st_size = self.size
        st.st_mode = stat.S_IFREG | 0o444
        st.st_nlink = 1
        return st


def eagle_file_factory(obj: dict) -> EagleFile:
    return EagleFile(
        id=obj['id'],
        name=obj['name'],
        folders={EagleFolderID(fid) for fid in obj.get('folders', []) if fid is not None},
        ext=obj.get('ext', None),
        is_deleted=obj.get('isDeleted', False),
        size=obj.get('size', 0),
        width=obj.get('width', 0),
        height=obj.get('height', 0),
        modification_time=obj.get('modificationTime', 0),
        last_modified=obj.get('lastModified', 0)
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
