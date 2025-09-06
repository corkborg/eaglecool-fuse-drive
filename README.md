# EAGLE COOL FUSE Drive

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