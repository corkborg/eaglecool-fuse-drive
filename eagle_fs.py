#!/usr/bin/env python

import tomllib
import logging
import os
import stat
import errno
import fuse
from fuse import Fuse

from src.eagle_repository import EagleRepository
from src.model import FSStat

logger = logging.getLogger("eagle")
logger.setLevel(logging.INFO)

format = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(format=format)

if not hasattr(fuse, '__version__'):
    raise RuntimeError("your fuse-py doesn't know of fuse.__version__, probably it's too old.")

fuse.fuse_python_api = (0, 2)


class EagleFS(Fuse):

    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        self.parser.add_option(
            "--eagle_lib_path",
            help="Path to Eagle library",
            action="store"
        )


    def main(self, args=None):
        logger.info("Mounting EagleFS...")

        eagle_lib_path = self.cmdline[0].eagle_lib_path
        self.repository = EagleRepository(eagle_lib_path)
        self.repository.load()
        Fuse.main(self)

    def getattr(self, path):
        logger.info("getattr %s", path)

        if path == '/':
            st = FSStat()
            st.st_uid = os.getuid()
            st.st_gid = os.getgid()
            st.st_mode = stat.S_IFDIR | 0o775
            st.st_nlink = 2
            return st

        try:
            file = self.repository.get_metadata(path)
            st = file.to_stat()
            return st
        except Exception:
            return -errno.ENOENT

    def readdir(self, path, offset):
        """
        ディレクトリ内のファイル一覧
        """
        logger.info("readdir %s %s", path, offset)
        for r in  '.', '..':
            yield fuse.Direntry(r)
        for r in self.repository.list_filenames(path):
            yield fuse.Direntry(r)

    def open(self, path, flags):
        """
        ファイルを開くにあたって権限周りの確認
        """
        logger.info("open: %s %s", path, flags)

        try:
            self.repository.get_metadata(path)
        except Exception:
            return -errno.ENOENT
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        # 読み込み専用で開くことを要求されているか確認
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        """ファイルの中身を返す"""
        logger.info("read %s %s %s", path, size, offset)
        try:
            print("read", path, size, offset)
            return self.repository.get_binary(path, size, offset)
        except Exception as e:
            print("error:", e)
            return -errno.ENOENT

def main():
    usage="""
EagleFS: FUSE filesystem for Eagle Library

""" + Fuse.fusage
    server = EagleFS(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='setsingle')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
