#!/usr/bin/env python3

import argparse
import os
import pprint
import struct
import sys
import traceback

def read_uint32(fp, pos):
    """Read 4 little-endian bytes into an unsigned 32-bit integer. Return value, position + 4."""
    fp.seek(pos)
    val = struct.unpack("<I", fp.read(4))[0]
    return val, pos + 4

def read_strn(fp, pos, size):
    """Read N null-padded bytes into an ascii encoded string. Return value, position + N."""
    fp.seek(pos)
    val = struct.unpack("<" + str(size) + "s", fp.read(size))[0]
    return val.decode("ascii").strip("\0"), pos + size

def write_into(fp, fmt, *args):
    b = struct.pack(fmt, *args)
    fp.write(b)
    return len(b)

def pack(file_array, args):
    """Packs files or folders given into the first argument: a target file name or a directory (archive will be named the same as directory).
    
    If archive name exists, appends number and tries again."""
    output_target = file_array[0]
    input_set = file_array.copy() # shallow copy the array
    if os.path.isdir(output_target):
        # passed in a folder: name is our dat file name, input is full array (default)
        output_target = os.path.basename(os.path.realpath(output_target.rstrip("\\/")))
        if len(output_target) == 0:
            print("Error: Archive name invalid.", file=sys.stderr)
            return
    elif len(output_target) > 4 and output_target[-4:].upper() == ".DAT":
        # passed in a .dat name: name stays, input is everything else in array
        input_set = file_array[1:]
    else:
        # passed in just a set of files where [0] not being .dat so no name hint: error
        print("Error: Unknown file(s). Please provide a .DAT file or existing folder to pack it.", file=sys.stderr)
        return

    # traverse directories now to get all file paths going in
    input_files = []
    for f in input_set:
        for dirpath, dirnames, filenames in os.walk(f):
            # skip dirs that start with . (like .git, ._DS_STORE, etc) or __ (like __MACOSX)
            for dirname in dirnames:
                if dirname.startswith(".") or dirname.startswith("__"):
                    dirnames.remove(dirname)
            input_files += [os.path.join(dirpath, name) for name in filenames if not name.startswith(".") and not name.startswith("__")]

    # look for path of output and if conflicts add numbers
    try_count = 0
    alt = ""
    while os.path.exists("{}{}.dat".format(output_target, alt)):
        try_count += 1
        alt = "-{}".format(try_count)
        if try_count >= 100:
            print("Error: Archive output file exists and no alternative.", file=sys.stderr)
            return

    output_target = "{}{}.dat".format(output_target, alt)

    if not args.quiet:
        print("Packing {} files into {}...".format(len(input_files), output_target))

    # iterate files for file_tables
    file_tables = []
    for file_path in input_files:
        try:
            #print(file_path)

            # start by creating file table objects
            name, ext = os.path.splitext(os.path.basename(file_path).lower())

            # sanity checking
            try:
                name = name.encode("ascii")
                ext = ext.encode("ascii")
            except UnicodeError:
                print("Error: Input file names must be valid ASCII. {} skipped.".format(file_path), file=sys.stderr)
                continue

            if len(ext) != 4:
                print("Error: Input file names must have 3 character extensions. {} skipped.".format(file_path), file=sys.stderr)
                continue

            ext = ext[1:]

            if len(name) < 1 or len(name) > 8:
                print("Error: Input file names must be <= 8 characters in length. {} skipped.".format(file_path), file=sys.stderr)
                continue

            if b"." in name:
                print("Error: Input file names cannot have multiple extensions or additional dots. {} skipped.".format(file_path), file=sys.stderr)
                continue

            # create fd object (pos TBD)
            this_name_obj = {"name": name, "size": os.path.getsize(file_path), "pos": None, "full_name": file_path}

            # create ft object, or use existing (pos and count TBD)
            this_ext_table = None
            for table in file_tables:
                if table["name"] == ext:
                    this_ext_table = table
                    break
            if this_ext_table is None:
                this_ext_table = {"name": ext, "count": None, "pos": None, "files": [this_name_obj]}
                file_tables.append(this_ext_table)
            else:
                this_ext_table["files"].append(this_name_obj)
        except Exception as err:
            print("Error: Uncaught exception locating file: " + file_path, file=sys.stderr)
            print("{}".format(err), file=sys.stderr)
            if not args.quiet:
                traceback.print_exc()
            return

    try:
        # determine offsets of tables
        pos = 8 # header size
        ft_count = len(file_tables)
        pos += ft_count * 12 # end of ft tables
        for ft in file_tables:
            fd_count = len(ft["files"])
            ft["count"] = fd_count
            ft["pos"] = pos
            pos += fd_count * 16 # size of fd entries for this ext

        # determine offsets of files
        for ft in file_tables:
            for fd in ft["files"]:
                fd["pos"] = pos
                pos += fd["size"]

        # start writing archive
        with open(output_target, "wb") as f:
            pos  = 0
            pos += write_into(f, "<II", 12345678, ft_count)

            for ft in file_tables:
                f.write(ft["name"].ljust(4, b"\0"))
                pos += 4
                pos += write_into(f, "<II", ft["pos"], ft["count"])

            for ft in file_tables:
                for fd in ft["files"]:
                    f.write(fd["name"].ljust(8, b"\0"))
                    pos += 8
                    pos += write_into(f, "<II", fd["size"], fd["pos"])

            for ft in file_tables:
                for fd in ft["files"]:
                    file_path = fd["full_name"]
                    if not args.quiet:
                        print(file_path)
                    try:
                        with open(file_path, "rb") as fi:
                            f.write(fi.read(fd["size"]))
                    except Exception as err:
                        print("Error: Uncaught exception writing file to archive: " + output_target + " <- " + file_path, file=sys.stderr)
                        print("{}".format(err), file=sys.stderr)
                        if not args.quiet:
                            traceback.print_exc()
                        return

    except Exception as err2:
        print("Error: Uncaught exception writing archive: " + output_target, file=sys.stderr)
        print("{}".format(err2), file=sys.stderr)
        if not args.quiet:
            traceback.print_exc()

def unpack(file_array, args):
    """Unpacks one or more files given the provided arguments.
    
    If contents exist in the target output folder, they will be overwritten."""
    if not args.quiet:
        print("Unpacking {} files...".format(len(file_array)))
    # var used for not spamming errors about files of the wrong type, assumes at least some are valid...
    is_multiple = (len(file_array) != 1)
    for file_path in file_array:
        try:
            if not os.path.isfile(file_path):
                print("Error: File not found: " + file_path, file=sys.stderr)
                continue

            # base file name (folder name we'll be using)
            basename = os.path.basename(os.path.realpath(file_path))
            if len(basename) <= 4 or basename[-4:].upper() != ".DAT":
                if not is_multiple:
                    print("Error: Not an archive of the correct format [file name error]: " + file_path, file=sys.stderr)
                continue

            # make dirname
            dirname = basename[:-4] + "/"
            # print bare archive name
            if not args.quiet or args.test:
                print(basename)

            # start reading
            with open(file_path, "rb") as f:
                pos = 0
                magic, pos = read_uint32(f, pos)

                # must start with magic
                if magic != 12345678:
                    if not is_multiple:
                        print("Error: Not an archive of the correct format [magic number error]: " + file_path, file=sys.stderr)
                    continue

                # read file table count
                ft_count, pos = read_uint32(f, pos)

                # read each file table
                file_tables = []
                for x in range(0, ft_count):
                    ftext, pos = read_strn  (f, pos, 4)
                    ftpos, pos = read_uint32(f, pos)
                    ftnum, pos = read_uint32(f, pos)
                    
                    ft = {"name": ftext, "count": ftnum, "pos": ftpos, "files": []}

                    # subtables
                    for y in range(0, ftnum):
                        fdnam, ftpos = read_strn  (f, ftpos, 8)
                        fdsiz, ftpos = read_uint32(f, ftpos)
                        fdpos, ftpos = read_uint32(f, ftpos)
                        
                        fd = {"name": fdnam, "size": fdsiz, "pos": fdpos}

                        ft["files"].append(fd)

                    file_tables.append(ft)

                #print("{}".format(file_tables))
                if args.test:
                    # -t: test mode, print contents and exit
                    pp = pprint.PrettyPrinter(indent=4)
                    pp.pprint(file_tables)
                else:
                    # normal, write to files in dirname
                    if not os.path.isdir(dirname):
                        # DNE
                        os.mkdir(dirname)
                    # iterate through structures
                    for ft in file_tables:
                        for fd in ft["files"]:
                            # print "folder/file"
                            out_path = os.path.join(dirname, fd["name"] + "." + ft["name"])
                            if not args.quiet:
                                print(out_path)
                            # write to "folder/file"
                            with open(out_path, "wb") as fo:
                                f.seek(fd["pos"])
                                fo.write(f.read(fd["size"]))
        except Exception as err:
            print("Error: Uncaught exception parsing file: " + file_path, file=sys.stderr)
            print("{}".format(err), file=sys.stderr)
            if not args.quiet:
                traceback.print_exc()
            continue

def main():
    MODE_UNSET = 0
    MODE_UNPACK = 1
    MODE_PACK = 2

    parser = argparse.ArgumentParser(description="Packs and unpacks Zwei!! [Zwei: The Arges Adventure] DAT archives.")
    parser.add_argument("-u", "--unpack", help="try unpacking", action="store_true")
    parser.add_argument("-p", "--pack", help="try packing", action="store_true")
    parser.add_argument("-t", "--test", help="do not write output and print what would happen instead (test)", action="store_true")
    parser.add_argument("-q", "--quiet", help="suppress per-file output", action="store_true")
    parser.add_argument("-s", "--from-sh", help="suppress pause on completion, if invoked from CLI", action="store_true")
    parser.add_argument("infile", nargs="*", help="file(s) to read")
    args = parser.parse_args()

    mode = MODE_UNSET

    if args.pack and args.unpack:
        print("Error: You cannot both pack and unpack the input.", file=sys.stderr)
        return args.from_sh

    count = len(args.infile)

    if count == 0:
        print("Error: No files. Please provide a .DAT file to unpack or a folder to pack.", file=sys.stderr)
        return args.from_sh

    if args.pack:
        # -p
        mode = MODE_PACK
    elif args.unpack:
        # -u
        mode = MODE_UNPACK

    if mode == MODE_UNSET and os.path.isdir(args.infile[0]):
        # first file is dir -> pack
        mode = MODE_PACK

    if mode == MODE_UNSET and os.path.isfile(args.infile[0]) and args.infile[0][-4:].upper() == ".DAT":
        # first file is .dat -> unpack
        mode = MODE_UNPACK

    if mode == MODE_UNSET:
        print("Error: Unknown file(s). Please provide a .DAT file to unpack or a folder to pack.", file=sys.stderr)
    elif mode == MODE_UNPACK:
        unpack(args.infile, args)
    elif mode == MODE_PACK:
        pack(args.infile, args)

    return args.from_sh

if __name__ == "__main__":
    if not main():
        input("Press Enter to close...")


