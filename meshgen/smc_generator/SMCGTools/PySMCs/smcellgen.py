
"""
## Function smcellgen for generating SMC grid cells with a 
## given bathymetry.  Main function uses the SMC61250 grid as 
## an example to call smcellgen.
##
## First created:    JGLi18Sep2014
## Converted into Python.    JGLi14Feb2019 
## Last modified:    JGLi18Jun2025
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

## End of recusion_add function.


def smcellgen(Bathy, ndzlonlat, mlvlxy0, FileNm='./SMC61250', 
        Global=True, Arctic=False, depmin=0.0, dshalw=0.0, 
        wlevel=0.0, GlbArcLat=84.4, **kwargs): 
    """ 
    Generate SMC grid cells from size-1 resolution bathy.
    """

    import numpy  as np
    import pandas as pd
    from smcellgen import recursion_add 
    from datetime import datetime

## Bathy domain nlon and nlat and first point zlon zlat.
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
    if(abs(xlon[-1]+dlon-xlon[0]-360.0) < 0.01*dlon):
        WrapLon = True
        NCM = int( round( 360.0/dlon ) )
        if( NCM != nlon ): 
            print(" *** NCM not matching nlon:",NCM,nlon)

## SMC grid number of levels and i=j=0 lon lat. 
    NLvl  = int(mlvlxy0[0])
    x0lon = mlvlxy0[1]
    y0lat = mlvlxy0[2]
    MFct = 2**(NLvl-1)
    MFc2 = MFct*2
    MFc3 = MFct*3

## Find out row numbers of merging parallels of sizs-1 grid.
## It must be multiple of MFct as SMC grid level requires.
    prnlat=np.zeros(20, dtype=float)
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
        print(" Global grid istr, ixpd, jstr, jxpd =", 
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
            print(" *** Regional range:",xstart,ystart,xend,yend, 
                "\n Out of bathy range:",xlon[0],ylat[0],xlon[-1],ylat[-1])
            exit()

## Work out local grid loop start/end numbers.
        yrngmax = max([ abs(ystart), abs(yend) ])
        Merg = 1
        k=10
        while( yrngmax > prnlat[k] and k < 20 ):
            k += 1
            Merg = 2**(k-10)
        print(" Regional grid lon merging factor =", Merg)
        MFMG = Merg*MFct
 
        istart=int(round((xstart-xlon[0])/(MFMG*dlon)))*MFMG
        jstart=int(round((ystart-ylat[0])/(MFct*dlat)))*MFct
        iexpnd=int(round((xend-xstart)/(MFMG*dlon)))*MFMG
        jexpnd=int(round((yend-ystart)/(MFct*dlat)))*MFct

## Adjust i/jstart if start marge is less than MFMG/MFct.
        if( istart - MFMG < 0 ): istart = istart + MFMG
        if( jstart - MFct < 0 ): jstart = jstart + MFct
        print(" Regioanl grid istr, ixpd, jstr, jxpd = \n", 
                istart, iexpnd, jstart, jexpnd) 

## Distance of Bathy SW corner to cell i=j=0 point. 
    ishft = int( round( (zlon - x0lon)/dlon - 0.5 ) )
    jequt = int( round( (zlat - y0lat)/dlat - 0.5 ) )

    print (' zlon, zlat, x0lon, y0lat, ishft, jequt = \n',  
             zlon, zlat, x0lon, y0lat, ishft, jequt)

## Check subdomain edge width for each level of resolution.
    print('Lvl, size, check_edge' ) 
    for i in range(1, NLvl+1):
        print(i, 2**(i-1), recursion_add(i))

## Check whether bathy is fit for resolution levels.
    Abrt = False

## Arctic part requires extra merging close to the Pole. 
    if( Global ): Merg = 8
    if( Arctic ):
        ArcLat = GlbArcLat
        jArc = int(round((ArcLat-y0lat)/dlat/MFct )*MFct)
## Maximum merged line is just outside the polar cell.
        Polcat = 90.0 - dlat*MFct*1.5
        k=10
        while( Polcat > prnlat[k] and k < 20 ):
            k += 1
            Merg = 2**(k-10)
        print(' Arctic and boundary j and latitude = \n', 
               jArc, jArc*dlat+y0lat, GlbArcLat)

    print(' Maximum merge factor is =', Merg )
    
## Latitude number must be multiple of MFct for global grid.
    mlat = (nlat//MFct)*MFct 
    if( Global and mlat != nlat ):
        print(" *** Latitude number unfit for global grid!")
        print(" nlat, (nlat//MFct)*MFct, MFct, NLvl = \n", 
                nlat, mlat, MFct, NLvl)
        Abrt = True

## Longitude number must be multiple of MFct*Merg. 
## Global i will be consistent to global model and wrap at 360 
## deg or i = NCM.
    LFct = MFct*Merg
    mlon = (nlon//LFct)*LFct 
    if( Global and mlon != nlon ):
        print(" *** Longitude numbers unfit for global grid!") 
        print(" nlon, mlon, LFct, NLvl = \n", 
                nlon, mlon, LFct, NLvl)
        Abrt = True

    if( Abrt ): exit()

## Initialise cell count variables
    Ns = np.zeros( (NLvl+1), dtype=int )

## Bathy is assumed to be elevation above sea level so depth below sea level 
## is negative.  Minimum depth, depmin, must be >= water level, wlevel.
    if( depmin < wlevel ):
        print(" Minimum depth is reset to water level", 
                depmin, wlevel)
        depmin = wlevel
 
## Define shallow water area maximum level just below NLvl. 
    if( dshalw >= depmin): 
        dshalw  = depmin
        NLvshlw = NLvl 
    else:
        NLvshlw = max([1, NLvl-1])

    print(' WLevel, depmin, dshalw, NLvshlw = \n', 
            wlevel, depmin, dshalw, NLvshlw)
    nshalw = 0

## Size zone parallel index
    jprold=0
   
## Loop ends of i/j-loop at bathy data end.
    iend = istart + iexpnd
    jend = jstart + jexpnd - MFct
    
## Initial smcels as a list to append cell arrays.
    smcels = []
    print(" Cell generating started at ",
            datetime.now().strftime('%F %H:%M:%S'))

## latitude j loop at step of MFct rows. 
    for j in range(jstart, jend, MFct):

## Full grid jj and latitude for this row
        jj=j + jequt
        yj=ylat[j]
        if( j % 10*MFct == 0 ):
            print( j, "row started at ", 
                 datetime.now().strftime('%H:%M:%S'))

## Find j size-changing zone and merging number, ims. 
        for jpr in range(19): 
            if( j >= jprasn[jpr] and j < jprasn[jpr+1] ): 
                jprset = jpr
                ism = 2**abs(9-jprset)
## Set maximum merging to be Merg.
        if( ism > Merg ): ism = Merg

        if( jprset != jprold ): 
            jprold = jprset
            print ("Row j, jj, x-size ism and latitude yj=", 
                        j, jj, ism, yj)

## Set i-merging factor for i-loop step.
        iFct=ism*MFct
        iFc2=iFct*2
        iFc3=iFct*3

## For global grid, loop over all longitude point.
        for i in range(istart, iend, iFct):

## Extract a sub-array from Bathy for cell generating loop.
            subathy = np.zeros((MFc3, iFc3), dtype=float) 

            if( WrapLon ): 
                ii = (i + ishft + NCM) % NCM
                for ib in range(iFc3):
                    ik = (i+ib-iFct+NCM ) % NCM
                    subathy[:,ib] = Bathy[j-MFct:j+MFc2,ik] 
            else:
                ii = i + ishft 
                subathy[:,:] = Bathy[j-MFct:j+MFc2, 
                                     i-iFct:i+iFc2]

## Define a logical array in central area to control loop
            subchck=subathy[MFct:MFc2,iFct:iFc2]<depmin 

## Count any sea points within subathy deeper than dshalw. 
            nsubdep=np.sum(subathy[MFct:MFc2,iFct:iFc2] < \
                           dshalw )

## Loop over NLvl to define different sized cells according to 
## open sea area, starting with base level of size-MFct cell.
            levl = NLvl
            while( levl > 0 ):
                if( np.sum(subchck) == 0 ):
                    break
                elif( nsubdep == 0 and levl > NLvshlw ):
                    nshalw += 1
#                   print(' Shallow water skip levl, i, j =', 
#                                              levl, i, j) 
                else:
                    jchk = 2**(levl - 1)
                    irng = jchk*ism
                    jdk = recursion_add(levl)
                    idg = jdk*ism 

                    for jb in range(0,MFct,jchk):
## No size-1 cells within 2 rows of size-changing parallel. 
                        if( ( levl > 1 ) or ( levl==1 and \
                             (jprasn[jprset]+2 <= j+jb < jprasn[jprset+1]-2) ) ):
                            for ib in range(0,iFct,irng):
## Check cell and its surrounding points are all sea points 
## to define the cell. 
                                if( (np.sum( subchck[ \
       jb:jb+jchk, ib:ib+irng] )==irng*jchk) and (np.sum( \
       subathy[jb+MFct-jdk:jb+MFct+jchk+jdk, \
       ib+iFct-idg:ib+iFct+irng+idg]<depmin ) == \
       (irng+2*idg)*(jchk+2*jdk)) ):
                                    bsum=np.sum( subathy[ \
       jb+MFct:jb+MFct+jchk, ib+iFct:ib+iFct+irng] )

## Use difference from water level to define water depth.
                                    kdepth=np.ceil( wlevel \
       -bsum/float(irng*jchk) ).astype(int)
                                    subcel=[ii+ib, jj+jb, \
                                      irng, jchk, kdepth]
                                    subchck[jb:jb+jchk, \
                                      ib:ib+irng]=False
                                    smcels.append( subcel )
                                    Ns[levl] += 1
                                    if( Ns[levl] < 3 ):  
                                        print( jchk, 
       ' size i, j, yj, kdepth=', ii+ib, jj+jb, yj, kdepth) 

## Down one level if any sea points left.
                levl -= 1 

## End of i, j loops. 

## For global grid with Arctic part, define north polar cell. 
    if( Global and Arctic ):
        j=nlat-MFct

## Full grid jj and latitude for this row
        jj=j + jequt
        yj=ylat[j] 

## Polar cell x-size is the same as surrounding cells.
        ism = Merg 
        print ("Polar cell j, jj, x-size, ism and yj= \n", 
                           j, jj, ism*MFct, ism, yj)

## Last MFct rows in Bathy merged into one polar cell.
        dsum = np.sum( Bathy[j:nlat,:] )
        kdepth = int( round( wlevel - dsum/(MFct*nlon) ) )
        smcels.append( [0, jj, MFct*ism, MFct, kdepth] )
        Ns[NLvl] += 1

## All cells are done.
    print(" *** Done all cells Ns =", Ns)
    NL = sum(Ns[:])
    print(" *** Total cells Number =", NL)
    print(" *** Shallow water number in all sizes =", nshalw) 

## Follow Qingxiang's method to sort smcels before save it.
    smcelsdf=pd.DataFrame(smcels, columns=['i','j','di','dj','kdp'])
    smcelsdf.sort_values(by=['dj','j','i'], inplace=True)
    smcels = np.array(smcelsdf)

## Cell array output format for each cell.
    fmtcel='%6d %5d %4d %3d %5d'

## Separate Arctic and global parts out of full global cells. 
    if( Arctic ):
        jbdy = MFc2
        smcArc= smcels[smcels[:,1]>=jArc]
        nbglo = smcArc[smcArc[:,1]< jArc+jbdy].shape[0]
        nbArc = smcArc[smcArc[:,1]< jArc+2*jbdy].shape[0]-nbglo
        nArct = smcArc.shape[0]
        hdr = f'{nArct:8d} {nbglo:5d} {nbArc:5d}'
        Cell_Arct = FileNm +'BArc.dat'
        print(' ... saving BArc.dat with header '+hdr )
        np.savetxt(Cell_Arct, smcArc, fmt=fmtcel, header=hdr, 
                   comments='')
## Separate Global part out of the cells by jArc value
        smcels = smcels[smcels[:,1]<jArc+2*jbdy]
        Ns[NLvl] = Ns[NLvl] - nArct + nbArc + nbglo

## Recount global part cell numbers and deduct Arctic cells.
    Ns[0] = smcels.shape[0]
    Nsum = sum( Ns[1:] )
    if( Nsum != Ns[0] ):
        print(" *** Total number not matching sub-sum:", Ns[0], Nsum)
    
## Save the cell array, anyway.
    hdr = ''.join( [f"{n:8d}" for n in Ns] ) 
    print(' ... saving Cels.dat with header '+hdr )
    Cell_file = FileNm+'Cels.dat'
    np.savetxt(Cell_file, smcels, fmt=fmtcel, header=hdr, comments='')

    print( " smcellgen finished at", 
          datetime.now().strftime('%F %H:%M:%S') )

    return 0

## End of smcellgen function.


def main():

## Import relevant modules and functions
    import numpy   as np
    import netCDF4 as nc 

    Wrkdir='../tmpfls/'
    bathyf='../Bathys/Bathy088_059deg.nc' 
    Global= True
    Arctic= True
    GridNm='SMC61250'

## Open and read bathymetry data.
    datas = nc.Dataset(bathyf)

    print(datas)            ## Print information about the dataset.

    print(datas.__dict__)

    print(datas.__dict__['description'])

    for var in datas.dimensions.values(): print(var)

    nlat = datas.dimensions['lat'].size
    nlon = datas.dimensions['lon'].size
    dlat = 180.0 / float(nlat)
    dlon = 360.0 / float(nlon)

    print(" nlat, nlon, dlat, dlon =", nlat, nlon, dlat, dlon )

    xlon = datas.variables['lon'][:]
    ylat = datas.variables['lat'][:]
    Bathy= datas.variables['elevation'][:,:]
    depthmax = np.amin(Bathy)
    hightmax = np.amax(Bathy)
    print(' Bathy range=', depthmax, hightmax)
    print(' Bathy shape=', Bathy.shape )
    print(' x_lon range=', xlon[0], xlon[nlon-1])
    print(' y_lat range=', ylat[0], ylat[nlat-1])

    datas.close()

## Pack bathy parameters into one list.
    ndzlonlat=[ nlon, nlat, dlon, dlat, xlon[0], ylat[0] ]

## Check top row bathy values
    print('Bathy[',nlat-1,[f'{i:d}' for i in range(0,nlon,1024)],']')
    print(Bathy[nlat-1,0:nlon:1024])

## Decide resolution levels and SMC grid i=j=0 lon-lat.
    NLvl = 4
    x0lon = 0.0
    y0lat = 0.0
    mlvlxy0 = [ NLvl, x0lon, y0lat ]

    smcellgen(Bathy, ndzlonlat, mlvlxy0, FileNm=Wrkdir+GridNm, 
              Global=Global, Arctic=Arctic)
    
## End of main program.

if __name__ == '__main__':
    main()

## End of smcellgen.py program. 

