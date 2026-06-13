"""
## Procedure to setup regular grid parameters for a SMC grid.
## Converted from IDL to Python.  JGLi26Feb2019
## First created:   25 Feb 2015   Jian-Guo Li
## Last modified:   26 Jun 2025   Jian-Guo Li
##
"""

def regulrinfo( Model, zdlonlat, NLvLonLat, FLon=0.0, FLat=-80.0, **kwargs ):
 
    import numpy as np

    print(' Generating regular domain info for '+Model )

##  SMC grid i=j=0 point zlon, zlat and size-1 cell dlon, dlat.
    zlon=float(zdlonlat[0])
    zlat=float(zdlonlat[1])
    dlon=float(zdlonlat[2])
    dlat=float(zdlonlat[3])
    print(' zlon zlat dlon dlat =', zlon, zlat, dlon, dlat )

##  SMC grid resolution levels and NLon, NLat in size-1 cell unit.
    NRLv = int(NLvLonLat[0])
    NLon = int(NLvLonLat[1])
    NLat = int(NLvLonLat[2])
    MFct = 2**(NRLv - 1)
    print (' NRLv MFct NLon NLat = ', NRLv, MFct, NLon, NLat )

##  Check whether global periodic condition applies.
    Global = False
    NGlobl = int(round(360.0/dlon))
    if( NLon == NGlobl ): 
        Global = True
        print(" Global grid periodic condition applied.")

##  Regular grid increments by MFct.
    DLonR= dlon*MFct
    DLatR= dlat*MFct

##  Use input FLon and FLat to adjust starting points. 
    JEqut= MFct*int(round( (zlat - FLat)/DLatR ))
    IShft= MFct*int(round( (zlon - FLon)/DLonR ))

##  Adjust FLon and FLat to be centre of a base resolution cell.
    FLonR= zlon - IShft*dlon + DLonR*0.5 
    FLatR= zlat - JEqut*dlat + DLatR*0.5

##  Work out number of regular grid column and row numbers.
    NCol = NLon//MFct
    NRow = NLat//MFct
    if( Global ):
        NR90 = int(round( (90.0 - FLatR)/DLatR + 0.5 )) 
        NRow = min([NR90, NRow])

##  Regular grid last column lon and last row lat.
    EnLon= FLonR+(NCol-1)*DLonR
    EnLat= FLatR+(NRow-1)*DLatR

    print (' IShft JEqut NCol NRow = ',  IShft, JEqut, NCol,  NRow )
    print (' FLonR FLatR DLon DLat = ',  FLonR, FLatR, DLonR, DLatR)
    print (' EndLon, EndLat = ',  EnLon, EnLat)

##  Save info into a file.
    flxy = open(Model+"Rgul.txt", 'w')
    flxy.writelines(" Regular domain parameters for "+Model+" grid \n")
    flxy.writelines(" NC, NR= %d, %d \n" % (NCol,  NRow) )
    flxy.writelines(" DX, DY= %f, %f \n" % (DLonR, DLatR) )
    flxy.writelines(" X1, Y1= %f, %f \n" % (FLonR, FLatR) )
    flxy.writelines(" XN, YN= %f, %f \n" % (EnLon, EnLat) )
    flxy.writelines(" iShft, jEqut= %d, %d \n" % (IShft, JEqut) )
    flxy.writelines(" NRLvl, MRFct= %d, %d \n" % (NRLv,  MFct) )
    flxy.writelines(" End of regular information. \n")
    flxy.close()

    print(" End of regular information for "+Model )

    return  NRLv 

##  End of function regulrinfo.

 
def main():
    """  Generate regular grid parameters for SMC251040 global grid. """
    Model='SMC61250'
    Wrkdir='./'
    zrdlonlat=[ 0.0, 0.0, 0.087890625, 0.058593750 ]
    NLvLonLat=[ 4, 4096, 3072 ]
    NRLv = regulrinfo( Model, zrdlonlat, NLvLonLat, FLat=-79.8 ) 

##  End of main program.

if __name__ == '__main__':
    main()

##  End of program regulrinfo.py.

