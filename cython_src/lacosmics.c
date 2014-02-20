/**
 *
 * (c) Ralf Kotulla, kotulla@uwm.edu
 *
 * This module implements a iterative sigma-clipping routine to speed
 * up the corresponding functionality in podi_imcombine.
 *
 */

#define true 0
#define false 1
typedef int bool;

#include <math.h>
#include <gsl/gsl_sort.h>
#include <gsl/gsl_statistics.h>
#include <stdlib.h>
#include <time.h>

#define nan 0./0.
#define MAXMEDIAN 7
#define HEAPSIZE 25

#define True 1
#define False 0

// #define printf //

#define tracepx //printf


void convolve(double* input, int sx, int sy,
              double* output,
              double* kernel, int ksize)
{
    int kernel_center = (ksize-1)/2;

    int dx, dy, kx, ky, i;

    // Execute the convolution
    for (dx=0; dx<sx; dx++) {
        for (dy=0; dy<sy; dy++) {

            // Set the output pixel to 0 to start with
            output[dy + dx*sy] = 0.0;

            //
            // Compute the result for this pixel convolved with the kernel
            //
            for (kx = -1*kernel_center; kx<= kernel_center; kx++) {
                for (ky = -1*kernel_center; ky<= kernel_center; ky++) {
            /* for (kx = 0; kx<1; kx++) { */
            /*     for (ky = 0; ky<1; ky++) { */

                    if (dx+kx < 0 || dx+kx >= sx || dy+ky < 0 || dy+ky > sy) {
                        continue;
                    }

                    output[dy + dx*sy] += input[dy+ky + (dx+kx)*sy]
                        * kernel[ky+kernel_center + (kx+kernel_center)*ksize];
                    
                }
            }
            
        }
    }

    return;
}



// return the median value in a vector of 27 floats pointed to by a
double heapMedian3( double *a, unsigned char n_full )
{
   double left[HEAPSIZE], right[HEAPSIZE], median, *p;
   unsigned char nLeft, nRight;
   unsigned char n_half = (unsigned char) ((float)n_full / 2.0 + 0.5);
   unsigned char nVal;
   //printf("nhalf=%d, n_full=%d\n", n_half, n_full);
   
   // pick first value as median candidate
   p = a;
   median = *p++;
   nLeft = nRight = 1;

   for(;;)
   {
       // get next value
       double val = *p++;

       // if value is smaller than median, append to left heap
       if( val < median )
       {
           // move biggest value to the heap top
           unsigned char child = nLeft++, parent = (child - 1) / 2;
           while( parent && val > left[parent] )
           {
               left[child] = left[parent];
               child = parent;
               parent = (parent - 1) / 2;
           }
           left[child] = val;

           // if left heap is full
           if( nLeft == n_half )
           {
               // for each remaining value
               for( nVal = n_full - (p - a); nVal; --nVal )
               {
                   // get next value
                   val = *p++;

                   // if value is to be inserted in the left heap
                   if( val < median )
                   {
                       child = left[2] > left[1] ? 2 : 1;
                       if( val >= left[child] )
                           median = val;
                       else
                       {
                           median = left[child];
                           parent = child;
                           child = parent*2 + 1;
                           while( child < n_half )
                           {
                               if( child < n_half-1 && left[child+1] > left[child] )
                                   ++child;
                               if( val >= left[child] )
                                   break;
                               left[parent] = left[child];
                               parent = child;
                               child = parent*2 + 1;
                           }
                           left[parent] = val;
                       }
                   }
               }
               return median;
           }
       }

       // else append to right heap
       else
       {
           // move smallest value to the heap top
           unsigned char child = nRight++, parent = (child - 1) / 2;
           while( parent && val < right[parent] )
           {
               right[child] = right[parent];
               child = parent;
               parent = (parent - 1) / 2;
           }
           right[child] = val;

           // if right heap is full
           if( nRight == n_half )
           {
               // for each remaining value
               for( nVal = n_full - (p - a); nVal; --nVal )
               {
                   // get next value
                   val = *p++;

                   // if value is to be inserted in the right heap
                   if( val > median )
                   {
                       child = right[2] < right[1] ? 2 : 1;
                       if( val <= right[child] )
                           median = val;
                       else
                       {
                           median = right[child];
                           parent = child;
                           child = parent*2 + 1;
                           while( child < n_half )
                           {
                               if( child < n_half-1 && right[child+1] < right[child] )
                                   ++child;
                               if( val <= right[child] )
                                   break;
                               right[parent] = right[child];
                               parent = child;
                               child = parent*2 + 1;
                           }
                           right[parent] = val;
                       }
                   }
               }
               return median;
           }
       }
   }
}



void lacosmics__cy(double* data,
                   double* out_cleaned, int* out_mask, int* out_saturated,
                   int sx, int sy,
                   double gain, double readnoise,
                   double sigclip, double sigfrac, double objlim,
                   double saturation_limit, int verbose,
                   int niter)
{
    
    if (verbose) {
        printf("Gain=%f\n",gain);
        printf("readnoise=%f\n",readnoise);
    }
    
    saturation_limit = -1;
    int tracepixel = 233+484*sy; //484 + 233*sy;

    
    int lx, ly, _x, _y, i, wx, wy, n, x, y;
    int kernel_center = 1, ksize=3;
    int dx, dy, kx, ky;
    double tmpd;
    int sx2 = sx*2, sy2 = sy*2, ssm, ssp;

    // memory demand calculation
    // assume sx*sy = 16M
    double* larger_2x2 = (double*)malloc(sx*2*sy*2*sizeof(double));      // 64
    double* lapla_convolved = (double*)malloc(sx*2*sy*2*sizeof(double)); // 64
    double* deriv2 = (double*)malloc(sx*sy*sizeof(double));              // 16
    double* data_med5 = (double*)malloc(sx*sy*sizeof(double));                // 16
    double* noise = (double*)malloc(sx*sy*sizeof(double));               // 16
    double* sigmap = (double*)malloc(sx*sy*sizeof(double));              // 16
    double* sigmap_med5 = (double*)malloc(sx*sy*sizeof(double));         // 16
    double* sigmap_prime = (double*)malloc(sx*sy*sizeof(double));        // 16
    double* firstsel = malloc(sx*sy*sizeof(double));                     // 16
    double* data_med3 = malloc(sx*sy*sizeof(double));                     // 16
    double* data_med7 = malloc(sx*sy*sizeof(double));                     // 16
//    double data_med7;
    double* gfirstsel = (double*)malloc(sx*sy*sizeof(double));           // 16
    double* finalsel = (double*)malloc(sx*sy*sizeof(double));            // 16
    double* data_filtered = (double*)malloc(sx*sy*sizeof(double));       // 16
    //                                                               total: 272 Mpixel * 8 bytes ~ 2.2 GB
    
    int* blkavg_pixelcount = (int*)malloc(sx*sy*sizeof(int));            // 16
    int* pixel_changed = (int*)malloc(sx*sy*sizeof(int));                // 16
    int* crj_iteration = (int*)malloc(sx*sy*sizeof(int));                // 16
    int* saturated = (int*)malloc(sx*sy*sizeof(int));                    // 16
    //                                                               total: 32 Mpixel * 4 bytes ~ 128 MB
    
    double* neighbors = (double*)malloc(MAXMEDIAN*MAXMEDIAN*sizeof(double));

    int rerun_entirely = False;
    
    double laplace_kernel[3*3] = {  
          0., -1.,  0. ,
         -1. , 4., -1. ,
          0., -1.,  0. 
    };
    
    double growth_kernel[3*3] = {
         1., 1., 1. ,
         1., 1., 1. ,
         1., 1., 1. ,
    };
    

    //
    // Add here: determine gain
    //


  /*   # take second-order derivative (Laplacian) of input image */
  /* # kernel is convolved with subsampled image, in order to remove negative */
  /* # pattern around high pixels */

  /* if (verbose) { */
  /*  print("Convolving image with Laplacian kernel") */
  /*  print("") */
  /*  } */
  /* blkrep(oldoutput,blk,2,2) */
  /* convolve(blk,lapla,kernel) */
  /* imreplace(lapla,0,upper=0,lower=INDEF,radius=0) */
  /* blkavg(lapla,deriv2,2,2,option="average") */


    //
    // Perform the laplace filtering
    //
    if (verbose) printf("Working on frame with dimensions %d x %d\n", sx, sy);

    int iteration = 0;

    for (i=0; i<sx*sy; i++) {
        crj_iteration[i] = 0;
        saturated[i] = 0;
    }
    
    for (iteration = 0; iteration < niter; iteration++) {
        if (verbose) printf("\nStarting iteration %d (of %d)...\n\n", iteration+1, niter);
        
        // duplicate all pixels 2x2
        tracepx("### Trace pixel: input data = %f\n", data[tracepixel]);
        if (verbose) printf("Computing larger 2x2 blkrep array\n");
        for (_x = 0; _x<sx; _x++) {
            for (_y = 0; _y < sy; _y++) {
                i = _y + _x*sy;
                if (pixel_changed[i]==1 || iteration == 0 || rerun_entirely) {
                    larger_2x2[ _y*2   + (_x*2  )*sy*2 ] = data[i];
                    larger_2x2[ _y*2+1 + (_x*2  )*sy*2 ] = data[i];
                    larger_2x2[ _y*2   + (_x*2+1)*sy*2 ] = data[i];
                    larger_2x2[ _y*2+1 + (_x*2+1)*sy*2 ] = data[i];
                }
                
            }
        }

        //
        //
        //
        if (verbose) printf("Convolving with 3x3 laplace kernel!\n");
        /* convolve(larger_2x2, 2*sx, 2*sy, lapla_convolved,  laplace_kernel, 3); */
        for (dx=0; dx<sx2; dx++) {
            for (dy=0; dy<sy2; dy++) {
                i = dy + dx*sy2;
                if (pixel_changed[dy/2 + dx/2*sy]==1 || iteration == 0 || rerun_entirely) {
                    
                    lapla_convolved[i] = 0.0;

                    //
                    // Compute the result for this pixel convolved with the kernel
                    //
                    for (kx = -1*kernel_center; kx<= kernel_center; kx++) {
                        for (ky = -1*kernel_center; ky<= kernel_center; ky++) {
                            if (!(dx+kx < 0 || dx+kx >= sx2 || dy+ky < 0 || dy+ky > sy2)) {

                                lapla_convolved[i] += larger_2x2[dy+ky + (dx+kx)*sy2]
                                    * laplace_kernel[ky+kernel_center + (kx+kernel_center)*ksize];
                            }
                        }
                    }
                    /* printf("replacing negative pixel values\n"); */
                    /* imreplace(lapla_convolved, sx*2, sy*2, -1e99, 0., 0.0); */
                    lapla_convolved[i] = lapla_convolved[i] < 0 ? 0. : lapla_convolved[i];
                }
                
            }
        }

        if (verbose) printf("Running blkavg\n");
        for (_x = 0; _x<sx; _x++) {
            for (_y = 0; _y < sy; _y++) {
                i = _y + _x*sy;
                if (pixel_changed[i]==1 || iteration == 0 || rerun_entirely) {
                
                    deriv2[i] = 0.25 * (
                        lapla_convolved[ _y*2   + (_x*2  )*sy*2 ] +
                        lapla_convolved[ _y*2+1 + (_x*2  )*sy*2 ] +
                        lapla_convolved[ _y*2   + (_x*2+1)*sy*2 ] +
                        lapla_convolved[ _y*2+1 + (_x*2+1)*sy*2 ]
                    );
                }
            }
        }
        tracepx("### Trace pixel: deriv2 = %f\n", deriv2[tracepixel]);
        /* for (i=0; i<sx*sy; i++) { */
        /*     output[i] = deriv2[i]; */
        /* } */

        
        if (verbose) printf("Median-filtering the data, computing noise and significance\n");
        wx = wy = 5; dx = (wx-1)/2; dy = (wy-1)/2;
        for (_x=0; _x<sx; _x++) {
            for (_y=0; _y<sy; _y++) {
                i = _y + _x*sy;
                
                // only do work if necessary
                if (pixel_changed[i]==1 || iteration == 0 || rerun_entirely) {
                    n = 0;
                    for ( x = ( (_x-2) <  0 ?  0 : (_x-2) );
                          x < ( (_x+3) > sx ? sx : (_x+3) );
                          x++) {
                        for ( y = ( (_y-2) <  0 ?  0 : (_y-2) );
                              y < ( (_y+3) > sy ? sy : (_y+3) );
                              y++) {
                            neighbors[n++] = data[y + x*sy];
                        }
                    }
                    // Now compute the median
                    gsl_sort(neighbors, 1, n);
                    tmpd = gsl_stats_median_from_sorted_data(neighbors, 1, n);
                    data_med5[i] = tmpd < 0.00001 ? 0.00001 : tmpd;

                    /* // During the first iteration, create a mask for saturated stars */
                    /* if (iteration == 0 && saturation_limit > 0) { */
                    /*     if (med5[i] > saturation_limit) { */
                    /*         saturated[i] = 1; */
                    /*     } */
                    /* } */
                            
                    // Compute noise estimate
                    noise[i] = sqrt(data_med5[i]*gain + readnoise*readnoise)/gain;
                    // Compute significance of pixel
                    sigmap[i] = (deriv2[i] / noise[i]) / 2.;
                }
            }
        }
        tracepx("### Trace pixel: data_med5 = %f\n", data_med5[tracepixel]);
        tracepx("### Trace pixel: sigmap = %f\n", sigmap[tracepixel]);
        tracepx("### Trace pixel: noise = %f\n", noise[tracepixel]);
    

        //
        // If masking saturated pixels was requested, grow the masked area by +/- 2 pixels
        //
        if (iteration == 0 && saturation_limit > 0) {
            if (verbose) printf("Creating saturated pixel mask\n");
            ssm = -3; ssp = 4;
            for (_x=0; _x<sx; _x++) {
                for (_y=0; _y<sy; _y++) {
                    if (data_med5[_y + _x*sy] > saturation_limit) {
                        
                        for ( x = ( (_x+ssm) <  0 ?  0 : (_x+ssm) );
                              x < ( (_x+ssp) > sx ? sx : (_x+ssp) );
                              x++) {
                            for ( y = ( (_y+ssm) <  0 ?  0 : (_y+ssm) );
                                  y < ( (_y+ssp) > sy ? sy : (_y+ssp) );
                                  y++) {
                                saturated[y + x*sy] = 1;
                            }
                        }
                    }
                }
            }
        }
        
        if (verbose) printf("removing large structure\n");
        wx = wy = 5; dx = (wx-1)/2; dy = (wy-1)/2;
        for (_x=0; _x<sx; _x++) {
            for (_y=0; _y<sy; _y++) {
                i = _y + _x*sy;
                
                // only do work if necessary
                if (pixel_changed[i]==1 || iteration == 0 || rerun_entirely) {
                    n = 0;
                    for ( x = ( (_x-2) <  0 ?  0 : (_x-2) );
                          x < ( (_x+3) > sx ? sx : (_x+3) );
                          x++) {
                        for ( y = ( (_y-2) <  0 ?  0 : (_y-2) );
                              y < ( (_y+3) > sy ? sy : (_y+3) );
                              y++) {

                            neighbors[n++] = sigmap[y + x*sy];
                        }
                    }
                    // Now compute the median
                    gsl_sort(neighbors, 1, n);
                    sigmap_med5[i] = gsl_stats_median_from_sorted_data(neighbors, 1, n);
                    // Subtract the smoothed significance map from the pixel significance map
                    sigmap_prime[i] = sigmap[i] - sigmap_med5[i];
                }
            }
        }
        tracepx("### Trace pixel: sigmap_med5 = %f\n", sigmap_med5[tracepixel]);
        tracepx("### Trace pixel: sigmap_prime = %f\n", sigmap_prime[tracepixel]);

                
        if (verbose) printf("Selecting candidate CRs\n");
        for (i=0; i<sx*sy; i++) {
            firstsel[i] = ((sigmap_prime[i] > sigclip) && (saturated[i] == 0)) ? 1 : 0;
        }
    
        if (verbose) printf("subtract background and smooth component of objects\n");
        for (_x = 0; _x<sx; _x++) {
            for (_y = 0; _y < sy; _y++) {
                i = _y + _x*sy;

                if ((pixel_changed[i] || iteration == 0 || rerun_entirely)) {
                    //
                    // do 3x3 median filtering
                    //
                    n=0;
                    for ( x = ( (_x-1) <  0 ?  0 : (_x-1) );
                          x < ( (_x+2) > sx ? sx : (_x+2) );
                          x++) {
                        for ( y = ( (_y-1) <  0 ?  0 : (_y-1) );
                              y < ( (_y+2) > sy ? sy : (_y+2) );
                              y++) {
                            neighbors[n++] = data[y + x*sy];
                        }
                    }
                    gsl_sort(neighbors, 1, n);
                    data_med3[i] = gsl_stats_median_from_sorted_data(neighbors, 1, n);

                } // end if pixel_changed
            }
        }
        tracepx("### Trace pixel: data_med3 = %f\n", data_med3[tracepixel]);
        
        /* for (i=0; i<sx*sy; i++) { */
        /*     out_cleaned[i] = data_med3[i]; */
        /* } */
        
        
        for (_x = 0; _x<sx; _x++) {
            for (_y = 0; _y < sy; _y++) {
                i = _y + _x*sy;

                if ((pixel_changed[i] || iteration == 0 || rerun_entirely)) { // && firstsel[i] > 0) {
                    //
                    // do 7x7 median filtering
                    //
                    n=0;
                    for ( x = ( (_x-3) <  0 ?  0 : (_x-3) );
                          x < ( (_x+4) > sx ? sx : (_x+4) );
                          x++) {
                        for ( y = ( (_y-3) <  0 ?  0 : (_y-3) );
                              y < ( (_y+4) > sy ? sy : (_y+4) );
                              y++) {
                            neighbors[n++] = data_med3[y + x*sy];
                        }
                    }
                    gsl_sort(neighbors, 1, n);
                    data_med7[i] = gsl_stats_median_from_sorted_data(neighbors, 1, n);


                    tmpd = (data_med3[i] - data_med7[i]) / noise[i];
                    tmpd = tmpd < 0.01 ? 0.01 : tmpd;
                    
                    // out_cleaned[i] = tmpd; // this is f in the python version
                    
                    // if (firstsel[i] > 0) {
                    firstsel[i] = firstsel[i] > 0 && sigmap_prime[i] > (tmpd * objlim) ? 1 : 0;
                }

                // Also reset the mask of CR pixels to 0
                pixel_changed[i] = 0;
               
                
            }
        }
        tracepx("### Trace pixel: firstsel = %f\n", firstsel[tracepixel]);
        tracepx("### Trace pixel: tmpd = %f\n", (data_med3[tracepixel]-data_med7[tracepixel])/noise[tracepixel]);
 
        if (verbose) printf("Growing mask and checking neighboring pixels\n");
        /* n=0; for(i=0; i<sx*sy; i++) if (firstsel[i] > 0.5) n++; printf("Initial #CRs: %d (>%f sigma)\n", n, sigclip); */
        convolve(firstsel, sx, sy, gfirstsel, growth_kernel, 3);
        /* n=0; for(i=0; i<sx*sy; i++) if (gfirstsel[i] > 0.5) n++; printf("Initial grown #CRs: %d\n", n); */
        for (i=0; i<sx*sy; i++) {
            gfirstsel[i] = sigmap_prime[i] > sigclip && gfirstsel[i] > 0.5 && saturated[i] == 0 ? 1. : 0.;
        }
        /* n=0; for(i=0; i<sx*sy; i++) if (gfirstsel[i] > 0.5) n++; printf("remaining grown #CRs: %d\n", n); */
        tracepx("### Trace pixel: gfirstsel = %f\n", gfirstsel[tracepixel]);
        
    
        double sigcliplow = sigfrac * sigclip;
    
        if (verbose) printf("Growing mask again and checking for weaker neighboring pixels\n");
        convolve(gfirstsel, sx, sy, finalsel, growth_kernel, 3);
        /* n=0; for(i=0; i<sx*sy; i++) if (finalsel[i] > 0.5) n++; printf("2nd grown #CRs: %d\n", n); */
        for (i=0; i<sx*sy; i++) {
            finalsel[i] = sigmap_prime[i] > sigcliplow && finalsel[i] > 0.5 && saturated[i] == 0 ? 1. : 0.;
        }
        /* n=0; for(i=0; i<sx*sy; i++) if (finalsel[i] > 0.5) n++; printf("final #CRs: %d (>%f sigma)\n", n, sigcliplow); */
        tracepx("### Trace pixel: finalsel = %f\n", finalsel[tracepixel]);

        /* for (i=0; i<sx*sy; i++) { */
        /*     out_cleaned[i] = finalsel[i]; */
        /* } */

        int crpix_found = 0;
        for (i=0; i<sx*sy; i++) {
            crpix_found += finalsel[i];
        }
        if (verbose) printf("Found a total of %d cosmic-ray affected pixels\n", crpix_found);
    
        if (verbose) printf("create cleaned output image\n");
        wx = wy = 5; dx = (wx-1)/2; dy = (wy-1)/2;
        for (_x=0; _x<sx; _x++) {
            for (_y=0; _y<sy; _y++) {
                i = _y + _x*sy;

                // only compute the median of neighbors if we need to replace this pixel
                if (finalsel[i] > 0) {
                
                    crj_iteration[i] = iteration + 1;

                    // Collect all pixels in the neighborhood of this pixel
                    n = 0;
                    for ( x = ( (_x-2) <  0 ?  0 : (_x-2) );
                          x < ( (_x+3) > sx ? sx : (_x+3) );
                          x++) {
                        for ( y = ( (_y-2) <  0 ?  0 : (_y-2) );
                              y < ( (_y+3) > sy ? sy : (_y+3) );
                              y++) {
                            // Filter out pixels labeled as cosmics
                            // Ignore all pixels masked as cosmic rays in this
                            // or any of the past iterations
                            if (crj_iteration[y + x*sy] == 0 && finalsel[y + x*sy] == 0) {
                                neighbors[n++] = data[y + x*sy];
                            }
                        }
                    }
                    // Now compute the median
                    gsl_sort(neighbors, 1, n);
                    tmpd = gsl_stats_median_from_sorted_data(neighbors, 1, n);

                    // Replace this cosmic affected pixel with the median of its neighbors
                    data_filtered[i] = tmpd;

                    // Now mark all pixels in a 7 pixel box to be affected by the CR
                    for ( x = ( (_x-3) <  0 ?  0 : (_x-3) );
                          x < ( (_x+4) > sx ? sx : (_x+4) );
                          x++) {
                        for ( y = ( (_y-3) <  0 ?  0 : (_y-3) );
                              y < ( (_y+4) > sy ? sy : (_y+4) );
                              y++) {

                            pixel_changed[y + x*sy] = 1;
                        }
                    }
                    
                } else {
                    data_filtered[i] = data[i];
                }
                
            }
        }
        tracepx("### Trace pixel: data_filtered = %f\n", data_filtered[tracepixel]);


        // If necessary, prepare for the next iteration
        if (iteration < niter-1) {
            for (i=0; i<sx*sy; i++) {
                data[i] = data_filtered[i];
            }
        }

        if (verbose) printf("Done with iteration %d (of %d)...\n\n", iteration+1, niter);

    }

    // Copy cleaned image to output buffer
    if (verbose) printf("Preparing output...\n");
    for(_x=0; _x<sx; _x++){
        for(_y=0; _y<sy; _y++) {
            out_cleaned[_y + _x*sy] = data_filtered[_y + _x*sy];
            out_mask[_y + _x*sy] = crj_iteration[_y + _x*sy];
            out_saturated[_y + _x*sy] = saturated[_y + _x*sy];
        }
    }
    
    
    if (verbose) printf("done!\n");
    return;
}
    

#ifdef __STANDALONE__

void main()
{

    printf("test\n");

    int sx=512, sy=512, i, j;

    double* data = (double*)malloc(sx*sy*sizeof(double));
    double* retval = (double*)malloc(sx*sy*sizeof(double));

    double neighbors[50], median1, median2;
    clock_t c1, c2, c3;
    double time_a = 0, time_b = 0;
    
    int n = 25;
    for (i=0; i<500000; i++) {
        // Create some random numbers

        for (j=0; j<n; j++) {
            neighbors[j] = (double)(rand()%100);
            //printf("% 3d%s", (int)neighbors[j], (j<n-1 ? ", " : " --> "));
        }
        c1 = clock();
        median1 = heapMedian3(neighbors, n);
        c2 = clock();
        gsl_sort(neighbors, 1, n);
        median2 = gsl_stats_median_from_sorted_data(neighbors, 1, n);
        c3 = clock();

        time_a += (double)(c2 - c1)/CLOCKS_PER_SEC;
        time_b += (double)(c3 - c2)/CLOCKS_PER_SEC;
        
        //printf("%.0f / %.0f\n", median1, median2);
    }
    printf("Timing a=%f, b=%f, a/b=%f\n", time_a, time_b, time_a/time_b);
    
    
    return;
    
}

#endif