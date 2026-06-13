"""
##  smcelvrts function generates the polygon vertices used to draw cells
##  on grid plots or output field plots when field colour is filled. 
##  First Created:    12 Jan 2021     Jian-Guo Li
##  Last Modified:     8 Apr 2025     Jian-Guo Li
##
## usage:  nvrts, ncels, svrts, scels, nsmrk = smcelvrts( cel, zdlnlt, 
##           rdpols, rngsxy, excids=[], NArB=[], Pnrds=3.0 )
##
## input:  cel --- cell array to be projected. 
##         zdlnlt = [zrlon, zrlat, dxlon, dylat] --- i=j=0 lon-lat and size-1 increments.
##         rdpols = [radius, pangle, plon, plat] --- projection radius, angle, and pole.
##         rngsxy = [-10.0, 10.0,-13.0, 10.0] --- plot ranges (assume radius = 10.0 ).
##         excids = [] --- excluded cell ids to be appended at the end for marks. 
##         NArB = [] --- defaul empty list. Provided unempty if polar part is present.
##         Pnrds = 3.0 --- defaul distance from projection point as 3 sphere radius.
## output: nvrts, ncels --- cell vertices and cell ids on the northern hemisphere.
##         svrts, scles --- cell vertices and cell ids on the southern hemisphere. 
##         nsmrk --- numbers of marked cells on north and south hemispheres. 
##
"""

def smcelvrts( cel, zdlnlt, rdpols, rngsxy, excids=[], NArB=[], Pnrds=3.0):

    import numpy as np
    from steromap import steromap

##  Process input parameters.
    zrlon=zdlnlt[0]; zrlat=zdlnlt[1]
    dxlon=zdlnlt[2]; dylat=zdlnlt[3]
    nc = cel.shape[0]
    ng = nc
    nba = nbg = 0
    Arctic = False

    if( len(NArB) > 2 ):
        Arctic = True
        na  = int( NArB[0] )
        nba = int( NArB[1] )
        nbg = int( NArB[2] )
        ng  = nc - na
##  Default 1 polar cell.
        if( len(NArB) > 3 ):
            npl = int( NArB[3] )
        else:
            npl = 1

    nexc = len(excids)
    if( nexc > 0 ): print( " Marked cell numbers =", nexc )

##  Rotated pole lon-lat and projection angle
    radius = rdpols[0]
    pangle = rdpols[1]
    plon =   rdpols[2]
    plat =   rdpols[3]

    if( pangle <= 0.0 ): 
        print( ' Pangl has to be 0 < Pangl <= 90.0!' )
        print( ' Input Pangl is equal to', pangle )
        return 

    if( radius != 10.0 ):
        print( ' Projection radius is not the default 10.0 !' )
        print( ' Input radius is equal to', radius )

##  Initial verts and ncels variable for polycollections.
    nvrts = []
    ncels = []
    svrts = []
    scels = []
    nmark  = 0        
    smark  = 0
    if( nexc > 0 ):
        nbvrt = []
        nbcel = []
        sbvrt = []
        sbcel = []

##  Loop over all cells except Polar Cell, if any.
    for i in range(nc):

        if( (i < ng-nbg) or (i >= ng+nba) ):

##  Polar cell is projected as a square box
            if( Arctic and i >= nc-npl ):
                slon=np.arange(4)*90.0
##  Use off-pole side latitudes for polar cells.
                if( cel[i,1] > 0 ):    ## North polar cell.
                    slat=np.zeros(4) + cel[i,1]*dylat + zrlat
                else:          ## must be south polar cell.
                    slat=np.zeros(4) + (cel[i,1]+cel[i,3])*dylat + zrlat

##  Other cells are rectangular boxes by their sizes.
            else:
                xc=np.array( [cel[i,0],cel[i,0]+cel[i,2],cel[i,0]+cel[i,2],cel[i,0]] )
                yc=np.array( [cel[i,1],cel[i,1],cel[i,3]+cel[i,1],cel[i,3]+cel[i,1]] )
                slon=xc*dxlon + zrlon
                slat=yc*dylat + zrlat

##  Convert slat slon to elat elon with given new pole
            elat, elon, sxc, syc = steromap(slat, slon, plat, plon,
                  Pangl=pangle, radius=radius, Onecl=True, Pnrds=Pnrds)

##  Check projected cell position within range and separate two hemispheres.
            if( (rngsxy[0] < sxc[0] < rngsxy[1]) and 
                (rngsxy[2] < syc[0] < rngsxy[3]) ):

##  Check whether this cell is excluded from excids
                kexc = 0
                if( nexc > 0 ):
                    for k in range(nexc):
                        if( i == excids[k] ):
                            kexc += 1
                            if( elat[0] >= 0.0 ): 
                                nbvrt.append(list(zip(sxc,syc)))
                                nbcel.append(i)
                                nmark += 1
                            else:
                                sbvrt.append(list(zip(sxc,syc)))
                                sbcel.append(i)
                                smark += 1
                            break
                
                if( kexc < 1 ):
                    if ( elat[0] >= 0.0 ): 
                        nvrts.append(list(zip(sxc,syc)))
                        ncels.append(i)
                    else:
                        svrts.append(list(zip(sxc,syc)))
                        scels.append(i)


##  Append excluded cell verts if any. 
    if( nmark > 0 ):
        nvrts = np.concatenate( [nvrts, nbvrt], axis=0 )
        ncels = np.concatenate( [ncels, nbcel], axis=0 )
    if( smark > 0 ):
        svrts = np.concatenate( [svrts, sbvrt], axis=0 )
        scels = np.concatenate( [scels, sbcel], axis=0 )
    nsmrk = [nmark, smark]

## All done. Return projected cell vertices.

    return ( nvrts, ncels, svrts, scels, nsmrk )

## End of smcelvrts.py function.

