"""

This file only contains the settings to be used in podi_SAMPListener.

"""

message_queue = "odi.image.load"

output_format = "/scratch/%OBSID.fits"

output_dir = "/scratch/"

use_ssh = True

ssh_user = "rkotulla"
ssh_host = "localhost"
remote_podi_dir = "/work/podi_devel/"
ssh_executable = "/work/podi_devel/podi_collectcells.py"

# Some additional settings for the focus sequence
focus_display = "display"

swarp_nicelevel = "nice +10"

def translate_filename_local2remote(filename):
    """

    This is a template to re0write the filenames from local paths to the
    path used on the remote system

    """

    if (filename.startswith("/Volumes")):
        # This is on a Mac
        new_filename = filename.replace("/Volumes/", "/mnt/")
    else:
        new_filename = filename

    return new_filename





def translate_filename_remote2local(input_filename, remote_filename):
    """

    This is a template to re-write the filenames from the remote machine to 
    paths valid on the local machine.

    """

    if (remote_filename.startswith("/mnt")):
        # This is on a Linux Machine, convert to Mac
        local_filename = remote_filename.replace("/mnt/", "/Volumes/")
    else:
        local_filename = remote_filename

    if (local_filename.find("%") >= 0):
        # This filename contains some special formatting instructions
        # Go ahead and translate them
        from podi_definitions import format_filename
        local_filename = format_filename(input_filename, local_filename)

    return local_filename
