"""
## smcelvrglr function generates the polygon vertices used to draw cells
## on regular grid plots or output field when field colour is filled. 
##
## First Created:    JGLi12Jan2021
## Last Modified:    JGLi25Apr2025
##
## Input:    cel --- cell array to be projected. 
##           zdlnlt = [zrlon, zrlat, dxlon, dylat] --- i=j=0 lon-lat and size-1 increments.
##           rngsxy = [0.0, 360.0,-90.0, 90.0] --- plot ranges (assume lat-lon grid).
##           excids = [] --- excluded cell ids to be appended at the end for marks. 
##           NArB = [] --- default empty list. Provided unempty for the Arctic part.
## Output:   nvrts, ncels --- cell vertices and cell ids on the single plot plane.
##
"""

def smcelvrglr( cel, zdlnlt, rngsxy, excids=[], NArB=[] ):

    import numpy as np

## Process input parameters.
    zrlon=zdlnlt[0]; zrlat=zdlnlt[1]
    dxlon=zdlnlt[2]; dylat=zdlnlt[3]
    nc = cel.shape[0]
    ng = nc
    nba = nbg = npl = 0
    Arctic = False

    if( len(NArB) > 2 ):
        Arctic = True
        na  = int( NArB[0] )
        nba = int( NArB[1] )
        nbg = int( NArB[2] )
        ng  = nc - na

## Default 1 polar cell.
        if( len(NArB) > 3 ):
            npl = int( NArB[3] )
        else:
            npl = 1

    nexc = len(excids)
    if( nexc > 0 ): print( " Marked cell numbers =", nexc )

## Check lat-lon box range and return if not consistent.
    if( rngsxy[0] < rngsxy[1] ): 
        print( ' Longitude range:', rngsxy[0:2] )
    else:
        print( ' Inconsistent longitude range:', rngsxy[0:2] )
        return 

    if( rngsxy[2] < rngsxy[3] ):
        print( ' Latitude  range:', rngsxy[2:4] )
    else:
        print( ' Inconsistent latitude range:', rngsxy[2:4] )
        return 

## Initial verts and ncels variable for polycollections.
    nvrts = []
    ncels = []
    nmark  = 0        
    if( nexc > 0 ):
        nbvrt = []
        nbcel = []

## Loop over all cells, including Polar Cell if any.
    for i in range(nc):

## Excluding duplicated boundary cells for plotting.
        if( (i < ng-nbg) or (i >= ng+nba) ):

## Polar cell is projected as a square box
            if( Arctic and i >= nc-npl ):
                sxc=np.array( [0.0, 360.0, 360.0, 0.0] )
                yp1=cel[i,1]*dylat + zrlat
                yp2=(cel[i,1]+cel[i,3])*dylat + zrlat
                syc=np.array( [yp1, yp1, yp2, yp2] ) 

## Other cells are rectangular boxes by their sizes.
            else:
                xc=np.array( [cel[i,0],cel[i,0]+cel[i,2],cel[i,0]+cel[i,2],cel[i,0]] )
                yc=np.array( [cel[i,1],cel[i,1],cel[i,3]+cel[i,1],cel[i,3]+cel[i,1]] )
                sxc=xc*dxlon + zrlon
                syc=yc*dylat + zrlat

## Check projected cell is positioned within plotting range. 
            if( (rngsxy[0] <= sxc[2] and sxc[0] < rngsxy[1]) and 
                (rngsxy[2] <= syc[2] and syc[0] < rngsxy[3]) ):

## Check whether this cell is excluded from excids
                kexc = 0
                if( nexc > 0 ):
                    for k in range(nexc):
                        if( i == excids[k] ):
                            kexc += 1
                            nbvrt.append(list(zip(sxc,syc)))
                            nbcel.append(i)
                            nmark += 1
                            break
                
                if( kexc < 1 ):
                    nvrts.append(list(zip(sxc,syc)))
                    ncels.append(i)

## Append excluded cell verts if any. 
    if( nmark > 0 ):
        nvrts = np.concatenate( [nvrts, nbvrt], axis=0 )
        ncels = np.concatenate( [ncels, nbcel], axis=0 )

## All done. Return projected cell vertices.

    return ( nvrts, ncels, nmark )

## End of function smcelvrglr.py.

