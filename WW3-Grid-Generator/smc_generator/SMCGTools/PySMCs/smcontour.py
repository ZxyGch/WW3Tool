"""
##  Function to draw contour lines of a smc grid field on box plot.
##  
##  First created:        JGLi18May2022
##  Last modified:        JGLi01May2025
##
"""

def smcontour(ax, lvls, cel, swhs, colrs, config, 
              fmdi=-999.0, fntsz=10):

## Import relevant modules and functions
    import numpy as np

## Total cell number by cell array
    nc = swhs.shape[0]

## Local plot configuration parameters
    zdlnlt=config[0]
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]
    nabgpl=config[4]
    na= int(nabgpl[0])
    nb= int(nabgpl[1])
    nbg=int(nabgpl[2])
    npl=int(nabgpl[3])
    ng = nc - na
    print('nc, ng, na, nb, nbg, npl = \n', 
           nc, ng, na, nb, nbg, npl)

## Size-1 cell dlon dlat and reference point zlon zlat.
    zlon= zdlnlt[0]; zlat= zdlnlt[1]
    dlon= zdlnlt[2]; dlat= zdlnlt[3]
    print(' zdlnlt defined:', zdlnlt )

## Work out max and min values, excluding missing data fmdi.
    swhmx = swhs.max()
    swhmn = swhs[ swhs > fmdi ].min()
    print ( ' swhs range %f, %f' % (swhmn, swhmx) ) 

## Reset missing values fmdi or any value < swhmn to be swhmn 
    swhs[ swhs < swhmn ] = swhmn

## Declare a 2-D array to hold mapped swhs values.
    xlond=min([360.0, rngsxy[1]])
    nx=int( (xlond    -rngsxy[0])/dlon ) + 1
    ny=int( (rngsxy[3]-rngsxy[2])/dlat ) + 1
    nx0= int( (rngsxy[0]-zlon)/dlon )
    ny0= int( (rngsxy[2]-zlat)/dlat )
    xlon=(np.arange(nx)+nx0)*dlon
    ylat=(np.arange(ny)+ny0)*dlat

    print( " Plot box nx0 nx ny0 ny :", nx0, nx, ny0, ny )
    print( " Plot box xlon range :", xlon[0], xlon[-1] )
    print( " Plot box ylat range :", ylat[0], ylat[-1] )
    vrxy=np.zeros( (ny, nx) )
    print( " Vrxy 2-D shape = :", vrxy.shape  )

## Convert swhs into x-y rectangular array.
## Loop over all cells, including Polar Cells, if any.
    for i in range(nc):

## Exclude duplicated polar part boundary cells.
        if( (i < ng-nbg) or (i >= ng+nb) ):
            nxc0= max([0,cel[i,0] - nx0])
            nyc0= max([0,cel[i,1] - ny0])
            nxc = min([cel[i,2] + nxc0, nx])
            nyc = min([cel[i,3] + nyc0, ny])

## Polar cells always cover full range of [0:nx].
            if( i >= nc-npl ):
                nxc0 = 0; nxc = nx

## Check projected cell position within range. 
            if( ( nxc0 < nx ) and 
                ( nyc0 < ny ) ):

                vrxy[nyc0:nyc, nxc0:nxc] = swhs[i]

## Apply period boundary condition if full parallel circle.
    if( int(360.0/dlon) == nx-1 ):
        vrxy[:,nx-1] = vrxy[:,0] 
        print(" Period condition applied on vrxy at column", nx)
 
## Use selected cells to draw the plot.
    ax.set_xlim(rngsxy[0:2])
    ax.set_ylim(rngsxy[2:4])
    ax.set_autoscale_on(False)

## Draw the contour lines by specified levels. 
    ax.contour(xlon, ylat, vrxy, lvls, colors='k', linewidths=0.5)

## End of smcontour function. 

