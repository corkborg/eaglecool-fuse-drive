# Eagle.cool fuse filesystem

![Eagle cool fuse filesystem](img/header.jpg "Eagle cool fuse filesystem")

This project is for mounting Eagle libraries as a filesystem with FUSE.
Currently, it only supports Linux, but it may also be usable with macFuse and other platforms.

## Install

```
pip3 install -r requirements.txt
```

## Launch

```
python3 eagle_drive.py /mnt -o allow_other
```

## Stop

```
umount /mnt
```

## Debug

```
python3 eagle_drive.py /mnt -f -d -o allow_other
```

## File sharing

By default, FUSE makes files visible only to the running user.
To make the filesystem visible to systems with different running users, such as Samba, you need to change the FUSE settings.

```
echo 'user_allow_other' > /etc/fuse.conf
```