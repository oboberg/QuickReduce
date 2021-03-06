#!/usr/bin/env python
#
# Copyright 2012-2013 Ralf Kotulla
#                     kotulla@uwm.edu
#
# This file is part of the ODI QuickReduce pipeline package.
#
# If you find this program or parts thereof please make sure to
# cite it appropriately (please contact the author for the most
# up-to-date reference to use). Also if you find any problems 
# or have suggestiosn on how to improve the code or its 
# functionality please let me know. Comments and questions are 
# always welcome. 
#
# The code is made publicly available. Feel free to share the link
# with whoever might be interested. However, I do ask you to not 
# publish additional copies on your own website or other sources. 
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
#

from podi_definitions import *

wcs_ref_dir = "/datax/2mass_fits/"
wcs_ref_type = "2mass_nir"

sdss_ref_type = 'local' # can also be 'web' or 'stripe82'
sdss_ref_type = 'web'
sdss_ref_dir = '/nas/wiyn/sdss_photcalib/'

number_cpus = "auto"
max_cpu_count = 6
if (cmdline_arg_isset("-ncpus")):
    number_cpus = int(cmdline_arg_set_or_default("-ncpus", number_cpus))
    print "Using user-defined CPU count of",number_cpus


#wcs_ref_dir = "/datax/2mass_fits/"
#wcs_ref_type = "2mass_opt"

scratch_dir = "/tmp/"

if __name__ == "__main__":
    print "This file defines some site properties, mostly paths."
    print "Feel free to edit it to adapt directories to your site"
    
