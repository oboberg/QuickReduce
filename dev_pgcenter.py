#!/usr/local/bin/python

import pyfits
import math
import scipy
import sys
import os

import scipy.ndimage
import scipy.stats
import scipy.signal
import numpy
import bottleneck
from podi_definitions import *
import itertools

# def rebin_image(data, binfac):
    
#     if (binfac < 1):
#         stdout_write("Rebinning at the moment only supports binning to larger pixels with binfac>1\n")
#         return None
#     elif (binfac == 1):
#         return data
    
#     out_size_x, out_size_y = int(math.ceil(data.shape[0]*1.0/binfac)), int(math.ceil(data.shape[1]*1.0/binfac))
    
#     if (out_size_x*binfac != data.shape[0] or out_size_y*binfac != data.shape[1]):
#         # The input array size is not a multiple of the new binning
#         # Create a slightly larger array to hold the data to be rebinned
#         container = numpy.zeros(shape=(out_size_x*binfac, out_size_y*binfac))
        
#         # And insert the original data
#         container[0:data.shape[0], 0:data.shape[1]] = data[:,:]
#     else:
#         container = data 
    
#     rebinned = numpy.reshape(container, (out_size_x, binfac, out_size_y, binfac)).mean(axis=-1).mean(axis=1)
#     #rebinned = numpy.reshape(container, (out_size_x, binfac, out_size_y, binfac)).nm(axis=-1).nm(axis=1)
    
#     #rs = numpy.array(numpy.reshape(container, (out_size_x, binfac, out_size_y, binfac)), dtype=numpy.float32)
#     #rb1 = bottleneck.nanmean(rs, axis=-1)
#     #rb2 = bottleneck.nanmean(rb1, axis=1)
#     #rebinned = rb2
    
#     return rebinned





def find_center(hdu_data, coord_x, coord_y,
                #lx, ly, 
                prebin=8, 
                #r_minmax=[100,200], x_minmax=[400,600], y_minmax=[400,600], 
                search_x=[0, 300, 10],
                search_y=[0, 300, 10],
                search_r=[800, 1400, 10],
                fixed_radius=1270,
                # dx=2, dy=2, dr=2
                threshold=None,
                debugname=None,
                verbose=False
                ):


    #
    # Bin the data frame and the corresponding coordinate frames
    #
    ot33b = rebin_image(hdu_data, prebin, operation=numpy.mean)
    all_x = rebin_image(coord_x, prebin, operation=numpy.mean)
    all_y = rebin_image(coord_y, prebin, operation=numpy.mean)

    if (debugname != None):
        pyfits.HDUList([pyfits.PrimaryHDU(data=ot33b)]).writeto("debug_"+debugname+"___data.fits", clobber=True)
        pyfits.HDUList([pyfits.PrimaryHDU(data=all_x)]).writeto("debug_"+debugname+"___all_x.fits", clobber=True)
        pyfits.HDUList([pyfits.PrimaryHDU(data=all_y)]).writeto("debug_"+debugname+"___all_y.fits", clobber=True)
    ot33_orig = ot33b.copy()

    ot33b[numpy.isnan(ot33b)] = 0

    #
    # Compute the gradient frame by differentiating the image 
    # frame using a Sobel filter
    #
    x33 = scipy.ndimage.sobel(ot33b, axis=0, mode='constant')
    y33 = scipy.ndimage.sobel(ot33b, axis=1, mode='constant')
    abs33 = numpy.hypot(x33, y33)
    if (debugname != None):
        pyfits.HDUList([pyfits.PrimaryHDU(data=abs33)]).writeto("debug_"+debugname+"___sobel.fits", clobber=True)

    #
    # Create a mask of all valid images
    # This is needed to get rid of all the artificial edges 
    # at the edges of each cell
    # This mask is set to 1 for all NaN-masked pixels in the input frame
    # 
    mask = numpy.array(numpy.isnan(ot33_orig), dtype=numpy.float32)
    mask[3,3] = 1.
    numpy.savetxt("mask", mask)

    # 
    # Convolve the mask with a simple flat kernel to widen all gaps 
    # and get rid of cell edges
    # 
    kernel = numpy.ones(shape=(5,5))
    kernel_norm = kernel
    if (verbose): print "number valid pixels before growing",numpy.sum((mask == False))
    mask_grown_float = scipy.ndimage.filters.convolve(mask, kernel)
    mask_grown = mask_grown_float > 0
    numpy.savetxt("mask.g", mask_grown)
    if (verbose): print "number valid pixels after growing",numpy.sum((mask_grown == False))

    if (debugname != None):
        pyfits.HDUList([pyfits.PrimaryHDU(data=mask_grown_float)]).writeto("debug_"+debugname+"___mask.fits", clobber=True)

    #
    # Apply the now widened mask to the gradient map
    #
    abs33[numpy.isnan(ot33_orig)] = numpy.NaN
    abs33_binary = abs33.copy()
    abs33_binary[abs33 < 0.1] = 0
    abs33_binary[abs33 >= 0.1] = 1
    abs33[mask_grown] = numpy.NaN
    if (debugname != None):
        pyfits.HDUList([pyfits.PrimaryHDU(data=abs33)]).writeto("debug_"+debugname+"___sobel_filtered.fits", clobber=True)
    #
    # Now apply a threshold so we only deal with strong gradients and get rid 
    # of a lot of the underlying background noise
    #
    # Figure out what contrast we need
    #
    valid_pixels = numpy.isfinite(abs33)
    #print "number valid pixels",numpy.sum(valid_pixels)
    top10percent = scipy.stats.scoreatpercentile(abs33[valid_pixels].ravel(), 90)
    if (threshold == None):
        strong_values = abs33 > top10percent
        if (verbose): print "Only using pixels >",top10percent
    else:
        strong_values = abs33 > threshold
        if (verbose): print "Only using pixels >",threshold


#    all_y, all_x = numpy.indices(abs33.shape)

    #
    # All we need from now on are the coordinates of pixels with strong gradients
    #
    pixel_x = all_x[strong_values]
    pixel_y = all_y[strong_values]
    pixel_value = abs33[strong_values]
    if (verbose): print numpy.sum(strong_values),"pixels with enough signal left"

    #
    # setup the array for the pattern recognition
    #
    n_x = int(math.ceil((search_x[1] - search_x[0])/search_x[2]))
    x_values_to_try = (numpy.arange(n_x) * search_x[2]) + search_x[0]
    n_y = int(math.ceil((search_y[1] - search_y[0])/search_y[2]))
    y_values_to_try = (numpy.arange(n_y) * search_y[2]) + search_y[0]
    n_r = int(math.ceil((search_r[1] - search_r[0])/search_r[2]))
    r_values_to_try = (numpy.arange(n_r+1) * search_r[2]) + search_r[0]

    #print "search box x=",x_values_to_try
    #print "search box y=",y_values_to_try
    #print "search box r=",r_values_to_try

    #
    # Now do the hough transformation:
    # Loop over all possible center positions and count how 
    # many pixels fall into the radial slices
    #
    bincount = numpy.zeros(shape=(n_x, n_y, n_r))
    for i_cx, i_cy in itertools.product(range(n_x), range(n_y)):

        cx = x_values_to_try[i_cx]
        cy = y_values_to_try[i_cy]

        pixel_radius = numpy.sqrt( (cx-pixel_x)**2 + (cy-pixel_y)**2 )

        # Count pixels in each of the rings.
        # Also use intensity as weight to emphasize stronger features
        count,edges = numpy.histogram(pixel_radius, bins=r_values_to_try, 
                                      weights=pixel_value)
 
        # Insert the ring count into the overall structure
        bincount[i_cx, i_cy, :] = count[:]
    
        
    if (not fixed_radius == None):
        # Find what radial bin is covered by the specified radius
        ir = int(math.floor((fixed_radius - search_r[0]) / search_r[2]))
        if (verbose): print "using fixed radius",fixed_radius, ir

        # For this radius, find the center position with the strongest signal
        center_only = bincount[:,:,ir]
        index = numpy.argmax(center_only)
        #print "argmax=",index
        ix, iy = numpy.unravel_index(index, center_only.shape)
        #print "unraveled:",ix,iy
        #print x_values_to_try[ix], ix*search_x[2]+search_x[0]

    else:

        index = numpy.argmax(bincount)
        ix, iy, ir = numpy.unravel_index(index, bincount.shape)


    if (verbose): 
        print "found some results:"
        print "  center-x=",x_values_to_try[ix],"(",ix,")"
        print "  center-y=",y_values_to_try[iy],"(",iy,")"
        print "    radius=",r_values_to_try[ir],"(",ir,")"

    return x_values_to_try[ix], y_values_to_try[iy], r_values_to_try[ir], bincount, abs33



if __name__ == "__main__":

    hdu = pyfits.open(sys.argv[1])

    prebin=8
#    lx = [0,400,400,-100,-100]
#    ly = [0, 400,-100,-100,400]

    lx = numpy.array([0, 3200, 3200, -800, -800]) #/ prebin
    ly = numpy.array([0, 3200, -800, -800, 3200]) #/ prebin

    guess_center = {
        "OTA33.SCI": (4050, 4050),
        "OTA34.SCI": (4050, -100),
        "OTA44.SCI": (-100, -100),
        "OTA43.SCI": (-100, 4050),
        }

    guess_cx = numpy.array([0, 4050, 3200, -800, -800]) #/ prebin
    guess_cy = numpy.array([0, 4050, -800, -800, 3200]) #/ prebin

    dx, dy, dr = 16,16,16

    for i in range(1,5):
        print hdu[i].header["EXTNAME"]

        r_minmax=[800,1600] 
        x_minmax=[lx[i], lx[i]+1600]
        y_minmax=[ly[i], ly[i]+1600]

        rawdata = hdu[i].data.T
        # trim the edges generously
        rawdata[3980:,:] = numpy.NaN
        rawdata[:,3980:] = numpy.NaN
        px, py = numpy.indices(rawdata.shape)

        cx, cy = guess_center[hdu[i].header["EXTNAME"]]
        search_width=500

        x, y, r, bincount, edge_frame = find_center(rawdata, px, py,
                                                    search_r = [1200,1350, 10],
                                                    search_x = [cx-search_width, cx+search_width,20],
                                                    search_y = [cy-search_width, cy+search_width,20],
                                                    prebin=8,
                                                    #debugname=hdu[i].header["EXTNAME"],
                                                    fixed_radius=1280,
                                                    )
        print x,y,r, " ---> ", x, y, r
              
        numpy.savetxt("bincount"+hdu[i].header["EXTNAME"], numpy.sum(numpy.sum(bincount, axis=0), axis=0))
        # log = open("bincount"+hdu[i].header["EXTNAME"]+".full", "w")
        # for x,y,z  in itertools.product(range(bincount.shape[0]), 
        #                                 range(bincount.shape[1]), 
        #                                 range(bincount.shape[2])):
        #     print >>log, x, y, z, bincount[x,y,z]
        # log.close()

            
#        print x,y,r, " ---> ", x*prebin+1, y*prebin+1, r*prebin

        hdu[i].data = edge_frame
        print

        # Now we have a rough idea where the center is.
        # Extract a sub-region of the frame close to the center 
        # that contains the signal plus some extra, re-run the 
        # center-finding routine and refine the solution.
        center_x = x#*prebin
        center_y = y#*prebin
        radius = r#*prebin
        margin = 50 # pixels

        min_x, max_x = center_x - radius - margin, center_x + radius + margin
        min_y, max_y = center_y - radius - margin, center_y + radius + margin

        min_valid_x = numpy.max([0, min_x])
        max_valid_x = numpy.min([rawdata.shape[0], max_x])
        min_valid_y = numpy.max([0, min_y])
        max_valid_y = numpy.min([rawdata.shape[1], max_y])

        midres_data = rawdata[min_valid_x:max_valid_x, min_valid_y:max_valid_y]
        midres_filtered = scipy.signal.medfilt2d(midres_data, 7)
        midres_px   = px[min_valid_x:max_valid_x, min_valid_y:max_valid_y]
        midres_py   = py[min_valid_x:max_valid_x, min_valid_y:max_valid_y]
        
        x, y, r, bincount2, edge_frame2 = find_center(midres_filtered,
                                                    midres_px, midres_py,
                                                    search_r = [radius-20,radius+20,2],
                                                    search_x = [center_x-30,center_x+30,4],
                                                    search_y = [center_y-30,center_y+30,4],
                                                    prebin=4,
                                                    #debugname=hdu[i].header["EXTNAME"]+"__midres__",
                                                    fixed_radius=1280,
                                                      threshold=0,
                                                    )
 
        print "MID-resolution: ", x,y,r, " ---> ", x, y, r
 
        x, y, r, bincount2, edge_frame2 = find_center(midres_filtered,
                                                    midres_px, midres_py,
                                                    search_r = [radius-20,radius+20,2],
                                                    search_x = [center_x-30,center_x+30,4],
                                                    search_y = [center_y-30,center_y+30,4],
                                                    prebin=4,
                                                    #debugname=hdu[i].header["EXTNAME"]+"__midres__",
                                                      threshold=0,
                                                    )
 
        print "MID-resolution (variable r): ", x,y,r, " ---> ", x, y, r
 
    hduout = hdu[0:5]
    hduout.writeto("/scratch/edges.fits", clobber=True)

