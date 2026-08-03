#!/usr/bin/env python
import logging
import os
from pathlib import Path
import stat
import errno
import fuse
from fuse import Fuse

from src.eagle_repository import EagleRepository
from src.model import EagleFolder, EagleRootFolderID, FSStat

logger = logging.getLogger("eagle")
logger.setLevel(logging.INFO)

log_format = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(format=log_format)

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
        eagle_lib_path = Path(self.cmdline[0].eagle_lib_path)
        logger.info("Mounting EagleFS... %s to %s", eagle_lib_path.name, self.fuse_args.mountpoint)

        if 'debug' in self.fuse_args.optlist:
            logger.setLevel(logging.DEBUG)
            logger.debug("Debug logging enabled")

        self.repository = EagleRepository(eagle_lib_path)
        self.repository.load()
        Fuse.main(self)

    def fsinit(self):
        # fuse-python はデーモン化のために fork し、fork 前に起動したスレッドは
        # 子プロセスへ引き継がれない。監視スレッドは fork 後に呼ばれる
        # fsinit で起動する必要がある。
        self.repository.start()

    def fsdestroy(self):
        self.repository.close()

    def getattr(self, path):
        logger.debug("getattr %s", path)

        if path == '/':
            st = FSStat()
            st.st_uid = os.getuid()
            st.st_gid = os.getgid()
            st.st_mode = stat.S_IFDIR | 0o775
            st.st_nlink = 2
            root_time = self.repository.get_folder_time(EagleRootFolderID)
            st.st_atime = int(root_time.timestamp())
            st.st_mtime = int(root_time.timestamp())
            st.st_ctime = int(root_time.timestamp())
            return st

        try:
            file = self.repository.get_metadata(path)
            if isinstance(file, EagleFolder):
                return file.to_stat(self.repository.get_folder_time(file.id))
            return file.to_stat()
        except FileNotFoundError:
            return -errno.ENOENT
        except Exception:
            logger.exception("getattr failed: %s", path)
            return -errno.EIO

    def readdir(self, path, offset):
        """
        ディレクトリ内のファイル一覧
        """
        logger.debug("readdir %s %s", path, offset)
        try:
            filenames = self.repository.list_filenames(path)
        except FileNotFoundError:
            return -errno.ENOENT
        except Exception:
            logger.exception("readdir failed: %s", path)
            return -errno.EIO
        return [fuse.Direntry(r) for r in ['.', '..', *filenames]]

    def open(self, path, flags):
        """
        ファイルを開くにあたって権限周りの確認
        """
        logger.debug("open: %s %s", path, flags)

        try:
            self.repository.get_metadata(path)
        except FileNotFoundError:
            return -errno.ENOENT
        except Exception:
            logger.exception("open failed: %s", path)
            return -errno.EIO
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        # 読み込み専用で開くことを要求されているか確認
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

    def read(self, path, size, offset):
        """ファイルの中身を返す"""
        logger.debug("read %s %s %s", path, size, offset)
        try:
            return self.repository.get_binary(path, size, offset)
        except FileNotFoundError:
            return -errno.ENOENT
        except Exception:
            logger.exception("read failed: %s", path)
            return -errno.EIO


def main():
    usage="""
EagleFS: FUSE filesystem for Eagle Library

""" + Fuse.fusage
    server = EagleFS(version="%prog " + fuse.__version__,
                     usage=usage,
                     dash_s_do='undef')

    server.parse(errex=1)
    server.main()

if __name__ == '__main__':
    main()
