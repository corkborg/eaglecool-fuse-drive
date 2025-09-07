# Eagle cool fuse filesystem

![Eagle cool fuse filesystem](img/header.jpg "Eagle cool fuse filesystem")


Eagle cool is an image management tool (https://eagle.cool/)

This project is for mounting Eagle cool libraries as a filesystem with FUSE.<br>
Currently, it only supports Linux, but it may also be usable with macFuse and other platforms.

```shell
$ python3 eagle_fs.py /mnt --eagle_lib_path=test.library

$ ls -l /mnt
total 7
-r--r--r-- 1 user user 3036 Aug 19  57651  blue_MF7XBDKD71MCF.png
drwxr-xr-x 2 user user    0 Aug 16  57651 'empty folder_MF7X5JO46GF79'/
drwxr-xr-x 2 user user    0 Aug 14  57651  folder_MF7X2TP5LYADS/
drwxr-xr-x 2 user user    0 Aug 15  57651  nested_folder_MF7X4JQBHM2E7/
drwxr-xr-x 2 user user    0 Aug 16  57651  nested_folder_empty_MF7X58NBYUNSQ/
drwxr-xr-x 2 user user    0 Aug 16  57651  samefolder_MF7X5W2L2ZJ34/
drwxr-xr-x 2 user user    0 Aug 16  57651  samefolder_MF7X6HU53Z5W2/
-r--r--r-- 1 user user   17 Aug 14  57651  text_MF7X2MAQ0AQ13.txt

$ ls /mnt/folder_MF7X2TP5LYADS/
orangepng_MF7X11V2AM3EP.png  pink_gif_MF7X1TY7F0LWI.gif
```

## Install

```bash
pip3 install -r requirements.txt
```

## Launch

```bash
python3 eagle_fs.py /mnt --eagle_lib_path=test.library
```

If you need to share with daemons like samba, docker etc (you need to allow_user in FUSE)

```bash
python3 eagle_fs.py /mnt --eagle_lib_path=test.library -o allow_other
```

## Stop

```bash
umount /mnt
```

## Debug

```bash
python3 eagle_fs.py /mnt --eagle_lib_path=test.library -f -d
```

## Unittest

```bash
python3 -m unittest discover -s tests
```

## Fuse allow other.

By default, FUSE makes files visible only to current user.

To make the file system visible to systems with different running users, such as Samba, Docker, etc., you need to change the FUSE configuration.

```bash
echo 'user_allow_other' > /etc/fuse.conf
```