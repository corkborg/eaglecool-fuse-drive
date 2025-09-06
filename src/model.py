
import os
import stat
import fuse
from dataclasses import dataclass
from typing import NewType

EagleFolderID = NewType('EagleFolderID', str)
EagleFileID = NewType('EagleFileID', str)
EagleRootFolderID = EagleFolderID('root')

def sanitize_filename(filename: str) -> str:
    return filename.replace('/', '_')


@dataclass
class EagleFolder:
    id: EagleFolderID
    name: str
    children: list['EagleFolder']
    modificationTime: int

    def normalize_name(self):
        return sanitize_filename(f'{self.name}_{self.id}')

    def to_stat(self):
        st = FSStat()
        st.st_uid =  os.getuid()
        st.st_gid =  os.getgid()
        st.st_atime = self.modificationTime
        st.st_mtime = self.modificationTime
        #st.st_ctime = self.modificationTime
        st.st_mode = stat.S_IFDIR | 0o755
        st.st_nlink = 2
        return st

@dataclass
class EagleFile:
    id: EagleFileID
    name: str
    folders: list[EagleFolderID]
    ext: str | None
    size: int
    width: int
    height: int
    modificationTime: int
    lastModified: int

    def normalize_name(self):
        return sanitize_filename(f'{self.name}_{self.id}.{self.ext}')

    def folder_name(self):
        return f'{self.id}.info'

    def to_stat(self):
        st = FSStat()
        st.st_uid =  os.getuid()
        st.st_gid =  os.getgid()
        st.st_atime = self.lastModified
        st.st_mtime = self.modificationTime
        st.st_ctime = self.lastModified
        st.st_size = self.size
        st.st_mode = stat.S_IFREG | 0o444
        st.st_nlink = 1
        return st


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