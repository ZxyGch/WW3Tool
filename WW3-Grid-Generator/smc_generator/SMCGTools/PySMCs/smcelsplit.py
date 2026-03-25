"""
##  Function smcelsplit for splitting a SMC grid into sub-grids.
##
##  First created:        JGLi08Oct2021
##  Last modified:        JGLi05Feb2025
##
"""

def smcelsplit(SMCeFile, zdlonlat, SpltFile, WrkDir='./', NLvl=5, **kwargs): 
    """ Split a SMC grid into sub-grids with given splitting lines. """

##  Import relevant modules and functions
    import numpy as np
    import pandas as pd

    from datetime import datetime
    from readcell import readcell   
    from readtext import readtext   

    print( " smcelsplt started at %s " % datetime.now().strftime('%F %H:%M:%S') )

##  New cell array saved directory. 
    print (" Split cell arrays will be saved in ", WrkDir)

##  Read cell array from input file. 
    headrs, cel = readcell( [ SMCeFile ] ) 
    nc = int( headrs[0].split()[0] )
    print ('Total cell number = %d' % nc )
    print ("First cell array is ", cel[0,:])
    print (" Last cell array is ", cel[nc-1,:])

##  Resort cell array cel before splitting by j row loop.
    smcelsdf = pd.DataFrame(cel, columns=['i','j','di','dj','kh'])
    smcelsdf.sort_values(by=['j','i'], inplace=True)
    cel = np.array(smcelsdf)
    print (" Cell array is resorted by j and i.")

##  Size-1 cell increments and i=j=0 point.
    x0lon=float(zdlonlat[0])
    y0lat=float(zdlonlat[1])
    dxlon=float(zdlonlat[2])
    dylat=float(zdlonlat[3])
    print(" Input grid x0lon, y0lat, dxlon, dylat = \n", 
            x0lon, y0lat, dxlon, dylat )

##  MFct for base resolution cell size.
    MFct = 2**(NLvl - 1)
    print(" No. of levels and MFct are", NLvl, MFct)

##  Read dividing lines.
    headr, lines = readtext( SpltFile ) 
    
##  American line:
    merc = int(lines[0,1])
    AmLatLon = lines[1:merc+1, :]
    print(merc, AmLatLon)

##  Africa-Europe line:
    mfic = int(lines[merc+1, 1])
    AfLatLon = lines[merc+2:, :]
    print(mfic, AfLatLon)

##  Work out separation i values and loop over all cells
    mer = 0
    mfc = 0
    mau = 0
    AmLat = AmLatLon[mer, 0]
    AmLon = AmLatLon[mer, 1] 
    MAmLn = int(int(AmLon/dxlon)/MFct)*MFct 
    AfLat = AfLatLon[mfc, 0]
    AfLon = AfLatLon[mfc, 1]
    MAfLn = int(int(AfLon/dxlon)/MFct)*MFct 

    Atlns = []
    Pacfc = []
    South = []
    ABndy = []
    PBndy = []
    SBndy = []

##  Above Bring Strait are all in Atln sub-grid.
    BndBring= int(int( 66.0/dylat)/MFct)*MFct 
    print("BndBring =", BndBring )

##  Below 24.0S are all in South sub-grid.
    BndAtlan= int(int( -24.0/dylat)/MFct)*MFct 
    print("BndAtlan =", BndAtlan )

##  Africa line at 23.0E to define South grid above BandAtlan.
    BndAfric= int(int( 23.0/dxlon)/MFct)*MFct 
    print("BndAfric =", BndAfric )

##  Boundary widths in base resolution cell sizes.
    LB4= 4*MFct
    LB3= 3*MFct
    LB2= 2*MFct

    for i in range(nc): 

##  Cell SW corner lat lon location
        icel=cel[i,0]
        jcel=cel[i,1]
        slon= x0lon + float(cel[i,0])*dxlon
        slat= y0lat + float(cel[i,1])*dylat

##  Cells above BndBring = 66 are grouped into Atln grid.
        if( jcel >= BndBring ):
            Atlns.append( list(cel[i,:]) ) 

##  Cels below BndAtlan are grouped into South sub-grid.
        elif( jcel < BndAtlan ):
            South.append( list(cel[i,:]) ) 

##  Other cells are separated by three lines into three parts.
        else:

##  Adjust separation i values if necessary.
            if( slat > AmLat ):
                if(mer+1 < merc):
                    AmLa1 = AmLatLon[mer, 0]
                    AmLat = AmLatLon[mer+1, 0]
                    AmLo1 = np.mod(AmLatLon[mer, 1] + 360.0, 360.0) 
                    AmLo2 = np.mod(AmLatLon[mer+1, 1] + 360.0, 360.0) 
                    print(" Updated AmLa1, AmLo1 at slat:", AmLa1, AmLo1, slat)
                    mer += 1
            if( slat > AfLat ):
                if(mfc+1 < mfic):
                    AfLa1 = AfLatLon[mfc, 0]
                    AfLat = AfLatLon[mfc+1, 0]
                    AfLo1 = AfLatLon[mfc, 1] 
                    AfLo2 = AfLatLon[mfc+1, 1] 
                    print(" Updated AfLa1, AfLo1 at slat:", AfLa1, AfLo1, slat)
                    mfc += 1

##  American line is inclined so AmLon has to be calculated row by row.             
            AmLon = AmLo1 + (AmLo2 - AmLo1)*(slat-AmLa1)/(AmLat-AmLa1)
            MAmLn = int(int(AmLon/dxlon)/MFct)*MFct 
##  Afric-European line is inclined so AfLon has to be calculated row by row.             
            AfLmn = AfLo1 + (AfLo2 - AfLo1)*(slat-AfLa1)/(AfLat-AfLa1)
##  Afric-European line strides 0-meridian so needs wrapping to [0, 360) range. 
            AfLon = np.mod(AfLmn + 360.0, 360.0)
            MAfLn = int(int(AfLon/dxlon)/MFct)*MFct

##  Atln part between MAmLn and MAfLn.
            if( (MAfLn >= MAmLn and (MAmLn <= icel < MAfLn)) or
                (MAfLn <  MAmLn and (MAmLn <= icel or icel < MAfLn)) ):
                Atlns.append( list(cel[i,:]) )

##  Soth grid boundary points within Atln grid between 10S and 10N along AfLon:
                if( abs(slat) <= 10.0 and (MAfLn-LB3 <= icel < MAfLn) ):
                    South.append( list(cel[i,:]) )
                    SBndy.append( list(cel[i,:]) )

##  Soth grid between MAfLn and BndAfric.
            elif( slat < 9.0 and (MAfLn <= icel or icel < BndAfric) ):
                South.append( list(cel[i,:]) )

##  Atln boundary points within Soth grid near MAfLn. 
                if( MAfLn <= icel < MAfLn + LB4 ):
                    Atlns.append( list(cel[i,:]) )
                    ABndy.append( list(cel[i,:]) ) 

##  Othwise all belong to Pacf sub-grid and Soth boundary cells.
##  The horizontal boundary line is LB3 or 3-base-resolution cells wide.
            else:
                Pacfc.append( list(cel[i,:]) ) 
                if( jcel < BndAtlan + LB3 ):
                    PBndy.append( list(cel[i,:]) ) 
                    South.append( list(cel[i,:]) )

##  Soth grid and boundary cells within Pacf grid along BndAtlan.
                if( BndAtlan + LB3 <= jcel < BndAtlan + 2*LB2 ):
                    South.append( list(cel[i,:]) )
                    SBndy.append( list(cel[i,:]) )

##  Atln grid boundary cells within 1 deg latitude along BndBring.
            if( (BndBring-2*LB2 <= jcel < BndBring) and
                        ( 187.0 <= slon < 195.0 ) ):
                Atlns.append( list(cel[i,:]) ) 
                if( jcel < BndBring - LB2 ):
                    ABndy.append( list(cel[i,:]) ) 
                else:
                    PBndy.append( list(cel[i,:]) ) 

##  Convert cell lists and save into two cell files.
    fmtcel='%6d %5d %4d %3d %5d'

    Atcels = np.array(Atlns)
    print(" Saving Atcels cells:", Atcels.shape )
    np.savetxt(WrkDir+"AtnCels.dat", Atcels, fmt=fmtcel, comments='')

    Pacels = np.array(Pacfc)
    print(" Saving Pacels cells:", Pacels.shape )
    np.savetxt(WrkDir+"PcfCels.dat", Pacels, fmt=fmtcel, comments='')

    Shcels = np.array(South)
    print(" Saving Shcels cells:", Shcels.shape )
    np.savetxt(WrkDir+"SthCels.dat", Shcels, fmt=fmtcel, comments='')

    ABcels = np.array(ABndy)
    print(" Saving ABcels cells:", ABcels.shape )
    np.savetxt(WrkDir+"AtnBdys.dat", ABcels, fmt=fmtcel, comments='')

    PBcels = np.array(PBndy)
    print(" Saving PBcels cells:", PBcels.shape )
    np.savetxt(WrkDir+"PcfBdys.dat", PBcels, fmt=fmtcel, comments='')

    SBcels = np.array(SBndy)
    print(" Saving SBcels cells:", SBcels.shape )
    np.savetxt(WrkDir+"SthBdys.dat", SBcels, fmt=fmtcel, comments='')

    print( " smcelsplt finished at %s " % datetime.now().strftime('%F %H:%M:%S') )

    return 0

## End of smcelsplt function ##


def main():
    import sys
    import numpy as np

    print(" Input argvs =", sys.argv[1:])
    SMCeFile='../DatGMC/SMC61250Cels.dat' 
    GridInfo='../DatGMC/Gridinfo6km.dat'
    SpltFile='../Bathys/Subgrdline2.dat'
    WrkDir='../ztmpfls/'
    NLvl=4

    nagv = len(sys.argv) 
    if( nagv > 1 and len(sys.argv[1]) > 2 ): SMCeFile=sys.argv[1] 
    if( nagv > 2 and len(sys.argv[2]) > 2 ): SpltFile=sys.argv[2]
    if( nagv > 3 and len(sys.argv[3]) > 2 ): GridInfo=sys.argv[3]
    if( nagv > 4 and len(sys.argv[4]) > 2 ): WrkDir  =sys.argv[4]
    if( nagv > 5 and int(sys.argv[5]) > 0 ): NLvl=int(sys.argv[5])

    print(" Input cells file: ", SMCeFile)
    print(" Input split file: ", SpltFile)
    print(" Working file dir: ", WrkDir  )

    print(" Read grid info from ", GridInfo)

##  Read grid info from file (or define it here).
    zdlonlat = np.genfromtxt(GridInfo, dtype=float, skip_header=1)
#   dxlon=0.035156250
#   dylat=0.0250
#   x0lon = 0.0
#   y0lat = 0.0
#   zdlonlat =[ x0lon, y0lat, dxlon, dylat ]
    print(" Input grid zlon zlat dlon dlat = \n", zdlonlat)

##  Call smcelsplit to split into sub-grid cells.
    print(" Calling smcelsplit to split cells ... ")
    status = smcelsplit( SMCeFile, zdlonlat, SpltFile, WrkDir=WrkDir, NLvl=NLvl ) 

##  End of main function 

if __name__ == '__main__':
    main()

##  End of program smcelsplit.py. 

