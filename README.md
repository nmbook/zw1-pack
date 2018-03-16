Packs and unpacks Zwei!! [Zwei: The Arges Adventure] DAT archives.

Usage
=====

Unpack
------

`./zw1_pack.py [-u] FILE.DAT ...`
Any number of FILE.DAT files can be given as arguments and they will be unpacked in sequence.
"-u" is optional.

Pack
----

`./zw1_pack.py -p FILE.DAT contents`
The first argument specifies the file name to use, all other files and folders will be placed inside (folders will be traversed since this archive format has no structure).
If "-p" is not provided and first argument is a folder, a DAT file of that folder name will be packed instead.

Windows Desktop
---------------

If Python 3 is installed on the desktop, this script should allow you to drag and drop a .dat file onto it. The file will be unpacked to a sub-folder (will overwrite if files already exist).
This script should allow you to drag and drop a directory onto it. The directory will be packed into a same-named .dat (will not overwrite).

Other Notes
-----------

The intended usage is you unpack a .dat file, make modifications, then pack it again (it will append a "-1"), then you replace the file for the game to see. Note that the file format strictly prohibits file names longer than 8 characters, non-ASCII file names, and files must have a 3-character extension.

Format Technical Details
========================

```
(uint32) Magic 0x00bc614e (12345678)
(uint32) Number of file tables, one table per file extension

For each type, specifies a file table (12 byte entries):
   (str[4]) File extension, padded with null
   (uint32) Position in this archive of this file table
   (uint32) Number of files

After these follows file tables, at positions listed above...

for each file, specifies a file info struct (16 byte entries):
   (str[8]) File name, padded with nulls
   (uint32) File size
   (uint32) Position in this archive of file

After these follows file data, at positions listed above...
```

Contents
========

File data is not compressed. In fact, the contents are all uncompressed formats, like BMP, TXT, and WAV.

To provide BMP files, the game expects **24-bit color, no color space information**.

To provide text files, the game expects **shift-JIS encoded text**.
