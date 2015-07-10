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

"""
podi_matchpupilghost

This module contains all routines and functionality related to removing the 
pupilghost signature from either the flat-field or a science frame. 


Standalone functions:
================================================================================
Most routines are made to be called from other routines, but the following 
stand-alone modi exist:


* **Create a radial profile from a full 2-d template**

  Run as :
  ``./podi_matchpupilghost -makeradial 2d-template.fits 1d-output.fits``



* **Compute the best-fitting scaling factor for the template**

  Run as:
  ``./podi_matchpupilghost -getscaling science_input.fits template.fits``



* **Subtract the pupilghost from a given frame, with automatic scaling**

  Run as:
  ``./podi_matchpupilghost -cleanpupilghost inputframe.fits template.fits output.fits``

  In this case, the scaling factor is automatically derived in the same manner
  as with the -getscaling flag described above.




* **Subtract the pupilghost from a given frame**

  Run as:
  ``./podi_matchpupilghost -cleanpupilghost inputframe.fits template.fits output.fits (scaling)``

  (scaling is optional, and a value of 1.0 is assumed if no value is given.


Modules
================================================================================

"""


import sys
import os
import pyfits
import numpy
import scipy
import dev_pgcenter
import podi_logging
import logging

gain_correct_frames = False
from podi_definitions import *
from podi_commandline import *
import podi_fitskybackground

"""
Available functions
===================
"""


scaling_factors = {
    "odi_g": 1.0,
    "odi_i": 0.3, #15,
}

def compute_pupilghost_template_ota(input_hdu, pupil_hdu, 
                                    rotate=True, verbose=True, non_negative=True,
                                    source_center_coords='data'
                                ):

    """

    Contains all functionality to match and rotate the pupilghost template to 
    match the current OTA.

    Parameters
    ----------
    input_hdu : pyfits.HDU
        Has to be a valid ImageHDU. This HDU is the source of the image data 
        that contains the pupilghost, as well as the EXTNAME keyword to select
        the correct template.

    rotator_angle : float
        Rotator angle from the primary HDU

    filtername : string
        This parameter is only important if source_center_coords is not set to
        'header' or 'data'. In that case, it defines the filter for the set of 
        set of pre-canned pupilghost center coordinates

    pupil_hdu : pyfits.HDUList
        HDUlist containing the pupilghost template

    scaling : float
        scaling factor for the pupilghost amplutide

    rotate : Bool
        Apply rotation (see rotator_angle) to the pupilghost template before
        removing it from the input data

    verbose : Bool
        Output some progress updates during runtime

    non_negative : Bool
        if set, all negative values in the pupilghost templates (that are 
        very likely unphysical) are clipped to 0.

    source_center_coords : ('data', 'header', 'xxx').
        if set to 'data', the center of the pupilghost is determined auto-
        matically during execution. If set to 'header', it is assumed that
        the input-hdu already contains header keywords with information about
        the location of the pupilghost. This is likely not the case for flat-
        field data, but important for science frames. All other values use
        the pre-canned coordinates given in podi_definitions.

    Returns
    -------
    No return value per se, changes are reflected in input_hdu

    see also
    --------
    `dev_pgcenter.find_pupilghost_center`

    """

    #
    # Check if this extension is included in the pupilghost template
    #
    extname = input_hdu.header['EXTNAME']
    right_ext = -1
    for this_ext in range(1, len(pupil_hdu)):
        if (pupil_hdu[this_ext].header['EXTNAME'] == extname):
            right_ext = this_ext
            break

    if (right_ext < 0):
        # This extension is not listed in the pupil-ghost template
        # We can't do anythin in this case, so let's simply return
        input_hdu.header['PGAFCTD'] = (False, "is the OTA affected by the pupilghost")
        return None

    # Get some information about the current input frame
    rotator_angle = input_hdu.header['ROTSTART'] if (rotate) else 0.
    filtername = input_hdu.header['FILTER']

    #
    # Set the coordinates of the center of the pupilghost 
    #
    # Read the center coordinates from the pupil ghost template file
    source_center_coords = 'data'
    if (source_center_coords == 'data'):
        fx, fy, fr, vx, vy, vr = dev_pgcenter.find_pupilghost_center(input_hdu, verbose=False)
        center_x, center_y = vx, vy
    #
    # Use center coordinates from header
    elif (source_center_coords == 'header'):
        # if ("PGCNTR_X" in input_hdu.header): 
        #     center_x = input_hdu.header['PGCNTR_X']
        # if ("PGCNTR_Y" in input_hdu.header): 
        #     center_y = input_hdu.header['PGCNTR_Y']

        if ('PGEFCTVX' in input_hdu.header):
            center_x = input_hdu.header['PGEFCTVX']
        if ('PGEFCTVX' in input_hdu.header):
            center_x = input_hdu.header['PGEFCTVX']
    #
    # by default, resort to the old-fashined canned values
    else:
        if (filtername in pupilghost_centers):
            if (extname in pupilghost_centers[filtername]):
                print pupilghost_centers[filtername][extname]
                center_x, center_y = pupilghost_centers[filtername][extname]
            else:
                if (extname in pupilghost_centers):
                    center_x, center_y = pupilghost_centers[extname]
                else:
                    # Don't know what center coordinate to use, abort
                    return None
        elif (extname in pupilghost_centers):
            center_x, center_y = pupilghost_centers[extname]
        else:
            # Don't know what center coordinate to use, abort
            return None

    #
    # Now we know we have to do something
    #
    if (verbose): 
        print "Found matching pupil ghost template in extension",right_ext
    print "Using center coordinates", center_x, center_y," for data frame"

    if (rotate):
        # print "___%s___" % rotator_angle
        if (rotator_angle == "unknown"):
            rotator_angle = 0.0

        # Rotate to the right angle
        # Make sure to rotate opposite to the rotator angle since we rotate 
        # the correction and not the actual data
        template = pupil_hdu[right_ext].data
        # Replace all NaNs with zeros
        template[numpy.isnan(template)] = 0.

        if (math.fabs(rotator_angle) < 0.5):
            if (verbose): print "Rotator angle is small (%.2f), skipping rotation" % (rotator_angle)
            rotated = template
        else:
            if (verbose): print "rotating template by",rotator_angle,"degrees"
            rotated = rotate_around_center(template, rotator_angle, mask_nans=False)
    else:
        if (verbose): print "No rotation requested, skipping rotation"
        rotated = pupil_hdu[right_ext].data
     
   
    template_centerx, template_centery = rotated.shape[0]/2, rotated.shape[1]/2
    if (source_center_coords == 'data'):
        #
        # Ok, now we have the pupil ghost rotated to the right angle
        #
        data_shape = input_hdu.data.shape

        # Now extract the right quadrant from the pupilghost template
        quadrant = {'OTA33.SCI': [0,4500,0,4500],
                    'OTA34.SCI': [0,4500,4500,9000],
                    'OTA44.SCI': [4500,9000,4500,9000],
                    'OTA43.SCI': [4500,9000,0,4500],
                }
        quadrant = {'OTA33.SCI': [400,4500,400,4500],
                    'OTA34.SCI': [400,4500,4500,8600],
                    'OTA44.SCI': [4500,8600,4500,8600],
                    'OTA43.SCI': [4500,8600,400,4500],
                }
        xys = quadrant[extname]
        template_quadrant = rotated[xys[2]:xys[3], xys[0]:xys[1]]
        # Now we have the right quadrant, search for center position in template
        imghdu = pyfits.ImageHDU(data=template_quadrant)
        imghdu.header['EXTNAME'] = extname
        pyfits.HDUList([pyfits.PrimaryHDU(), imghdu]).writeto("template_%s.fits" % extname, clobber=True)
        tx, ty, _, _, _, _ = dev_pgcenter.find_pupilghost_center(imghdu, verbose=False,
                                                                 fixed_radius=vr)
        print "Found pg center at",tx, ty
        
        template_centerx, template_centery = tx+xys[0], ty+xys[2]
        print "Using",template_centerx, template_centery, "as center coordinates for template"
        # center_x, center_y = vx, vy
        
        # Swap x/y since python does it too
        print "rot.shape=",rotated.shape

 
    bx = template_centerx - center_x
    by = template_centery - center_y
    tx, ty = bx + data_shape[0], by + data_shape[1]

    correction = rotated[by:ty, bx:tx]
    correction[numpy.isnan(correction)] = 0.

    if (non_negative):
        correction[correction < 0] = 0

    # Store the position of the pupil ghost center
    input_hdu.header['PGAFCTD'] = (True, "is the OTA affected by the pupilghost")
    input_hdu.header['PGCENTER'] = "%d %d" % (center_x, center_y)
    input_hdu.header['PGCNTR_X'] = (center_x, 'pupil ghost center x')
    input_hdu.header['PGCNTR_Y'] = (center_y, 'pupil ghost center y')
    input_hdu.header['PGTMPL_X'] = (template_centerx, 'pupil ghost template center x')
    input_hdu.header['PGTMPL_Y'] = (template_centery, 'pupil ghost template center y')
    input_hdu.header['PGREG_X1'] = (bx, "matched region of pupilghost, left")
    input_hdu.header['PGREG_X2'] = (tx, "matched region of pupilghost, right")
    input_hdu.header['PGREG_Y1'] = (by, "matched region of pupilghost, bottom")
    input_hdu.header['PGREG_Y2'] = (ty, "matched region of pupilghost, top")
    input_hdu.header['PGEFCTVX'] = (center_x - template_centerx + rotated.shape[1]/2, "effective pupilghost center X")
    input_hdu.header['PGEFCTVY'] = (center_y - template_centery + rotated.shape[0]/2, "effective pupilghost center Y")
    input_hdu.header['PGROTANG'] = (rotator_angle, "pupil ghost rotator angle")

    return correction


def get_pupilghost_scaling_ota(science_hdu, pupilghost_frame, 
                               n_samples=750, boxwidth=20, 
                               verbose=True,
                               pg_matched=False):
    """Find the optimum scaling for the pupil ghost. This is done by sampling the
    image frame and the pupil ghost template at a range of identical
    positions. The median ratio between these measurements then yields the
    scaling ratio.

    Parameters
    ----------
    
    science_hdu : ImageHDU

        If science frame is a string, it is interpreted as the filename of the
        science frame for which we are to obtain the scaling. Alternatively you
        can also pass the HDUList of the science frame.

    pupilghost_template : string of HDUList

        same as above, just for the pupil-ghost template

    n_samples : int

        Number of intensity samples to take *from each OTA* when deriving the
        optimum scaling factor.

    boxwidth : int
 
        Size of the sample box, in pixels

    Returns
    -------

    median_scaling_factor

    standard deviation of scaling factor

    """

    logger = logging.getLogger("GetPupilghostScaling")

    merged_all = numpy.zeros(shape=(0,6))

    any_affected = False


    
    extname = science_hdu.header['EXTNAME']
    filter = science_hdu.header['FILTER']

    if (type(pupilghost_frame) == str):
        pg_hdulist = pyfits.open(pupilghost_frame)
        pg = pg_hdulist[extname].data
    elif (type(pupilghost_frame) == pyfits.HDUList):
        pg = pupilghost_frame[extname].data
    elif (type(pupilghost_frame) == numpy.ndarray):
        pg = pupilghost_frame
    else:
        logger.debug("Not sure what the format of the pupilghost is!")
        return None

    logger.debug("Checking extension %s (filter: %s) for pupilghost effects" % (extname, filter))

    if (not 'PGAFCTD' in science_hdu.header or not science_hdu.header['PGAFCTD']):
        # This frame does not contain the keyword labeling it as affected by
        # the pupilghost. In that case we don't need to do anything
        logger.debug("This extension (%s) does not have any pupilghost problem" % (extname))
        return None

    logger.debug("Checking pupilghost center position")

    # Try to find the center position of the pupilghost from the science
    # frame. The necessary headers should have been inserted during 
    # flat-field correction
    if ('PGEFCTVX' in science_hdu.header and 
        'PGEFCTVY' in science_hdu.header):

        center = (science_hdu.header['PGEFCTVX'], 
                  science_hdu.header['PGEFCTVY'])

    else:
        logger.debug("Couldn't find a pupilghost center, skipping rest of work")
        return None

    data = science_hdu.data

    #n_samples = 1750
    logger.debug("Getting sky-samples for science frame")
    samples = numpy.array(podi_fitskybackground.sample_background(data, None, None, 
                                                      min_found=n_samples, fit_regions=[], 
                                                      boxwidth=boxwidth))

    if (samples.shape[0] <= 0):
        logger.debug("Couldn't find enough sky samples, skipping OTA %s" % (extname))
        return None

    box_centers = samples[:,2:4]

    dxy = box_centers - center
    pg_xy = box_centers
    if (not pg_matched):
        # This is the case if we compare to the full template
        # Now convert the x/y from the science frame 
        # into x/y in the pupil ghost frame
        pg_xy = dxy + [ 0.5*pg.shape[0], 0.5*pg.shape[1] ]
        
    #print dxy[0:10,:]
    #print pg_xy[0:10,:]

    #print pg_samples.shape
    #print pg_xy.shape
    logger.debug("Getting sky-samples for pupilghost template")
    pg_samples =  numpy.array(podi_fitskybackground.sample_background(pg, None, None, 
                                                                      fit_regions=[],
                                                                      box_center=pg_xy,
                                                                      boxwidth=boxwidth))
    if (pg_samples.shape[0] <= 0):
        logger.debug("Couldn't find enough pg.template samples, skipping OTA %s" % (extname))
        return None


    #print pg_samples.shape

    #continue

    ri = 400
    ro = 3300
    radius = numpy.sqrt(numpy.sum( dxy**2, axis=1))
    #print radius[0:10]

    #print extname
    #print center

    # numpy.savetxt("xxx", samples)
    # numpy.savetxt("yyy", pg_samples)

    # unaffected data points inside or outside the pupil ghost
    unaffected = (radius < ri) | (radius > ro)
    skylevel = numpy.median(samples[:,4][unaffected])
    logger.debug("Found background level not affected by PG: %.1f" % (skylevel))

    # derive maximum intensity of pupil ghost 
    # better: read from file
    pg_max = numpy.max(pg_samples[:,4])
    logger.debug("Maximum intensity of pupilghost: %f" % (pg_max))

    # Now merge the two arrays:
    merged = numpy.empty(shape=(pg_xy.shape[0],6))
    merged[:,0:2] = samples[:,2:4]
    merged[:,2:4] = pg_samples[:,2:4]
    merged[:,4] = numpy.array(samples)[:,4] - skylevel
    merged[:,5] = numpy.array(pg_samples)[:,4]
    # numpy.savetxt("zzz", merged)


    ratio = merged[:,4] / merged[:,5]
    logger.debug("simple ratio science/template (ota %s): %f" % (extname, numpy.median(ratio)))

    strong_pg_signal = merged[:,5] > 0.4*pg_max
    valid_ratios = ratio[strong_pg_signal]
    median_ratio = numpy.median(valid_ratios)
    uncert_ratio = numpy.std(valid_ratios)

    logger.debug("ratio for strong pg pixels (%d samples): %f +/- %f" % (
        numpy.sum(strong_pg_signal), median_ratio, uncert_ratio))

    good_samples = None
    if (numpy.sum(strong_pg_signal) > 0):
        # Only merge the samples with sufficient pupilghost signal
        good_samples = merged[strong_pg_signal]
        
    return good_samples








def subtract_pupilghost_extension(input_hdu, rotator_angle, filtername, pupil_hdu, scaling, 
                                  rotate=True, verbose=True, non_negative=True,
                                  source_center_coords='data'
                                  ):

    """

    Contains all functionality to execute the actual pupil ghost removal. The
    pupil ghost is roatted to match the rotation angle of the science frame,
    then scaled with the specified scaling factor and lastly the scaled template
    is removed from the science frame. The results stay in the input_hdu
    variable that is also returned.

    Parameters
    ----------
    input_hdu : pyfits.HDU
        Has to be a valid ImageHDU. This HDU is the source of the image data 
        that contains the pupilghost, as well as the EXTNAME keyword to select
        the correct template.

    rotator_angle : float
        Rotator angle from the primary HDU

    filtername : string
        This parameter is only important if source_center_coords is not set to
        'header' or 'data'. In that case, it defines the filter for the set of 
        set of pre-canned pupilghost center coordinates

    pupil_hdu : pyfits.HDUList
        HDUlist containing the pupilghost template

    scaling : float
        scaling factor for the pupilghost amplutide

    rotate : Bool
        Apply rotation (see rotator_angle) to the pupilghost template before
        removing it from the input data

    verbose : Bool
        Output some progress updates during runtime

    non_negative : Bool
        if set, all negative values in the pupilghost templates (that are 
        very likely unphysical) are clipped to 0.

    source_center_coords : ('data', 'header', 'xxx').
        if set to 'data', the center of the pupilghost is determined auto-
        matically during execution. If set to 'header', it is assumed that
        the input-hdu already contains header keywords with information about
        the location of the pupilghost. This is likely not the case for flat-
        field data, but important for science frames. All other values use
        the pre-canned coordinates given in podi_definitions.

    Returns
    -------
    No return value per se, changes are reflected in input_hdu

    see also
    --------
    `dev_pgcenter.find_pupilghost_center`

    """

    #
    # Check if this extension is included in the pupilghost template
    #
    extname = input_hdu.header['EXTNAME']
    right_ext = -1
    for this_ext in range(1, len(pupil_hdu)):
        if (pupil_hdu[this_ext].header['EXTNAME'] == extname):
            right_ext = this_ext
            break

    if (right_ext < 0):
        # This extension is not listed in the pupil-ghost template
        # We can't do anythin in this case, so let's simply return
        input_hdu.header['PGAFCTD'] = (False, "is the OTA affected by the pupilghost")
        return

    #
    # Set the coordinates of the center of the pupilghost 
    #
    # Read the center coordinates from the pupil ghost template file
    source_center_coords = 'data'
    if (source_center_coords == 'data'):
        fx, fy, fr, vx, vy, vr = dev_pgcenter.find_pupilghost_center(input_hdu, verbose=False)
        center_x, center_y = vx, vy
    #
    # Use center coordinates from header
    elif (source_center_coords == 'header'):
        # if ("PGCNTR_X" in input_hdu.header): 
        #     center_x = input_hdu.header['PGCNTR_X']
        # if ("PGCNTR_Y" in input_hdu.header): 
        #     center_y = input_hdu.header['PGCNTR_Y']

        if ('PGEFCTVX' in input_hdu.header):
            center_x = input_hdu.header['PGEFCTVX']
        if ('PGEFCTVX' in input_hdu.header):
            center_x = input_hdu.header['PGEFCTVX']
    #
    # by default, resort to the old-fashioned canned values
    else:
        if (filtername in pupilghost_centers):
            if (extname in pupilghost_centers[filtername]):
                print pupilghost_centers[filtername][extname]
                center_x, center_y = pupilghost_centers[filtername][extname]
            else:
                if (extname in pupilghost_centers):
                    center_x, center_y = pupilghost_centers[extname]
                else:
                    # Don't know what center coordinate to use, abort
                    return
        elif (extname in pupilghost_centers):
            center_x, center_y = pupilghost_centers[extname]
        else:
            # Don't know what center coordinate to use, abort
            return

    #
    # Now we know we have to do something
    #
    if (verbose): 
        print "Found matching pupil ghost template in extension",right_ext
    print "Using center coordinates", center_x, center_y," for data frame"

    if (rotate):
        # print "___%s___" % rotator_angle
        if (rotator_angle == "unknown"):
            rotator_angle = 0.0

        # Rotate to the right angle
        # Make sure to rotate opposite to the rotator angle since we rotate 
        # the correction and not the actual data
        template = pupil_hdu[right_ext].data
        # Replace all NaNs with zeros
        template[numpy.isnan(template)] = 0.

        if (math.fabs(rotator_angle) < 0.5):
            if (verbose): print "Rotator angle is small (%.2f), skipping rotation" % (rotator_angle)
            rotated = template
        else:
            if (verbose): print "rotating template by",rotator_angle,"degrees"
            rotated = rotate_around_center(template, rotator_angle, mask_nans=False)
    else:
        if (verbose): print "No rotation requested, skipping rotation"
        rotated = pupil_hdu[right_ext].data
     
   
    template_centerx, template_centery = rotated.shape[0]/2, rotated.shape[1]/2
    if (source_center_coords == 'data'):
        #
        # Ok, now we have the pupil ghost rotated to the right angle
        #
        data_shape = input_hdu.data.shape

        # Now extract the right quadrant from the pupilghost template
        quadrant = {'OTA33.SCI': [0,4500,0,4500],
                    'OTA34.SCI': [0,4500,4500,9000],
                    'OTA44.SCI': [4500,9000,4500,9000],
                    'OTA43.SCI': [4500,9000,0,4500],
                }
        quadrant = {'OTA33.SCI': [400,4500,400,4500],
                    'OTA34.SCI': [400,4500,4500,8600],
                    'OTA44.SCI': [4500,8600,4500,8600],
                    'OTA43.SCI': [4500,8600,400,4500],
                }
        xys = quadrant[extname]
        template_quadrant = rotated[xys[2]:xys[3], xys[0]:xys[1]]
        # Now we have the right quadrant, search for center position in template
        imghdu = pyfits.ImageHDU(data=template_quadrant)
        imghdu.header['EXTNAME'] = extname
        pyfits.HDUList([pyfits.PrimaryHDU(), imghdu]).writeto("template_%s.fits" % extname, clobber=True)
        tx, ty, _, _, _, _ = dev_pgcenter.find_pupilghost_center(imghdu, verbose=False,
                                                                 fixed_radius=vr)
        print "Found pg center at",tx, ty
        
        template_centerx, template_centery = tx+xys[0], ty+xys[2]
        print "Using",template_centerx, template_centery, "as center coordinates for template"
        # center_x, center_y = vx, vy
        
        # Swap x/y since python does it too
        print "rot.shape=",rotated.shape

 
    bx = template_centerx - center_x
    by = template_centery - center_y
    tx, ty = bx + data_shape[0], by + data_shape[1]

    correction = rotated[by:ty, bx:tx]
    correction[numpy.isnan(correction)] = 0.

    if (non_negative):
        correction[correction < 0] = 0

    input_hdu.data -= (correction * scaling)

    # Store the position of the pupil ghost center
    input_hdu.header['PGAFCTD'] = (True, "is the OTA affected by the pupilghost")
    input_hdu.header['PGCENTER'] = "%d %d" % (center_x, center_y)
    input_hdu.header['PGCNTR_X'] = (center_x, 'pupil ghost center x')
    input_hdu.header['PGCNTR_Y'] = (center_y, 'pupil ghost center y')
    input_hdu.header['PGTMPL_X'] = (template_centerx, 'pupil ghost template center x')
    input_hdu.header['PGTMPL_Y'] = (template_centery, 'pupil ghost template center y')
    input_hdu.header['PGREG_X1'] = (bx, "matched region of pupilghost, left")
    input_hdu.header['PGREG_X2'] = (tx, "matched region of pupilghost, right")
    input_hdu.header['PGREG_Y1'] = (by, "matched region of pupilghost, bottom")
    input_hdu.header['PGREG_Y2'] = (ty, "matched region of pupilghost, top")
    input_hdu.header['PGEFCTVX'] = (center_x - template_centerx + rotated.shape[1]/2, "effective pupilghost center X")
    input_hdu.header['PGEFCTVY'] = (center_y - template_centery + rotated.shape[0]/2, "effective pupilghost center Y")
    input_hdu.header['PGSCALNG'] = (scaling, "pupil ghost template scaling")
    input_hdu.header['PGROTANG'] = (rotator_angle, "pupil ghost rotator angle")

    if (verbose): print "all done, going home!"
    return input_hdu




def subtract_pupilghost(input_hdu, pupil_hdu, scaling, rotate=True, verbose=True,
                        source_center_coords='data',
                        ):
    """
    This is a wrapper around the subtract_pupilghost_extension routine,
    going through all the extensions that might have a pupil ghost.
    """
    
    # Add some parallelization here

    # Now go through each of the HDUs in the data frame and correct the pupil ghost
    for i in range(1, len(input_hdu)):
        if (not is_image_extension(input_hdu[i])):
            continue

        rotator_angle = input_hdu[0].header['ROTSTART'] if (rotate) else 0.
        filtername = input_hdu[0].header['FILTER']

        # Perform pupilghost removal on a single extension
        # simple hand on all parameters
        subtract_pupilghost_extension(input_hdu[i], rotator_angle, filtername, pupil_hdu, 
                                      rotate=rotate, 
                                      scaling=scaling, 
                                      verbose=verbose, 
                                      source_center_coords=source_center_coords)

    return input_hdu



def create_azimuthal_template(filename, outputfilename):
    """
    This routine will read the full pupilghost template and create 
    a radial profile by averaging out the azimuthal variations. This 
    radial pupil template will then be used in collectcells to remove 
    the pupil ghost from science frames.
    """

    # Open file and extract data
    # Things here are simple, since the file should only have the primary 
    # and one image extension
    hdulist = pyfits.open(filename)
    raw_data = hdulist[1].data

    binning = 1
    import podi_fitpupilghost
    data, radius, angle = podi_fitpupilghost.get_radii_angles(raw_data, (4500,4500), binfac=binning)

    pupilsub, radial_profile, pupil_radial_2d = \
        podi_fitpupilghost.fit_radial_profile(data, radius, angle, data, (500, 4180, 10), binfac=binning, 
                                              verbose=True, show_plots=True,
                                              force_positive=False, zero_edges=False,
                                              save_profile=outputfilename[:-5]+".profile.dat")

    # pyfits.writeto("radial_profile.fits", radial_profile)
    # pyfits.writeto("pupilsub.fits", pupilsub, clobber=True)
    # pyfits.writeto("pupil_radial_2d.fits", pupil_radial_2d, clobber=True)

    hdulist[1].data = pupil_radial_2d
    
    clobberfile(outputfilename)
    hdulist.writeto(outputfilename)

    return


def get_pupilghost_scaling(science_frame, pupilghost_frame, 
                n_samples=750, boxwidth=20, 
                verbose=True):
    """Find the optimum scaling for the pupil ghost. This is done by sampling the
    image frame and the pupil ghost template at a range of identical
    positions. The median ratio between these measurements then yields the
    scaling ratio.

    Parameters
    ----------
    
    science_frame : string or HDUList

        If science frame is a string, it is interpreted as the filename of the
        science frame for which we are to obtain the scaling. Alternatively you
        can also pass the HDUList of the science frame.

    pupilghost_template : string of HDUList

        same as above, just for the pupil-ghost template

    n_samples : int

        Number of intensity samples to take *from each OTA* when deriving the
        optimum scaling factor.

    boxwidth : int
 
        Size of the sample box, in pixels

    Returns
    -------

    median_scaling_factor

    standard deviation of scaling factor

    """

    logger = logging.getLogger("GetPupilghostScaling")

    sci_hdulist = pyfits.open(science_frame) if (type(science_frame) == str) else science_frame
    pg_hdulist = pyfits.open(pupilghost_frame) if (type(pupilghost_frame) == str) else pupilghost_frame

    merged_all = numpy.zeros(shape=(0,6))

    any_affected = False

    for ext in range(1,len(science_frame)):
        extname = sci_hdulist[ext].header['EXTNAME']
        filter = sci_hdulist[0].header['FILTER']
        
        logger.debug("Checking extension %s (filter: %s) for pupilghost effects" % (extname, filter))

        if (not 'PGAFCTD' in sci_hdulist[ext].header or not sci_hdulist[ext].header['PGAFCTD']):
            # This frame does not contain the keyword labeling it as affected by
            # the pupilghost. In that case we don't need to do anything
            logger.debug("This extension (%s) does not have any pupilghost problem" % (extname))
            continue

#        pupilghost_affected = sci_hdulist[ext].header['PGAFCTD']
#        if (not pupilghost_affected):
#            continue

        logger.debug("Checking pupilghost center position")

        # Try to find the center position of the pupilghost from the science
        # frame. The necessary headers should have been inserted during 
        # flat-field correction
        if ('PGEFCTVX' in sci_hdulist[ext].header and 
            'PGEFCTVY' in sci_hdulist[ext].header):
            
            center = (sci_hdulist[ext].header['PGEFCTVX'], 
                      sci_hdulist[ext].header['PGEFCTVY'])

        else:
            logger.debug("Couldn't find a pupilghost center, skipping rest of work")
            continue

        any_affected = True

        data = sci_hdulist[ext].data
        pg = pg_hdulist[extname].data
        
        #n_samples = 1750
        logger.debug("Getting sky-samples for science frame")
        samples = numpy.array(podi_fitskybackground.sample_background(data, None, None, 
                                                          min_found=n_samples, fit_regions=[], 
                                                          boxwidth=boxwidth))

        if (samples.shape[0] <= 0):
            logger.debug("Couldn't find enough sky samples, skipping OTA %s" % (extname))
            continue

        box_centers = samples[:,2:4]
        #print box_centers.shape

        # Now convert the x/y from the science frame 
        # into x/y in the pupil ghost frame
        dxy = box_centers - center
        pg_xy = dxy + [ 0.5*pg.shape[0], 0.5*pg.shape[1] ]

        #print dxy[0:10,:]
        #print pg_xy[0:10,:]

        #print pg_samples.shape
        #print pg_xy.shape
        logger.debug("Getting sky-samples for pupilghost template")
        pg_samples =  numpy.array(podi_fitskybackground.sample_background(pg, None, None, 
                                                                          fit_regions=[],
                                                             box_center=pg_xy))
        if (pg_samples.shape[0] <= 0):
            logger.debug("Couldn't find enough pg.template samples, skipping OTA %s" % (extname))
            continue

#        pg_samples = podi_fitskybackground.sample_background(pg, None, None, 
#                                                             box_center=box_centers)

        #print pg_samples.shape

        #continue

        ri = 400
        ro = 3300
        radius = numpy.sqrt(numpy.sum( dxy**2, axis=1))
        #print radius[0:10]

        #print extname
        #print center

        # numpy.savetxt("xxx", samples)
        # numpy.savetxt("yyy", pg_samples)

        # unaffected data points inside or outside the pupil ghost
        unaffected = (radius < ri) | (radius > ro)
        skylevel = numpy.median(samples[:,4][unaffected])
        logger.debug("Found background level not affected by PG: %.1f" % (skylevel))

        # derive maximum intensity of pupil ghost 
        # better: read from file
        pg_max = numpy.max(pg_samples[:,4])
        logger.debug("Maximum intensity of pupilghost: %f" % (pg_max))

        # Now merge the two arrays:
        merged = numpy.empty(shape=(pg_xy.shape[0],6))
        merged[:,0:2] = samples[:,2:4]
        merged[:,2:4] = pg_samples[:,2:4]
        merged[:,4] = numpy.array(samples)[:,4] - skylevel
        merged[:,5] = numpy.array(pg_samples)[:,4]
        # numpy.savetxt("zzz", merged)

        ratio = merged[:,4] / merged[:,5]
        logger.debug("simple ratio science/template (ota %s): %f" % (extname, numpy.median(ratio)))

        strong_pg_signal = merged[:,5] > 0.4*pg_max
        valid_ratios = ratio[strong_pg_signal]
        median_ratio = numpy.median(valid_ratios)
        uncert_ratio = numpy.std(valid_ratios)

        logger.debug("ratio for strong pg pixels (%d samples): %f +/- %f" % (
            numpy.sum(strong_pg_signal), median_ratio, uncert_ratio))

        # Only merge the samples with sufficient pupilghost signal
        good_samples = merged[strong_pg_signal]
        if (good_samples.shape[0] > 0):
            logger.debug("Adding %d pg samples from ota %s to global list" % (good_samples.shape[0], extname))
            merged_all = numpy.append(merged_all, good_samples, axis=0)

        # numpy.savetxt("merged%s" % (extname), merged[strong_pg_signal])

    if (any_affected):
        # print "\n\n============================\n\n"
        ratio = merged_all[:,4] / merged_all[:,5]

        pg_max = numpy.max(merged_all[:,5])
        # strong_pg_signal = merged_all[:,5] > 0.4*pg_max

        # valid_ratios = ratio[strong_pg_signal]

        numpy.savetxt("pgsamples.all", merged_all)

        good_ratios, valid = three_sigma_clip(ratio, return_mask=True) #[strong_pg_signal])
        numpy.savetxt("pgsamples.valid", merged_all[valid])


        median_ratio = numpy.median(valid_ratios)
        logger.debug("median_ratio = %f" % (median_ratio))
        logger.debug("error = %f" % (numpy.std(valid_ratios)))
        logger.debug("clipped median: %f" % (numpy.median(good_ratios)))
        logger.debug("clipped std: %f" % (numpy.std(good_ratios)))

        numpy.savetxt("merged_all", merged_all)
        numpy.savetxt("merged_clipped", good_ratios)

        clipped_median = numpy.median(good_ratios)
        clipped_std = numpy.std(good_ratios)
        return any_affected, clipped_median, clipped_std

    return any_affected, -1., -1.








if __name__ == "__main__":

    options = read_options_from_commandline(None)
    podi_logging.setup_logging(options)

    if (len(sys.argv) <= 1 or sys.argv[1] == "-help"):
        #print help('podi_matchpupilghost')
        import podi_matchpupilghost as me
        print me.__doc__

    elif (cmdline_arg_isset("-makeradial")):
        inputframe = get_clean_cmdline()[1]
        outputframe = get_clean_cmdline()[2]
        create_azimuthal_template(inputframe, outputframe)

    elif (cmdline_arg_isset("-getscaling")):
        science_frame = get_clean_cmdline()[1]
        pupilghost_frame = get_clean_cmdline()[2]
        #get_scaling(science_frame, pupilghost_frame)

        sci_hdu = pyfits.open(science_frame)
        pg_hdu = pyfits.open(pupilghost_frame)
        get_pupilghost_scaling(sci_hdu, pg_hdu)
      
    elif (cmdline_arg_isset("-cleanpupilghost")):
        science_frame = get_clean_cmdline()[1]
        pupilghost_frame = get_clean_cmdline()[2]
        output_frame = get_clean_cmdline()[3]
        #get_scaling(science_frame, pupilghost_frame)

        sci_hdu = pyfits.open(science_frame)
        pg_hdu = pyfits.open(pupilghost_frame)
        scaling, scale_std = get_pupilghost_scaling(sci_hdu, pg_hdu)
        subtract_pupilghost(sci_hdu, pg_hdu, scaling=scaling, rotate=False)
        
        sci_hdu.writeto(output_frame, clobber=True)

    else:
        # Read filenames from command line
        inputframe = sys.argv[1]
        pupilghost_template = sys.argv[2]

        # and open all fits files
        input_hdu = pyfits.open(inputframe)
        pupil_hdu = pyfits.open(pupilghost_template)

        scaling = 1.0
        if (len(sys.argv) > 4):
            scaling = float(sys.argv[4])
        print "using scaling factor",scaling

        subtract_pupilghost(input_hdu, pupil_hdu, scaling=scaling, 
                            source_center_coords='precomp',
                            rotate=False)

        # Now, using the rotation angle given in the input frame, 
        # rotate and extract the pupil ghost sections for each of the OTAs.
        # And finally apply the correction
        #hdu_matched = subtract_pupilghost(input_hdu, pupil_hdu, scaling)


        output_filename = sys.argv[3]
        input_hdu.writeto(output_filename, clobber=True)

    # Shutdown logging to shutdown cleanly
    podi_logging.shutdown_logging(options)
