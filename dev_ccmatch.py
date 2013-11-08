#!/usr/bin/env python


import sys
import numpy
import os
import pyfits
import datetime
import scipy
import scipy.stats
import math
import scipy.spatial
import itertools

from  podi_definitions import *
import podi_search_ipprefcat
from podi_wcs import *

max_pointing_error = 3.

def count_matches(src_cat, ref_cat, 
                  matching_radius=(max_pointing_error/60.), 
                  fine_radius=(4./3600.), debugangle=None):

    # 
    # Now loop over all stars in the source catalog and find nearby stars in the reference catalog
    # Use a rather large matching radius for this step
    #
    # matching_radius = 1./60. # 1 arcmin
    ref_tree = scipy.spatial.cKDTree(ref_cat)

    src_tree = scipy.spatial.cKDTree(src_cat)

    # print "\n\n\nIn count_matches:"
    # print "src-cat:",src_cat.shape
    # print "ref-cat:",ref_cat.shape

    # find all matches
    matches = src_tree.query_ball_tree(ref_tree, matching_radius, p=2)
    # also count how many matches in total we have found
    n_matches = src_tree.count_neighbors(ref_tree, matching_radius, p=2)

    all_offsets = numpy.zeros(shape=(n_matches,2))
    cur_pair = 0

    # dummy = open("ccmatch.offsets.%d" % int(round((debugangle*60),0)), "w")

    for cur_src in range(len(matches)):
        if (len(matches[cur_src]) <= 0):
            continue

        #if (verbose): print "\n",cur_src
        # print matches[cur_src]
        #
        # matches[cur_src] contains the indices of matching stars from the reference catalog
        # So extract the actual coordinates of all nearby reference stars
        #
        cur_matches = numpy.array(ref_cat[matches[cur_src]])
        #if (verbose): print cur_matches

        # print cur_matches.shape

#        matches[cur_src] -= src_cat[cur_src]

        # Subtract the source position to get relative offsets
        cur_matches -= src_cat[cur_src]
        #if (verbose): print cur_matches
      
        #numpy.savetxt(dummy, cur_matches)
        #print >>dummy, "\n\n\n\n\n"

        # And add all offsets into the global offset registry
        for cur_refstar in range(len(matches[cur_src])):
            all_offsets[cur_pair,:] = cur_matches[cur_refstar]
            cur_pair += 1

    all_offsets = all_offsets[:cur_pair,:]
    # print "found", all_offsets.shape, "potential offsets", cur_pair, n_matches

    numpy.savetxt("ccmatch.dump",all_offsets)

    # 
    # At this stage, we have a catalog of all potential offsets, 
    # so we now need to figure out which one is the most likely,
    # i.e. the most frequently occuring
    #

    candidate_offset_tree = scipy.spatial.cKDTree(all_offsets)

    # print all_offsets.shape

    n_coincidences = candidate_offset_tree.count_neighbors(candidate_offset_tree, fine_radius, p=2)
    coincidences = candidate_offset_tree.query_ball_tree(candidate_offset_tree, fine_radius, p=2)

    search_weights = numpy.zeros(shape=(len(coincidences),3))

    for i in range(len(coincidences)):
        search_weights[i,0] = len(coincidences[i])
        search_weights[i,1:3] = all_offsets[i,:]

    # search_weights = numpy.zeros(shape=(all_offsets.shape[0],3))
    # search_weights[:,1:3] = all_offsets
    # for i in range(all_offsets.shape[0]):
    #     neighbors = candidate_offset_tree.query_ball_point(search_weights[i,1:3], 1e-8, p=2)
    #     search_weights[i,0] = len(neighbors)
    #     #search_weights[i,0] = candidate_offset_tree.count_neighbors(
    #     #    scipy.spatial.cKDTree(search_weights[i,1:3]), (5./3600.), p=2)

    # Find which offset has the highest weight
    max_coincidence_count = numpy.argmax(search_weights[:,0])

    best_offset = all_offsets[max_coincidence_count,:]
    print "best offset", best_offset
    print "matching in",search_weights[max_coincidence_count],"fields"

    if (not debugangle == None):
        numpy.savetxt("ccmatch.offsetcount.%d" % int(round((debugangle*60),0)), search_weights)

    return search_weights[max_coincidence_count,0], best_offset


def rotate_shift_catalog(src_cat, center, angle, shift=None, verbose = False):
    
    if (verbose):
        print "\n\n\nIn rotate_shift_catalog"
        print "angle =", angle
        print "shift =", shift
        print "center =", center
        print "src-cat=\n", src_cat[:3]

    center_ra, center_dec = center
    # print center_ra, center_dec

    src_rotated = numpy.zeros_like(src_cat)
    src_rel_to_center = src_cat - [center_ra, center_dec] 
    if (not shift == None):
        src_rel_to_center += shift

    # print "\n\n\nDuring rotation"
    # print "src-cat=\n",src_cat[:5,:]
    # print "src-cat rel to center=\n",src_rel_to_center[:5,:]
    # print "rotation end...\n\n"

    # angles are given in arcmin
    angle_rad = math.radians(angle)
    if (verbose): print "angle radians =",angle_rad

    # print "in rot_shift: angle-rad=",angle_rad

    if (not shift == None):
        print "@@@@ shift rotation"
        print "shift=", shift
        print "angle=", angle*60, "arcmin"
        print "X=",math.cos(angle_rad) * shift[0] - math.sin(angle_rad) * shift[1]
        print "y=",math.sin(angle_rad) * shift[0] + math.cos(angle_rad) * shift[1]

    src_rotated[:,0] \
        = math.cos(angle_rad) * src_rel_to_center[:,0] \
        - math.sin(angle_rad) * src_rel_to_center[:,1] \
        + center_ra
    src_rotated[:,1] \
        = math.sin(angle_rad) * src_rel_to_center[:,0] \
        + math.cos(angle_rad) * src_rel_to_center[:,1] \
        + center_dec
    
    if (verbose): print "src_rotated=\n", src_rotated[:3]

#    if (not shift == None):
#        if (verbose): print "applying shift", shift
#        src_rotated += shift

    if (verbose): print "src-final=\n", src_rotated[:3],"\n\n\n"
        
    return src_rotated

def kd_match_catalogs(src_cat, ref_cat, matching_radius, max_count=1):

    src_tree = scipy.spatial.cKDTree(src_cat[:,0:2])
    ref_tree = scipy.spatial.cKDTree(ref_cat[:,0:2])

    # print src_cat[0:5]
    # print ref_cat[0:5]

    # Create an array to hold the matched catalog
    output_cat = numpy.empty(shape=(src_cat.shape[0], src_cat.shape[1]+ref_cat.shape[1]))
    # and insert the source catalog
    n_src_columns = src_cat.shape[1]
    output_cat[:,0:n_src_columns] = src_cat

    # print output_cat[0:5]

    # also create an array holding for which sources we found a match
    match_found = numpy.zeros(shape=(src_cat.shape[0]))

    # match the catalogs using a kD-tree
    match_indices = src_tree.query_ball_tree(ref_tree, matching_radius, p=2)

    # print src_tree.count_neighbors(ref_tree, matching_radius, p=2)

    # Now loop over all matches and merge the found matches
    for cur_src in range(src_cat.shape[0]):

        # Determine how many reference stars are close to this source
        # Do not keep match if none or too many reference stars are nearby
        n_matches = len(match_indices[cur_src])
        if (n_matches <= 0 or n_matches > max_count):
            continue
    
        output_cat[cur_src, n_src_columns:] = ref_cat[match_indices[cur_src][0]]
        match_found[cur_src] = 1

    # Now eliminate all sources without matches
    final_cat = output_cat[match_found == 1]

    return final_cat



def find_best_guess(src_cat, ref_cat,
                    center_ra, center_dec,
                    matching_radius=(max_pointing_error/60.),
                    angle_max=5., #degrees
                    d_angle=3, # arcmin
                    fine_radius=2./3600.
                    ):

    # 
    # Now loop over all stars in the source catalog and find nearby stars in the reference catalog
    # Use a rather large matching radius for this step
    #
    #matching_radius = 1./60. # 1 arcmin
    ref_tree = scipy.spatial.cKDTree(ref_cat)

    #angle_max = 2.
    #d_angle = 5.
    n_angles = int(math.ceil((2 * angle_max) / (d_angle / 60.))) + 1

    all_results = numpy.zeros(shape=(n_angles, 4))

    all_results[:,0] = numpy.linspace(-angle_max, angle_max, n_angles)
    for cur_angle in range(n_angles):

        angle = all_results[cur_angle,0]
        # print "\n\n\n",angle*60

        src_rotated = rotate_shift_catalog(src_cat, (center_ra, center_dec), angle, None)
        # print "src-cat:",src_cat.shape
        # print "src_roated:",src_rotated.shape
        # print "ref-cat:",ref_cat.shape

        # angle_rad = math.radians(angle)

        # src_rotated = numpy.zeros_like(src_cat)
        # src_rel_to_center = src_cat - [center_ra, center_dec]
        # src_rotated[:,0] \
        #     = math.cos(angle_rad) * src_rel_to_center[:,0] \
        #     + math.sin(angle_rad) * src_rel_to_center[:,1] \
        #     + center_ra
        # src_rotated[:,1] \
        #     = -math.sin(angle_rad) * src_rel_to_center[:,0] \
        #     +  math.cos(angle_rad) * src_rel_to_center[:,1] \
        #     + center_dec

        n_matches, offset = count_matches(src_rotated, ref_cat, matching_radius, 
                                          fine_radius=fine_radius,
                                          debugangle=angle)

        all_results[cur_angle,1] = n_matches
        all_results[cur_angle,2:4] = offset

    numpy.savetxt(sys.stdout, all_results)
    numpy.savetxt("ccmatch.allresults", all_results)


    #
    # Now find the best solution (the one with the highest matched star density)
    #
    idx_best_angle = numpy.argmax(all_results[:,1])

    best_guess = all_results[idx_best_angle]
    print best_guess, "angle=",best_guess[0]*60.,"arcmin"


    return best_guess





def fit_best_rotation_shift(src_cat, ref_cat, 
                            best_guess,
                            center_ra, center_dec,
                            matching_radius=(6./3600.)
                            ):

    src_rotated = rotate_shift_catalog(src_cat, 
                                       (center_ra, center_dec), 
                                       angle=best_guess[0], 
                                       shift=best_guess[2:4])

    numpy.savetxt("ccmatch.roughalign", src_rotated)

    # Match up stars
    ref_tree = scipy.spatial.cKDTree(ref_cat)
    src_tree = scipy.spatial.cKDTree(src_rotated)
    # matching_radius = 3./3600.

    matched_src_ref_idx = src_tree.query_ball_tree(ref_tree, matching_radius, p=2)

    src_ref_pairs = numpy.ones(shape=(src_rotated.shape[0],4))
    src_ref_pairs[:,0:2] = src_rotated[:,0:2]
    src_ref_pairs[:,2:4] = numpy.NaN

    #
    # Merge the two catalogs to make fitting easier
    #
    for i in range(len(matched_src_ref_idx)):
        # Ignore all points with no or more than 1 closest match
        n_close_stars = len(matched_src_ref_idx[i])
        if (not n_close_stars == 1):
            continue

        src_ref_pairs[i, 2:4] = ref_cat[matched_src_ref_idx[i][0]]

    numpy.savetxt("ccmatch.srcrefmatched", src_ref_pairs)

    #
    # Further optimize the rotation angle by introducing the 
    # shift and rotation as free parameters and fitting to minimize 
    # the deviations
    #

    def difference_ref_src_catalogs(src, ref, declination):
        diff = src - ref
        diff[:,0] *= math.cos(math.radians(declination))
        distance = numpy.hypot(diff[:,0], diff[:,1])
        # return diff.ravel() #stance
        return distance

    # Optimize rotation angle by fitting offsets with rotation as a free parameter
    def optimize_rotation_angle(p, src, ref, center):
        ra, dec = center
        # print p
        src_rotated = rotate_shift_catalog(src, center, 
                                          angle=p[0], 
                                          shift=p[1:2])
        return difference_ref_src_catalogs(src_rotated, ref, dec)

    r_mismatch = difference_ref_src_catalogs(src_ref_pairs[:,0:2], src_ref_pairs[:,2:4], center_dec)

    p_init = [best_guess[0], best_guess[2], best_guess[3]]
    print p_init

    x_rotated = rotate_shift_catalog(src_cat, (center_ra, center_dec), 
                                     angle=best_guess[0], shift=best_guess[2:4])

    def difference_source_reference_cat(p, src_cat, ref_cat, center, for_fitting=False):
        src_rotated = rotate_shift_catalog(src_cat, center, 
                                           angle=p[0], 
                                           shift=p[1:3])
        diff = src_rotated - ref_cat
        if (for_fitting):
            return diff.ravel()

        return diff


    numpy.savetxt("ccmatch.x_rotated", x_rotated)

    numpy.savetxt("ccmatch.r_mismatch", r_mismatch)

    center_radec = (center_ra, center_dec)
    diff = difference_source_reference_cat(p_init, 
                                           src_cat, # src-cat
                                           src_ref_pairs[:,2:4],  # matched ref-cat 
                                           center_radec)
    numpy.savetxt("ccmatch.diff", diff)


    # 
    # Eliminate all source stars without nearby/unique 
    # match in the reference catalog
    #

    valid_matches = numpy.isfinite(src_ref_pairs[:,2])
    matched_src = src_cat[valid_matches]
    matched_ref = src_ref_pairs[:,2:4][valid_matches]

    # diff2 = difference_source_reference_cat(p_init, 
    #                                         matched_src, 
    #                                         matched_ref, 
    #                                         center_radec, 
    #                                         for_fitting=False)
    # numpy.savetxt("ccmatch.diff2", diff2)

    args = (matched_src, matched_ref, center_radec, True)
    fit = scipy.optimize.leastsq(difference_source_reference_cat, 
                                 p_init, 
                                 args=args, 
                                 full_output=1)

    best_fit = fit[0]

    # print "\n\nbefore/after fit"
    # print p_init
    # print fit[0]
    # # Compute uncertainty on the shift and rotation
    # uncert = numpy.sqrt(numpy.diag(fit[1]))
    # print uncert
    # best_shift_rotation_solution = fit[0]


    diff_afterfit = difference_source_reference_cat(fit[0], 
                                                    matched_src, 
                                                    matched_ref, 
                                                    center_radec, 
                                                    for_fitting=False)
    
    numpy.savetxt("ccmatch.diff_afterfit", diff_afterfit)

    return best_fit




if __name__ == "__main__":
    verbose=False

    mode = cmdline_arg_set_or_default('-mode', 'xxx')
    print mode

    valid_mode = (mode == "shift" or mode == "rotation" or mode == "distortion")
    if (not valid_mode):
        print """\
This mode is not known.
Valid modes are only
  * shift
  * rotation
  * distortion
"""
        sys.exit(0)

    outputfile = sys.argv[4]

    # Load the source catalog file
    src_catfile = sys.argv[1]
    src_raw = numpy.loadtxt(src_catfile)

    #
    # For testing purposes, rotate the field by a little
    #
    testing = False
    if (testing):
        angle = 7./60. # 10 arcmin
        center_ra = numpy.median(src_raw[:,0])
        center_dec = numpy.median(src_raw[:,1])
        src_xxx = rotate_shift_catalog(src_raw[:,0:2], (center_ra, center_dec), angle, [0.01, -0.005])
        src_raw[:,0:2] = src_xxx

    # eliminate all flagged stars
    src_cat = src_raw[src_raw[:,7] == 0][:,0:2]

    print "src_cat:",src_cat.shape

    # 
    # Create the reference catalog
    #
    ref_catfile = sys.argv[2]
    ref_raw = numpy.loadtxt(ref_catfile)[:,0:2]
    print "ref. cat (raw) =",ref_raw.shape


    #
    # Reduce the reference catalog to approx. the coverage of the source catalog
    #
    ref_cat = match_catalog_areas(src_cat, ref_raw, max_pointing_error/60.)
    print "area matched ref. catalog:", ref_cat.shape



    inputframe = sys.argv[3]
    print "optimizing rotation in frame",inputframe
    
    hdulist = pyfits.open(inputframe)
    # hdulist.info()

  

    #
    # compute the center of the field
    #
    center_ra = hdulist[1].header['CRVAL1'] #numpy.median(src_cat[:,0])
    center_dec = hdulist[1].header['CRVAL2'] #numpy.median(src_cat[:,1])
    print "field center at ", center_ra, center_dec

    current_best_rotation = 0
    current_best_shift = [0.,0.]

    if (mode == "shift"):
        best_guess = find_best_guess(src_cat, ref_cat,
                                     center_ra, center_dec,
                                     matching_radius=(max_pointing_error/60.),
                                     angle_max=0.00001, #degrees
                                     d_angle=3 # arcmin
                                     )
        print "\n\n\n\n\n found best guess:"
        print best_guess
        print best_guess[2:4]*3600.
        print "\n\n\n\n\n"

        hdulist[0].header['WCS1_DA'] = (best_guess[0], "WCS calib best guess angle")
        hdulist[0].header['WCS1_DRA'] = (best_guess[2], "WCS calib best guess d_RA")
        hdulist[0].header['WCS1_DDE'] = (best_guess[3], "WCS calib best guess d_DEC")
        hdulist[0].header['WCS1_N'] = (best_guess[1], "WCS calib best guess # matches")

        # Now apply this shift to the output file and write results

        for ext in range(len(hdulist)):
            if (not is_image_extension(hdulist[ext])):
                continue
            ota_extension = hdulist[ext]
            wcs_poly = header_to_polynomial(ota_extension.header)
            wcs_poly = wcs_apply_shift(wcs_poly, best_guess[2:4])
            wcs_wcspoly_to_header(wcs_poly, ota_extension.header)
        print "writing results ..."
        hduout = pyfits.HDUList(hdulist[0:2])
        hduout.writeto(outputfile, clobber=True)

        # For testing, apply correction to the input catalog, 
        # match it to the reference catalog and output both to file
        src_rotated = rotate_shift_catalog(src_cat[:,0:2], (center_ra, center_dec), 
                                           angle=0.,
                                           shift=best_guess[2:4],
                                           verbose=False)
        matched = kd_match_catalogs(src_rotated, ref_cat, matching_radius=(2./3600.), max_count=1)
        numpy.savetxt("ccmatch.after_shift", matched)

        sys.exit(0)

    #
    #   |
    #   |
    #   |   This is the end of computing for mode="shift"
    #  \1/  The code below optimizes rotation and possibly distortion
    #   "
    #

    #
    # Find 1st order best guess
    #
    best_guess = find_best_guess(src_cat, ref_cat,
                                 center_ra, center_dec,
                                 matching_radius=(max_pointing_error/60.),
                                 angle_max=4, #degrees
                                 d_angle=3 # arcmin
                                 )
    print "\n\n\n\n\n found best guess:"
    print best_guess
    print best_guess[2:4]*3600.
    print "\n\n\n\n\n"

    # hdulist[0].header['WCS1_DA'] = best_guess[0]
    # hdulist[0].header['WCS1_DRA'] = best_guess[2]
    # hdulist[0].header['WCS1_DDE'] = best_guess[3]
    # hdulist[0].header['WCS1_N'] = best_guess[1]
    hdulist[0].header['WCS1_DA'] = (best_guess[0], "WCS calib best guess angle")
    hdulist[0].header['WCS1_DRA'] = (best_guess[2], "WCS calib best guess d_RA")
    hdulist[0].header['WCS1_DDE'] = (best_guess[3], "WCS calib best guess d_DEC")
    hdulist[0].header['WCS1_N'] = (best_guess[1], "WCS calib best guess # matches")


    print "\n\n\n\n\nbest guess:\n",best_guess,"\n\n\n\n\n"

    current_best_rotation = best_guess[0]
    current_best_shift = best_guess[2:4]

    guessed_cat = rotate_shift_catalog(src_cat[:,0:2], (center_ra, center_dec), 
                                       angle=current_best_rotation,
                                       shift=current_best_shift,
                                       verbose=False)
    numpy.savetxt("ccmatch.guessed_cat", guessed_cat)

    guessed_match = kd_match_catalogs(guessed_cat, ref_cat, (5./3600), max_count=1)
    numpy.savetxt("ccmatch.guessed_match", guessed_match)
    

    # 
    # With this best guess at hand, match each star in the source 
    # catalog to a closest match in the reference catalog
    # 

    best_shift_rotation_solution = fit_best_rotation_shift(
        src_cat, ref_cat, best_guess,
        center_ra, center_dec,
        matching_radius=(5./3600.)
        )

    print "\n\n\n\n\nresulting fit solution:\n",best_shift_rotation_solution,"\n\n\n\n\n"

    src_rotated = rotate_shift_catalog(src_cat[:,0:2], (center_ra, center_dec), 
                                       angle=best_shift_rotation_solution[0],
                                       shift=best_shift_rotation_solution[1:3],
                                       verbose=False)
    matched = kd_match_catalogs(src_rotated, ref_cat, matching_radius=(2./3600.), max_count=1)
    numpy.savetxt("ccmatch.after_shift+rot", matched)


    current_best_rotation = best_shift_rotation_solution[0]
    current_best_shift = best_shift_rotation_solution[1:3]
    n_matches = numpy.sum(numpy.isfinite(matched[2]))

    hdulist[0].header['WCS1_DA'] = (best_guess[0], "WCS calib best guess angle")
    hdulist[0].header['WCS1_DRA'] = (best_guess[2], "WCS calib best guess d_RA")
    hdulist[0].header['WCS1_DDE'] = (best_guess[3], "WCS calib best guess d_DEC")
    hdulist[0].header['WCS1_N'] = (best_guess[1], "WCS calib best guess # matches")

    hdulist[0].header['WCS2_DA']  = (current_best_rotation, "WCS rot refi d_angle")
    hdulist[0].header['WCS2_DRA'] = (current_best_shift[0], "WCS rot refi r_RA")
    hdulist[0].header['WCS2_DDE'] = (current_best_shift[1], "WCS rot refi r_DEC")
    hdulist[0].header['WCS2_N']   = (n_matches, "WCS rot refi n_matches")


    if (mode == "rotation"):
        # We only asked for rotation optimization, so 
        # end the processing right here
        for ext in range(len(hdulist)):
            if (not is_image_extension(hdulist[ext])):
                continue
            ota_extension = hdulist[ext]
            wcs_poly = header_to_polynomial(ota_extension.header)
            wcs_poly = wcs_apply_rotation(wcs_poly, current_best_rotation)
            wcs_poly = wcs_apply_shift(wcs_poly, current_best_shift)
            wcs_wcspoly_to_header(wcs_poly, ota_extension.header)
        print "writing results ..."
        #hduout = pyfits.HDUList(hdulist[0:3])
        #hduout.append(hdulist[13])
        hduout = pyfits.HDUList(hdulist[0:5])
        hduout.writeto(outputfile, clobber=True)

        # For testing, apply correction to the input catalog, 
        # match it to the reference catalog and output both to file
        src_rotated = rotate_shift_catalog(src_cat[:,0:2], (center_ra, center_dec), 
                                           angle=current_best_rotation,
                                           shift=current_best_shift,
                                           verbose=False)
        matched = kd_match_catalogs(src_rotated, ref_cat, matching_radius=(2./3600.), max_count=1)
        numpy.savetxt("ccmatch.after_rotation", matched)
        sys.exit(0)


    #
    #   |
    #   |     All code below is to optimize
    #   |     the distortion within the frame
    #   |     Proceed with caution !!
    #  \1/
    #   "

    # 
    # Now we have the best fitting rotation and shift position.
    # In a next step, go ahead and refine the distortion in the frame
    # 
    print "\n\n\nOptimizing distortion..."
    print "Using initial guess", best_shift_rotation_solution

    # Apply the best-fit rotation to all coordinates in source catalog
    # src_raw = numpy.loadtxt(src_catfile)
    full_src_cat = src_raw.copy()
    numpy.savetxt("ccmatch.opt_src", full_src_cat)
    
    src_rotated = rotate_shift_catalog(full_src_cat[:,0:2], (center_ra, center_dec), 
                                       angle=current_best_rotation,
                                       shift=current_best_shift,
                                       verbose=True)

    numpy.savetxt("ccmatch.opt_rot", src_rotated)

    # Update the Ra/Dec in the full source catalog
    full_src_cat[:,0:2] = src_rotated[:,0:2]

    # Now we have the full source catalog, with better matching star coordinates
    # Next, eliminate all stars with flags
    valid_stars = full_src_cat[:,7] == 0
    valid_src_cat = full_src_cat[valid_stars]

    numpy.savetxt("ccmatch.opt_ref", ref_cat)
    numpy.savetxt("ccmatch.opt_valid", valid_src_cat)

    # diff = full_src_cat[:,0:2] - src_raw[:,0:2]
    # diff2 = src_rotated[:,0:2] - src_raw[:,0:2]
    # numpy.savetxt("ccmatch.opt_diff", diff)
    # numpy.savetxt("ccmatch.opt_diff2", diff2)


    #
    # Next we can do the actual coordinate matching between the source and 
    # reference star catalog
    #
    matched_catalog = kd_match_catalogs(valid_src_cat, ref_cat, matching_radius=(2./3600))
    numpy.savetxt("ccmatch.match_cat_for_distopt", matched_catalog)
    
    print "OTAs of each source:\n",matched_catalog[:,8]

    for ext in range(len(hdulist)):
        if (not is_image_extension(hdulist[ext])):
            continue

        ota_extension = hdulist[ext]
        # print ota_extension.header['FPPOS'], ota_extension.header['FPPOS'][2:4]
        ota = int(ota_extension.header['FPPOS'][2:4])
        print "\n\n\nworking on OTA %02d ..." %(ota)

        # sources from this OTA
        in_this_ota = (matched_catalog[:,8] == ota)
        print numpy.sum(in_this_ota)
        number_src_in_this_ota = numpy.sum(in_this_ota)

        # Read the WCS imformation from the fits file
        wcs_poly = header_to_polynomial(ota_extension.header)

        # And apply the best results for shift and rotation
        wcs_poly = wcs_apply_rotation(wcs_poly, best_shift_rotation_solution[0])
        wcs_poly = wcs_apply_shift(wcs_poly, best_shift_rotation_solution[1:3])


        if (number_src_in_this_ota < 15):
            print "Not enough stars to optimize distortion"
            wcs_poly_after_fit = wcs_poly

        else:

            # print in_this_ota
            # print matched_catalog[:,8]

            ota_cat = matched_catalog[in_this_ota]
            ota_ref = matched_catalog[in_this_ota][:,-2:] #31:33]

            print "sources in ota %d = %s ..." % (ota, str(ota_cat.shape))

            xi, xi_r, eta, eta_r, cd, crval, crpix = wcs_poly
            #numpy.savetxt(sys.stdout, xi, "%9.2e")
            #numpy.savetxt(sys.stdout, xi_r, "%9.2e")

            # wcs_poly = update_polynomial(wcs_poly, 
            #                              numpy.array([1.11, 2.22, 3.33, 4.44]), 
            #                              numpy.array([1.11, 2.22, 3.33, 4.44]), 
            #                              )

            # Read starting values from current WCS solution
            wcs_poly_to_arrays(wcs_poly)

            #
            # Now with the updated header, compute ra,dec from x,y
            #
            ra_dec = wcs_pix2wcs(ota_cat[:,2:4], wcs_poly)

            numpy.savetxt("ccmatch.true_radec.OTA%02d" % (ota), ota_cat[:,0:2])
            numpy.savetxt("ccmatch.computed_radec.OTA%02d" % (ota), ra_dec)

            xi, xi_r, eta, eta_r, cd, crval, crpix = wcs_poly
            xi[0,0] = 10000
            wcs_poly2 = xi, xi_r, eta, eta_r, cd, crval, crpix
            ra_dec2 = wcs_pix2wcs_2(ota_cat[:,2:4], wcs_poly2)
            numpy.savetxt("ccmatch.computed_radec2.OTA%02d" % (ota), ra_dec2)

            # sys.exit(0)

            xi, xi_r, eta, eta_r, cd, crval, crpix = wcs_poly
            print
            #numpy.savetxt(sys.stdout, xi, "%9.2e")
            #numpy.savetxt(sys.stdout, xi_r, "%9.2e")

            def optimize_distortion(p, input_xy, input_ref, wcs_poly, fit=True):
                n_params = p.shape[0] / 2
                p_xi = p[:n_params]
                p_eta = p[-n_params:]

                wcs_poly_for_fit = update_polynomial(wcs_poly, p_xi, p_eta)

                ra_dec_computed = wcs_pix2wcs(input_xy, wcs_poly_for_fit)
                diff = input_ref - ra_dec_computed
                if (not fit):
                    return diff
                print p_xi,p_eta,numpy.sum(diff**2)
                return diff.ravel()

            #
            # Determine initial guesses from the current wcs distortion
            #
            xi_1d, eta_1d = wcs_poly_to_arrays(wcs_poly)

            # For now, let's optimize only the first 4 factors
            n_free_parameters = 3 # or 4 or 7 or 12 or 17 or 24
            p_init = numpy.append(xi_1d[:n_free_parameters], eta_1d[:n_free_parameters])
            print p_init

            print "ota-cat=\n",ota_cat[:,2:4]
            print "ota-ref=\n",ota_ref

            diff = optimize_distortion(p_init, ota_cat[:,2:4], ota_ref, wcs_poly, fit=False)
            numpy.savetxt("ccmatch.optimize_distortion_before_OTA%02d" % (ota), diff)

            if (True):
                print "\n\n\n\n\n\n\nStarting fitting\n\n\n\n\n"
                args = (ota_cat[:,2:4], ota_ref, wcs_poly, True)
                fit = scipy.optimize.leastsq(optimize_distortion, 
                                             p_init, 
                                             args=args, 
                                             full_output=1)

                print "\n\n\n\n\n\n\nDone with fitting"
                print p_init
                print fit[0]
                print "\n\n\n\n\n"
                p_afterfit = fit[0]
            else:
                p_afterfit = p_init

            diff_after = optimize_distortion(p_afterfit, ota_cat[:,2:4], ota_ref, wcs_poly, fit=False)
            numpy.savetxt("ccmatch.optimize_distortion_after_OTA%02d" % (ota), diff_after)
        
            wcs_poly_after_fit = update_polynomial(wcs_poly, 
                                                   p_afterfit[:n_free_parameters],
                                                   p_afterfit[-n_free_parameters:]
                                                   )

        #
        # Make sure to write the updated WCS header back to the HDU
        # This is done even if not enough sources for distortion fitting were found
        #
        wcs_wcspoly_to_header(wcs_poly_after_fit, ota_extension.header)

    print "writing results ..."
    hduout = pyfits.HDUList(hdulist[0:3])
    hduout.append(hdulist[13])
    hduout.writeto(outputfile, clobber=True)
    # hdulist.writeto(outputfile, clobber=True)

    sys.exit(0)
