"""
## Function to generate boundary cells for a rectangular regional model.
## It is a complimentary function to smcellgen, which generates the inner 
## cells for a regional model, apart of its global grid capacity.
##
## First created:    JGLi07Jul2023
## Last modified:    JGLi16Jun2025
##
"""

def recursion_add(n):
    """ 
    Subdomain edge width for size-n cell checking. 
    """
    if( n <= 2 ): 
        return 0
    else:
        return  2**(n-2)+recursion_add(n-1)

##  End of recusion_add function.


def smcellbdy(Bathy, ndzlonlat, mlvlxy0, FileNm='./SMC61250', 
        Global=True, Arctic=False, depmin=0.0, dshalw=0.0, 
        wlevel=0.0, msea=1, GlbArcLat=84.4, **kwargs ):
    """ 
    Generate SMC grid boudarny cells from regional bathy. 
    """

    import numpy   as np
    import pandas  as pd
    from smcellbdy import recursion_add
    from datetime import datetime

## Bathy domain nlon and nlat and south-west first point zlon zlat.
    nlon = int(ndzlonlat[0])
    nlat = int(ndzlonlat[1])
    dlon = ndzlonlat[2]
    dlat = ndzlonlat[3]
    zlon = ndzlonlat[4]
    zlat = ndzlonlat[5]
    xlon = np.arange(nlon)*dlon + zlon
    ylat = np.arange(nlat)*dlat + zlat

## Check whether bathy could wrap in longitude range.
    WrapLon = False
    if( abs(xlon[-1]+dlon - xlon[0] - 360.0) < 0.01*dlon ):
        WrapLon = True
        NCM = int( round( 360.0/dlon ) )
        if( NCM != nlon ): 
            print(" *** NCM not matching nlon:", NCM, nlon)

## SMC grid number of levels and i=j=0 lon lat. 
    NLvl  = int(mlvlxy0[0])
    x0lon = mlvlxy0[1]
    y0lat = mlvlxy0[2]
    MFct = 2**(NLvl-1)

## Find out row numbers of merging parallels of sizs-1 grid.
## It must be multiple of MFct as SMC grid level requires.
    prnlat=np.zeros((20), dtype=float)
    prnlat[10:]=np.array([60.000000, 75.522486, 82.819245, 
               86.416678, 88.209213, 89.104712, 89.552370, 
               89.776188, 89.888094, 89.944047])
    prnlat[:10]=-1.0*prnlat[10:][::-1]

    jprasn=np.rint( (prnlat-zlat+0.5*dlat)/(dlat*MFct) )*MFct
    jprasn=jprasn.astype(int)

    print (' South hemi paralles =',  jprasn[:10])
    print (' North hemi paralles =',  jprasn[10:])

## Global grid uses full bathymetry file.
    if( Global ):
        istart = 0
        jstart = MFct
        iexpnd = nlon
        jexpnd = nlat - MFct 
        print( " Global grid istr, ixpd, jstr, jxpd =", 
                 istart, iexpnd, jstart, jexpnd) 
## Regional grid requires SW and NE corner locations.
    else:
        xstart = mlvlxy0[3]
        ystart = mlvlxy0[4]
        xend   = mlvlxy0[5]
        yend   = mlvlxy0[6]

## Check regional grid range within bathymetry range.
        if( xstart < xlon[0] or xend > xlon[-1] or
            ystart < ylat[0] or yend > ylat[-1] ):
            print(" *** Regional range:", xstart, ystart, xend,    yend, 
                "\n Out of bathy range:", xlon[0],ylat[0],xlon[-1],ylat[-1])
            exit()

## Work out local grid loop start/end numbers.
        yrngmax = max([ abs(ystart), abs(yend) ])
        Merg = 1
        k=10
        while( yrngmax > prnlat[k] and k < 20 ):
            k += 1
            Merg = 2**(k-10)
        print(" Regional grid longitude merging factor =", Merg )
        MFMG = Merg*MFct
 
        istart = int(round( (xstart-xlon[0])/(MFMG*dlon) ))*MFMG
        jstart = int(round( (ystart-ylat[0])/(MFct*dlat) ))*MFct
        iexpnd = int(round( (xend - xstart + dlon)/(MFMG*dlon) ))*MFMG
        jexpnd = int(round( (yend - ystart + dlat)/(MFct*dlat) ))*MFct

## Adjust i/jstart if start marge is less than MFMG/MFct.
        if( istart < 0 ): istart = istart + MFMG
        if( jstart < 0 ): jstart = jstart + MFct
        print( " Regioanl grid istr, ixpd, jstr, jxpd = \n",
                 istart, iexpnd, jstart, jexpnd) 

## Work out boundary edge starting i, j values.
        ibdy0 = istart; ibdyn = istart + iexpnd - MFMG
        jbdy0 = jstart; jbdyn = jstart + jexpnd - MFct 
        print (' Boundary edge i0, in, j0, jn =', ibdy0, ibdyn, jbdy0, jbdyn )

## Distance of Bathy south-west to cell i=j=0 point as ishft and jequt.
    ishft = int( round( (zlon - x0lon)/dlon - 0.5 ) )
    jequt = int( round( (zlat - y0lat)/dlat - 0.5 ) )

    print (' zlon, zlat, x0lon, y0lat, ishft, jequt = \n', 
             zlon, zlat, x0lon, y0lat, ishft, jequt )

## Check edge width for each level of resolution.
    print('Lvl, size, check_edge' ) 
    for i in range(1,NLvl+1):
        print(i, 2**(i-1), recursion_add(i) )

## Initialise cell count variables
    Ns = np.zeros((NLvl+1), dtype=int)

## Bathy is assumed to be elevation above sea level so depth below sea level 
## is negative.  Minimum depth, depmin, must be >= water level, wlevel.
    if( depmin < wlevel ):
        print(" Minimum depth is adjusted equal to water level", depmin, wlevel)
        depmin = wlevel

## Define shalow water area maximum level to be 1 level below NLvl. 
    if( dshalw >= depmin): 
        dshalw=depmin
        NLvshlw = NLvl 
    else:
        NLvshlw = max([1, NLvl-1])
    print(' Water level, minimum and shallow water depths, and NLvshlw = \n',
            wlevel, depmin, dshalw, NLvshlw)

## Size zone parallel index
    jprold=0
   
## Loop ends of i/j-loop ends at bathy data end.
    iend = istart + iexpnd
    jend = jstart + jexpnd

## Initial smcels as a list to append cell arrays.
    smcels = []

    print( " Cell generating started at "+ datetime.now().strftime('%F %H:%M:%S') )

## For each MFct rows except for the last MFct rows and the bottom MFct rows
    for j in range(jstart, jend, MFct):

## Full grid jj and latitude for this row
        jj=j + jequt
        yj=ylat[j]
        if( j % 10*MFct == 0 ):
            print ( j, "row started at "+ datetime.now().strftime('%H:%M:%S') )

## Find j size-changing zone and work out merging sizes ims in the zone 
        for jpr in range(19): 
            if( j >= jprasn[jpr] and j < jprasn[jpr+1] ):
                jprset = jpr
                ism = 2**abs(9-jprset)
## Set maximum merging to be 64 or 2**6
        if( ism > Merg ): ism = Merg

        if( jprset != jprold ): 
            jprold = jprset
            print ("Row j, jj, x-size ism and latitude yj=", j, jj, ism, yj)

## Set i-merging factor for i-loop step.
        iFct=ism*MFct

## For global grid, loop over all longitude point.
        for i in range(istart, iend, iFct):

## Declare a sub-array for cell generating.
            subathy = np.zeros((MFct, iFct), dtype=float)

            if( WrapLon ):
                ii = (i + ishft + NCM) % NCM
            else:
                ii = i + ishft

## Extract a sub-array from Bathy for cell generating.
            if( (j == jbdy0 or j == jbdyn) ):
                subathy[:,:] = Bathy[j:j+MFct,i:i+iFct]
            elif( i == ibdy0 or i == ibdyn ):
                subathy[:,:] = Bathy[j:j+MFct,i:i+iFct]
            else:
## None boundary area set bathy to be land above depmin.
                subathy[:,:] = 999.0

## Define a logical array in central area to control loop
            subchck = subathy[:,:] < depmin

## Loop over NLvl to define different sized cells according to open sea area,
## starting with base level of size-MFct cell but exclude level 1 cells.
            levl = NLvl
            while( levl > 1 ):
                if( np.sum(subchck) == 0 ):
                    break
                else:
                    jchk = 2**(levl - 1)
                    irng = jchk*ism
                    jdk = recursion_add(levl)
                    idg = jdk*ism 

                    for jb in range(0,MFct,jchk):
                        for ib in range(0,iFct,irng):
## Check cell area and its surrounding points are all sea points or 
## at level one 2 and there are 2 or more sea points to define a boundary cell. 
                            nsea = np.sum( subchck[jb:jb+jchk,ib:ib+irng] ) 
                            if( ( nsea == irng*jchk ) or ( levl == 2 and nsea >= msea ) ): 
                                bsum = np.sum( subathy[jb:jb+jchk, ib:ib+irng] )
## Use ceilling diffence from water level to define water depth.  JGLi02Nov2023
                                kdepth = np.ceil( wlevel - bsum/float(irng*jchk) ).astype(int)
                                subcel=[ii+ib, jj+jb, irng, jchk, max( [1,kdepth] )]
                                subchck[jb:jb+jchk,ib:ib+irng] = False
                                smcels.append( subcel )
                                Ns[levl] += 1
                                if( Ns[levl] < 3 ):  
                                    print( jchk, ' size i, j, yj, kdepth= \n',
                                           ii+ib, jj+jb, yj, kdepth )

## Down one level if any sea points left.
                levl -= 1 

## End of i, j loops. 

## All cells are done.
    print(  " *** Done all cells Ns =", Ns )
    NL = sum(Ns[:])
    print(  " *** Total cells Numbr =", NL )

## Follow Qingxiang Liu's method to sort smcels before save it.
    smcelsdf = pd.DataFrame(smcels, columns=['i','j','di','dj','kdp'])
    smcelsdf.sort_values(by=['dj','j','i'], inplace=True)
    smcels = np.array(smcelsdf)

## Cell array output format for each cell.
    fmtcel='%6d %5d %4d %3d %5d'

## Recount global part cell numbers and deduct size-8 Arctic cells.
    Ns[0] = smcels.shape[0]
    if( sum(Ns[1:]) != Ns[0] ):
        print( "*** Warning total cell number does not match sub-cell sum:", Ns[0], sum(Ns[1:]) )
    
## Save the cell array, anyway.
    hdr = ''.join( [f"{n:8d}" for n in Ns] ) 
    print(' ... saving Cels.dat with header '+hdr )
    Cell_file = FileNm+'Bdys.dat'
    np.savetxt(Cell_file, smcels, fmt=fmtcel, header=hdr, comments='')

    print( " smcellbdy finished at %s " % datetime.now().strftime('%F %H:%M:%S') )

## End of smcellbdy function.


def main():

## Import relevant modules and functions
    import numpy   as np
    import pandas  as pd
    import netCDF4 as nc
    from datetime import datetime

    Wrkdir='../Bathys/'
    bathyf='Amm15Bathy.nc' 
    Global= False
    Arctic= False
    GridNm='AMM153km'

## Open and read bathymetry data.
    datas = nc.Dataset(bathyf)

    print(datas)            ## Print information about the dataset.

    nlat = datas.dimensions['lat'].size
    nlon = datas.dimensions['lon'].size
    zlat = -7.2942; zlon = -10.8895  
    dlat =  0.0135; dlon = 0.0135
    ylat = zlat + np.arange(nlat)*dlat
    xlon = zlon + np.arange(nlon)*dlon

    print(" nlat, nlon, dlat, dlon =", nlat, nlon, dlat, dlon )
    print(" Grid range x0, y0, xn, yn =",xlon[0],ylat[0],xlon[-1],ylat[-1] )

## Pack bathy parameters into one list.
    ndzlonlat=[ nlon, nlat, dlon, dlat, zlon, zlat ]

    Bathy= - datas.variables['Bathymetry'][:,:]
    depthmax = np.amin(Bathy)
    hightmax = np.amax(Bathy)
    print(' Bathy range=', depthmax, hightmax)
    print(' Bathy shape=', Bathy.shape )

    datas.close()

## Check top row bathy values
    print('Bathy[',nlat-1,[f'{i:d}' for i in range(0,nlon,1024)],']')
    print(Bathy[nlat-1,0:nlon:1024])

## Decide resolution levels and SMC grid i=j=0 lon-lat.
    NLvl = 2

## For AMM15 domain, the refrence point is set to be at the SW corner of
## the AMM15 rotated grid, half-grid length offset for the true cell corner. 
    x0lon = xlon[0] - 0.5*dlon 
    y0lat = ylat[0] - 0.5*dlat 
    print( GridNm+" grid x0lon, y0lat =", x0lon, y0lat )

## Note AMM15 ocean model bathy has odd number of rows (1345) so the last row
## ylat[-1] is droped for the 2-level grid for even number of size-1 rows.
    depmin=  5.0
    dshalw= -150.0
    mlvlxy0 = [ NLvl, x0lon, y0lat, xlon[0], ylat[0], xlon[-1], ylat[-2] ]

    smcellbdy(Bathy, ndzlonlat, mlvlxy0, FileNm=Wrkdir+GridNm, Global=Global, 
              Arctic=Arctic, depmin=depmin, dshalw=dshalw)

## End of main program.

if __name__ == '__main__':
    main()

## End of smcellbdy.py program.

