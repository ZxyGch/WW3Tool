"""
## Function smcellSWE to generate a global SMC grid for SWEs model. 
## The main() function uses the SMC1R3 grid as an example.
##
##  First created:        JGLi06Oct2021
##  Last modified:        JGLi12May2025
##
"""

def smcellSWE(zdlonlat, nlvlmdep, FileNm='./SMC1R3', 
              Global=True, Arctic=True, ArcLat=77.0):
    """ Generate SMC full grid cells from given size-1 info. """

    import numpy  as np
    import pandas as pd

## Bathy domain nlon and nlat and reference point zlon zlat.
    zlon = zdlonlat[0] 
    zlat = zdlonlat[1]
    dlon = zdlonlat[2]
    dlat = zdlonlat[3]
    nlon = int(round(360.0/dlon))
    nlat = int(round(180.0/dlat))
    nla2 = nlat//2
    print(" nlon, nlat, nla2 =", nlon, nlat, nla2 )

## SMC grid number of levels and i=j=0 lon lat. 
    NLvel = int(nlvlmdep[0])
    MDeep = int(nlvlmdep[1])

## Define different level cell sizes.
    MFn = np.array([2**n for n in range(NLvel)], dtype=int)
    MFct = MFn[-1]
    print(" NLvel, MDeep =", NLvel, MDeep)
    print(" MFn[:] = ", MFn)

## Check dlon meets periodic boundary requirement.
    dlonerror = 360.0 - nlon*dlon
    if( abs(dlonerror/dlon) > 1.0E-4 ):
        print(" DLon error too large for periodic condition.", dlonerror, dlon)
        exit()

## Find out row numbers of merging parallels at sizs-1 resolution.
## It must be multiple of MFct rows as multi-resolution levels require.
    xlon = np.arange(nlon)*dlon + zlon
    ylat = np.arange(nla2)*dlat + zlat

    prnlat=np.array([60.000000, 75.522486, 82.819245, 86.416678, 88.209213,
                     89.104712, 89.552370, 89.776188, 89.888094, 89.944047])
#   jprasn=np.fix( (prnlat-zlat+0.5*dlat)/(dlat*MFct) )*MFct
    jprasn=np.fix( (prnlat-zlat)/(dlat*MFct) )*MFct
    jprasn=jprasn.astype(int)

    print (' North hemi parallels =', jprasn)

## If Arctic part is required extra merging will be required in the Arctic part. 
    if( Global ): 
## Maximum merged line is just outside the polar cell at base resolution.
        Polcat = 90.0 - dlat*MFct*1.5
        k=0
        while( Polcat > prnlat[k] and k < 10 ):
            k += 1
            Merg = 2**k
    print(' Maximum merge factor is =', Merg )

## Find out Arctic part starting row number by given ArcLat latitude value.
    if( Arctic ):
        jArc   = int( round( (ArcLat-zlat)/dlat/MFct )*MFct )
        print(' Arctic and boundary j and latitude =', jArc, jArc*dlat+zlat, ArcLat)
        smcbdy=[]
        smcArc=[]
    
## Longitude number needs to be multiple of MFct*Merg due to zonal merging.
## Global i will be consistent to global model and wrap at 360 deg or NCM.
    LFct = MFct*Merg
    mlon = (nlon//LFct)*LFct 
    if( Global and mlon != nlon ):
        print(" Longitude numbers unfit for global grid with level ", NLvel )
        print(" nlon, mlon, LFct =", nlon, mlon, LFct )
        exit()

## Initialise cell count variables
    Ns = np.zeros( (NLvel+1), dtype=int )

## Size zone parallel index
    jprold=0
    jprset=0
    ism=1
   
## Initial smcels as a list to append cell arrays.
    smcels = []

## Define refined area i, j ranges for SMC1R3 grid if NLvel==3.
## Latitude from 15N (j=60) to 50N (j=200), relaxing width 8.
## Longitude range is roughly from 14E (i=40) to 84E (i=240).
    ijsn = [40, 60, 240, 200] 
    ijs1 = [48, 68, 232, 192] 

## For each MFct rows except for the last MFct rows.
    for j in range(0, nla2-MFct, MFct):

## Full grid jj and latitude for this row
        yj=ylat[j]
        if( j % 10*MFct == 0 ):
            print ( j, "row reached." )

## Find j size-changing zone and work out merging sizes ims.
        for jpr in range(10): 
            if( j >= jprasn[jpr] and j < jprasn[jpr+1] ):
                jprset = jpr+1
                ism = 2**abs(jprset)
## Set maximum merging to be Merg.
        if( ism > Merg ): ism = Merg

        if( jprset != jprold ): 
            jprold = jprset
            print ("Row j, x-size ism and latitude yj=", j, ism, yj)

## Set i-merging factor for i-loop step.
        iFn=ism*MFn
        iFct=iFn[-1]
        print(" j, ism, iFn =", j, ism, iFn)

## For global grid, loop over all longitude point.
        for i in range(0, nlon, iFct):

## North hemisphere refined areas if NLevel >= 3.
            if( ( NLvel >= 3 ) and \
                (ijsn[0] <= i < ijsn[2]) and \
                (ijsn[1] <= j < ijsn[3]) ):
                for jk in range(0,2*MFn[-2], MFn[-2]):
                    for ik in range(0,2*iFn[-2], iFn[-2]):
                        if( (ijs1[0] <= i+ik < ijs1[2]) and \
                            (ijs1[1] <= j+jk < ijs1[3]) ):
## NLevel-2 (size-1) cells wihtin refined zone.
                            for jm in range(0, 2*MFn[-3], MFn[-3]):
                                for im in range(0,2*iFn[-3], iFn[-3]):
                                    subcel=[i+ik+im, j+jk+jm, \
                                            iFn[-3], MFn[-3], MDeep]
                                    smcels.append( subcel )
                                    Ns[-3] += 1
                        else:
## NLevel-1 (size-2) cells within relaxation zone.
                            subcel=[i+ik, j+jk, \
                                    iFn[-2], MFn[-2], MDeep]
                            smcels.append( subcel )
                            Ns[-2] += 1

            else:
## Base resolution northern hemisphere cells.
                subcel=[i, j, iFct, MFct, MDeep]

                if( Arctic and j >= jArc ):
## Append cells to Arctic part.
                    smcArc.append( subcel )
                    if( j < jArc + 4*MFct ): 
## Also append boundary cells to smcbdy for 4 rows. 
                        smcbdy.append( subcel )
                else:
## Append the cells to global part. 
                    smcels.append( subcel )
                    Ns[-1] += 1

## Southern hemisphere are all base resolution cells, no refinement. 
            substh=[i, -j-MFct, iFct, MFct, MDeep]
            if( Arctic and j >= jArc ):
                smcArc.append( substh )
                if( j < jArc + 4*MFct ): 
                    smcbdy.append( substh )
            else:
                smcels.append( substh )
                Ns[-1] += 1
## End of i, j loops. 

## Two polar cells with the same size as the last row cells.
    npl=2
    j=nla2-MFct
    subcel=[0,  j, iFct, MFct, MDeep]
    substh=[0, -j-MFct, iFct, MFct, MDeep]

    if( Arctic ):
        smcArc.append( subcel )
        smcArc.append( substh )
    else:
        smcels.append( subcel )
        smcels.append( substh )
        Ns[-1] += 2

## Cell array output format for each cell.
    fmtcel='%6d %5d %4d %3d %5d'
    nArct = 0

    if( Arctic ):
## Conversion to np.array is needed for array operations. 
        smcArcnp = np.array(smcArc)
        smcbdynp = np.array(smcbdy)
        jbdy = MFct*2
        nArct = smcArcnp.shape[0]

## Count boundary cells for global and Arctic parts.
        nbGlo = smcbdynp[ np.abs(smcbdynp[:,1]+0.5) > jArc+jbdy ].shape[0]
        nbArc = smcbdynp.shape[0] - nbGlo
        hdr = f'{nArct:8d} {nbArc:5d} {nbGlo:5d} {npl:5d}'

        ArcFl = FileNm +'BArc.dat'
        print(' ... saving BArc.dat with header '+hdr )
        np.savetxt(ArcFl, smcArcnp, fmt=fmtcel, header=hdr, \
                   comments='')

## Using pandas data frame to sort global part smcels before save it.
    smcelsdf = pd.DataFrame(smcels, columns=['i','j','di','dj','kdp'])
    smcelsdf.sort_values(by=['dj','j','i'], inplace=True)
    smcelsnp = np.array(smcelsdf)

## Append unsorted boundary cells to end of global part.
    if( Arctic ):
         smcelsnp = np.vstack( (smcelsnp, smcbdynp) )
         Ns[-1] += (nbArc + nbGlo)

## Save all or global part cells.
    GloFl = FileNm +'Cels.dat'
    Ns[0] = sum(Ns[1:])
    hdr = ''.join( [f"{n:8d}" for n in Ns] ) 
    print(' ... saving Cels.dat with header '+hdr )
    np.savetxt(GloFl, smcelsnp, fmt=fmtcel, header=hdr, \
                   comments='')

## All done, total cell number.
    print( " smcellSWE finished. Total cell NC=", Ns[0]+nArct )

    return 0

## End of smcellSWE function.


## Main program to generate SMC1R3 grid.

def main():

## Import relevant modules and functions
    import sys
    import numpy   as np

## Working dir and default setting.
    Wrkdir='./'
    Global= True
    Arctic= True
    ArcLat= 77.0
    GridInfo='./GridInfoSMC1R3.txt'

## Read grid information from default file or specific one.
    nagv = len(sys.argv) 
    if( nagv > 1 and len(sys.argv[1]) > 2 ): GridInfo=sys.argv[1]
    if( nagv > 2 and len(sys.argv[2]) > 2 ): ArcLat=float(sys.argv[2])
    print(" GridInfo and ArcLat set as ", GridInfo, ArcLat)

    with open( GridInfo, 'r' ) as flhdl:
        nxline = flhdl.readline().split()
        GridNm = nxline[0]
        NLevel = int(nxline[1])
        print(" Input grid name and NLevl= ", GridNm, NLevel)
        nxline = flhdl.readline().split()
        zdlonlat = np.array( nxline, dtype=float ) 

    print(" Input grid zlon zlat dlon dlat = \n", zdlonlat)

## Decide resolution levels and SMC grid i=j=0 lon-lat.
    MDeep = 100
    nlvlmdep = [ NLevel, MDeep ]

    smcellSWE(zdlonlat, nlvlmdep, FileNm=Wrkdir+GridNm, 
              Global=Global, Arctic=Arctic, ArcLat=ArcLat)
    
## End of main program.

if __name__ == '__main__':
    main()

## End of smcellSWE.py program. 

