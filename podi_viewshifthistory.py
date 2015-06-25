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


import sys
import numpy
import os
import math

from podi_definitions import *
import pyfits
import matplotlib.pyplot as plot
import matplotlib.cm as cm


def view_shift_history(filename):

    # Load the shiftf file
    hdu = pyfits.open(filename)
    dir, name = os.path.split(filename)

    #print hdu.info()
    
    shift_history = hdu[1].data


    if (cmdline_arg_isset("-shiftdelay")):
    
        shift_complete = hdu[1].data.field('shift_complete')
        #numpy.savetxt("/Volumes/ODIScratch/rkotulla/shift.dump", shift_history)

        time_diff = (shift_history.field('shift_complete') - shift_history.field('message_received')) * 1000.
        print time_diff.shape
        print time_diff
        count, bins = numpy.histogram(time_diff, 400, (-1,1))
        #for i in range(count.shape[0]):
        #    print bins[i], bins[i+1], count[i]

        mean_time = 0.5*(bins[:-1] + bins[1:])
        plot.plot(mean_time, count)
        plot.ylabel("Count")
        plot.xlabel("time delay between start and shift [milli-secs]")
        plot.show()
    
    elif (cmdline_arg_isset("-xyhist")):
        print "PLotting xy-histogram of shift positions"
        count, xedges, yedges = numpy.histogram2d(shift_history.field('shift1'), shift_history.field('shift2'),
                                                  bins=[20,20], range=[[-10,10], [-10,10]])

        fig = plot.figure()
        # split filename into directory and filename
        fig.suptitle("Shift history for\n%s" % (name))

        # Draw the 2-d histogram on the right
        img = plot.imshow(count, interpolation='nearest', extent=(xedges[0],xedges[-1],yedges[0],yedges[-1]),origin='lower')
        fig.colorbar(img)

        maxcount = numpy.max(count)
        for x in range(count.shape[0]):
            for y in range(count.shape[1]):
                color = "white" if count[x,y] < 0.2*max_count else "black"
                print count[x,y], max_count, color
                plot.text(0.5*(xedges[x]+xedges[x+1]), 0.5*(yedges[y]+yedges[y+1]), "%d" % count[x,y], ha='center', va='center', color=color)

        plot.xlabel("shift_x")
        plot.ylabel("shift_y")
        
        plot.show()


        #if (cmdline_arg_isset("-xyscatter")):
    else:

        n_shifts = shift_history.field('shift1').shape[0]
        # Create plot
        fig = plot.figure(figsize=(12,6))
        fig.canvas.set_window_title("podi_viewshifthistory: Shift history for: %s" % (name))
        fig.suptitle("Shift history for: %s  --  #shifts = %d" % (name, n_shifts ))

        little_scatter_x = numpy.random.rand(n_shifts)/3-(0.5/3)#0.25
        little_scatter_y = numpy.random.rand(n_shifts)/3-(0.5/3)#0.25

        # find range for framenum
        x_value = 'shift_complete' #'framenum'
        x_label = 'exposure time' # "frame number"
        _fn_min = numpy.min(shift_history.field(x_value))
        _fn_max = numpy.max(shift_history.field(x_value))
        x_offset = numpy.min(shift_history.field(x_value))
        fn_min = _fn_min - 0.03*(_fn_max-_fn_min) - x_offset
        fn_max = _fn_max + 0.03*(_fn_max-_fn_min) - x_offset

        # Draw the two plots on the left, bototm one first
        ax = plot.axes([0.05,0.1, 0.38,.35])
        print ax
        ax.scatter(shift_history.field(x_value)-x_offset, shift_history.field('shift2')+little_scatter_y)
        ax.set_xlim((fn_min, fn_max))
        #plot.scatter(shift_history.field(x_value), shift_history.field('shift2')+little_scatter_y)
        ax.grid(True)
        ax.set_xlabel(x_label)
        ax.set_ylabel("shift y")
        
        #plot.subplot(2,1,2)
        ax2 = plot.axes([0.05,0.55, 0.38,0.35])
        ax2.scatter(shift_history.field(x_value)-x_offset, shift_history.field('shift1')+little_scatter_x)
        #ax2.plot(shift_history.field(x_value), shift_history.field('shift1')+little_scatter_x, 'b-')
        ax2.set_xlim((fn_min, fn_max))
        ax2.grid(True)
        ax2.set_xlabel(x_label)
        ax2.set_ylabel("shift x")


        # Now draw the 2-d histogram pn the right
        # Find the maximum shift in either direction
        max_shift = numpy.max(numpy.append(shift_history.field('shift1'), shift_history.field('shift2')))
        print "max ot shift:", max_shift

        max_shift += 1
        n_bins = 2*(max_shift)+1
        
        count, xedges, yedges = numpy.histogram2d(shift_history.field('shift1'), 
                                                  shift_history.field('shift2'),
                                                  bins=[n_bins,n_bins], 
                                                  range=[[-max_shift-0.5,max_shift+0.5], [-max_shift-0.5,max_shift+0.5]])

#        count, xedges, yedges = numpy.histogram2d(shift_history.field('shift1'), shift_history.field('shift2'),
#                                                  bins=[20,20], range=[[-10,10], [-10,10]])

        ax3 = plot.axes([0.5,0.1,0.5,0.8])
        img = ax3.imshow(count, interpolation='nearest', extent=(xedges[0],xedges[-1],yedges[0],yedges[-1]),origin='lower')
        fig.colorbar(img)

        maxcount = numpy.max(count)
        for x in range(count.shape[0]):
            for y in range(count.shape[1]):
                color = "#000000" #if count[x,y] < 0.3*maxcount else "black"
                ax3.text(0.5*(xedges[x]+xedges[x+1]), 0.5*(yedges[y]+yedges[y+1]), "%d" % count[y,x], ha='center', va='center', color=color)

        ax3.set_xlabel("shift_x")
        ax3.set_ylabel("shift_y")
 

        
        plot.show()
        fig.savefig("shift.png")

    print 
    

    
if __name__ == "__main__":
    
    filename = sys.argv[1]
    
    view_shift_history(filename)
    
