"""
##  Function smcellful to generate a full global SMC grid. 
##  The main() function uses the SMC1d grid as an example.
##
##  First created:        JGLi06Oct2021
##  Last modified:        JGLi03Feb2025
##
"""

def main():

##  Import relevant modules and functions
    import sys
    import numpy   as np

    Wrkdir='./'
    Global= True
    Arctic= False
    GridNm='SMC1d'

##  Read grid information from default file or specific one.
    GridInfo='./SMC1dinfo.dat'
    NLvl = 1
    nagv = len(sys.argv) 
    if( nagv > 1 and len(sys.argv[1]) > 2 ): GridInfo=sys.argv[1]
    if( nagv > 2 and len(sys.argv[2]) > 0 ): NLvl=int(sys.argv[2])

    zdlonlat = np.genfromtxt(GridInfo, dtype=float, skip_header=1)
    print(" Input grid zlon zlat dlon dlat and NLvl= \n", zdlonlat, NLvl)

##  Decide resolution levels and SMC grid i=j=0 lon-lat.
    MDeep = 10
    nlvlmdep = [ NLvl, MDeep ]

    smcellful(zdlonlat, nlvlmdep, FileNm=Wrkdir+GridNm, 
              Global=Global, Arctic=Arctic)
    
##  End of main program.


def smcellful(zdlonlat, nlvlmdep, FileNm='./SMC1d', 
              Global=True, Arctic=False,  **kwargs ): 
    """ Generate SMC full grid cells from given size-1 info. """

    import numpy   as np
    import pandas  as pd

##  Bathy domain nlon and nlat and south-west first point zlon zlat.
    zlon = zdlonlat[0] 
    zlat = zdlonlat[1]
    dlon = zdlonlat[2]
    dlat = zdlonlat[3]
    nlon = int(round(360.0/dlon))
    nlat = int(round(180.0/dlat))
    nla2 = nlat//2
    print(" nlon, nlat, nla2 =", nlon, nlat, nla2 )

##  SMC grid number of levels and i=j=0 lon lat. 
    NLvel = int(nlvlmdep[0])
    MDeep = int(nlvlmdep[1])
    MFct = 2**(NLvel-1)
    print(" NLvel, MFct, MDeep =", NLvel, MFct, MDeep)

##  Check dlon meets periodic boundary requirement.
    dlonerror = 360.0 - nlon*dlon
    if( abs(dlonerror/dlon) > 1.0E4 ):
        print(" DLon error too large for periodic condition.", dlonerror, dlon)
        exit()

##  Find out when the row numbers of merging parallels of sizs-1 grid.
##  It has to be multiple of MFct rows as the resolution levels require.

    xlon = np.arange(nlon)*dlon + zlon
    ylat = np.arange(nla2)*dlat + zlat

    prnlat=np.zeros(10, dtype=float)
    prnlat=np.array([60.000000, 75.522486, 82.819245, 86.416678, 88.209213,
                     89.104712, 89.552370, 89.776188, 89.888094, 89.944047])

#   jprasn=np.rint( (prnlat-zlat+0.5*dlat)/(dlat*MFct) )*MFct
    jprasn=np.fix( (prnlat-zlat+0.5*dlat)/(dlat*MFct) )*MFct
    jprasn=jprasn.astype(int)

    print (' North hemi paralles =', jprasn)

##  If Arctic part is required extra merging will be required in the Arctic part. 
    if( Global ): 
##  Maximum merged line is just outside the polar cell at base resolution.
        Polcat = 90.0 - dlat*MFct*1.5
        k=0
        while( Polcat > prnlat[k] and k < 10 ):
            k += 1
            Merg = 2**k
    print(' Maximum merge factor is =', Merg )

    if( Arctic ):
        ArcLat = 84.8
        jArc   = int( round( (ArcLat-zlat)/dlat/MFct )*MFct )
        print(' Arctic and boundary j and latitude =', jArc, jArc*dlat+zlat, ArcLat)

    
##  Longitude number needs to be multiple of MFct*Merg due to zonal merging.
##  Global i will be consistent to global model and wrap at 360 deg or NCM.
    LFct = MFct*Merg
    mlon = (nlon//LFct)*LFct 
    if( Global and mlon != nlon ):
        print(" Longitude numbers unfit for global grid with level ", NLvel )
        print(" nlon, mlon, LFct =", nlon, mlon, LFct )
        exit()

##  Initialise cell count variables
    Ns = np.zeros( (NLvel+1), dtype=int )

##  Size zone parallel index
    jprold=0
    jprset=0
    ism=1
   
##  Initial smcels as a list to append cell arrays.
    smcels = []

##  For each MFct rows except for the last MFct rows and the bottom MFct rows
    for j in range(0, nla2, MFct):

##  Full grid jj and latitude for this row
        yj=ylat[j]
        if( j % 10*MFct == 0 ):
            print ( j, "row reached." )

##  Find j size-changing zone and work out merging sizes ims in the zone 
        for jpr in range(10): 
            if( j >= jprasn[jpr] and j < jprasn[jpr+1] ):
                jprset = jpr+1
                ism = 2**abs(jprset)
##  Set maximum merging to be 64 or 2**6
        if( ism > Merg ): ism = Merg

        if( jprset != jprold ): 
            jprold = jprset
            print ("Row j, x-size ism and latitude yj=", j, ism, yj)

##  Set i-merging factor for i-loop step.
        iFct=ism*MFct
        print(" j, ism, iFct =", j, ism, iFct)

##  For global grid, loop over all longitude point.
        for i in range(0, nlon, iFct):
            subcel=[i, j, ism, 1, MDeep]
            smcels.append( subcel )
            Ns[1] += 1

##  Mirror southern hemisphere row for all j > 0
        if( j > 0 ):
            for i in range(0, nlon, iFct):
                subcel=[i, -j, ism, 1, MDeep]
                smcels.append( subcel )
                Ns[1] += 1

##  End of i, j loops. 

##  Two polar cells with the same size as the last row cells.
    j=nla2
    subcel=[0,  j, ism, 1, MDeep]
    smcels.append( subcel )
    Ns[1] += 1
    subcel=[0, -j, ism, 1, MDeep]
    smcels.append( subcel )
    Ns[1] += 1

##  All cells are done.
    print(  " *** Done all cells Ns =", Ns )
    NL = sum(Ns[:])
    print(  " *** Total cells Numbr =", NL )

##  Follow Qingxiang Liu's method to sort smcels before save it.
#   smcelsdf = pd.DataFrame(smcels, columns=['i','j','di','dj','kdp'])
#   smcelsdf.sort_values(by=['dj','j','i'], inplace=True)
#   smcels = np.array(smcelsdf)
## Sorting is not required for 1 level 2 polar cell grids.

## Cell array output format for each cell.
    fmtcel='%6d %5d %4d %3d %5d'

## Separate Arctic part out of the cells and work out boundary 
## cell numbers.
    if( Arctic ):
        jbdy = MFct*2
        smcArc= smcels[smcels[:,1]>=jArc]
        nbArc = smcArc[smcArc[:,1]<jArc+  jbdy].shape[0]
        nbGlo = smcArc[smcArc[:,1]<jArc+2*jbdy].shape[0] - \
                nbArc
        nArct = smcArc.shape[0]
        smcArcnp = np.array(smcArc)
        hdr = f'{nArct:8d} {nbArc:5d} {nbGlo:5d}'
        ArcFl = FileNm +'BArc.dat'
        print(' ... saving BArc.dat with header '+hdr )
        np.savetxt(ArcFl, smcArc, fmt=fmtcel, header=hdr, \
                   comments='')
## Separate Global part out of the cells by jArc value
        smcels = smcels[smcels[:,1]<jArc+2*jbdy]
        Ns[NLvel] = Ns[NLvel] - nArct + nbArc + nbGlo

## Save all or global part cells.
    smcelsnp = np.array(smcels)
    GloFl = FileNm +'Cels.dat'
    Ns[0] = sum(Ns[1:])
    hdr = ''.join( [f"{n:8d}" for n in Ns] ) 
    print(' ... saving Cels.dat with header '+hdr )
    np.savetxt(GloFl, smcelsnp, fmt=fmtcel, header=hdr, \
                   comments='')
    print( " smcellful finished." )

    return 0

## End of smcellful function.

if __name__ == '__main__':
    main()

##  End of smcellful.py program. 

