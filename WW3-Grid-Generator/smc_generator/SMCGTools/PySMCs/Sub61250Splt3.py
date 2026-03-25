"""
##  Program to split the SMC61250 grid into 3 sub-grids.
##
##  First created:        JGLi08Feb2021 
##  Last modified:        JGLi05Feb2025 
##
"""

def main():

##  Import relevant modules and functions
    import numpy as np
    import pandas as pd

    from datetime import datetime
    from readcell import readcell   
    from readtext import readtext   

    print( " Program started at %s " % datetime.now().strftime('%F %H:%M:%S') )

##  Data and work directories. 
    Wrkdir='../'
    Tmpdir='../tmpfls/'

##  Read cell array from input file. 
    Cellfile = Wrkdir+'DatGMC/SMC61250Cels.dat'
    headrs, cel = readcell( [ Cellfile ] ) 
    nc = int( headrs[0].split()[0] )
    print ('Total cell number = %d' % nc )
    print ("First cell array is ", cel[0,:])
    print (" Last cell array is ", cel[nc-1,:])

##  Resort cell array cel before splitting by j row loop.
    smcelsdf = pd.DataFrame(cel, columns=['i','j','di','dj','kh'])
    smcelsdf.sort_values(by=['j','i'], inplace=True)
    cel = np.array(smcelsdf)
    print (" Cell array is resorted by j and i.")

##  Size-1 cell increments
#   nx=4096
#   ny=3072
#   dxlon=360.0/float(nx)
#   dylat=180.0/float(ny)
    dxlon=0.087890625
    dylat=0.058593750
    zrlon=0.0
    zrlat=0.0

##  Read dividing lines.
    headr, lines = readtext( Wrkdir+'Bathys/Subgrdline3.dat' ) 
    
##  American line:
    merc = int(lines[0,1])
    AmLatLon = lines[1:merc+1, :]
    print(merc, AmLatLon)

##  Africa-Europe line:
    mfic = int(lines[merc+1, 1])
    AfLatLon = lines[merc+2:, :]
    print(mfic, AfLatLon)

##  Australia-Asia line:
    maus = int(lines[merc+mfic+2, 1])
    AuLatLon = lines[merc+mfic+3:, :]
    print(maus, AuLatLon)

##  Work out separation i values and loop over all cells
    mer = 0
    mfc = 0
    mau = 0
    AmLat = AmLatLon[mer, 0]
    AfLat = AfLatLon[mfc, 0]
    AuLat = AuLatLon[mau, 0]
    Atlns = []
    Pacfc = []
    South = []
    SBndy = []
    ABndy = []
    PBndy = []
    BndBring= int(int( 66.0/dylat)/8)*8 
#   BndAtlan= int(int( -8.0/dylat)/8)*8 
#   BndPacif= int(int(-29.0/dylat)/8)*8 
    print("BndBring =", BndBring )
##  Boundary width below 60S in mergered zone
    LB=32

    for i in range(nc): 

##  Cell SW corner lat lon location
        icel=cel[i,0]
        jcel=cel[i,1]
        slon= zrlon + float(cel[i,0])*dxlon
        slat= zrlat + float(cel[i,1])*dylat
        if( slat > -60.0 ): LB=16

##  Cells above BndBring = 66 are grouped into Atlantic part.
        if( jcel >= BndBring ):
            Atlns.append( list(cel[i,:]) ) 

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
## Afric-Europe line stride 0-meridian so wrapping is done after interpolation.
                    AfLo1 = AfLatLon[mfc, 1] 
                    AfLo2 = AfLatLon[mfc+1, 1] 
                    print(" Updated AfLa1, AfLo1 at slat:", AfLa1, AfLo1, slat)
                    mfc += 1
            if( slat > AuLat ):
                if(mau+1 < maus):
                    AuLa1 = AuLatLon[mau, 0]
                    AuLat = AuLatLon[mau+1, 0]
                    AuLo1 = np.mod(AuLatLon[mau, 1] + 360.0, 360.0) 
                    AuLo2 = np.mod(AuLatLon[mau+1, 1] + 360.0, 360.0) 
                    print(" Updated AuLa1, AuLo1 at slat:", AuLa1, AuLo1, slat)
                    mau += 1
##  American line is inclined so AmLon has to be calculated row by row.             
            AmLon = AmLo1 + (AmLo2 - AmLo1)*(slat-AmLa1)/(AmLat-AmLa1)
            MAmLn = int(int(AmLon/dxlon)/8)*8 
##  Afric-European line is inclined so AfLon has to be calculated row by row.             
            AfLmn = AfLo1 + (AfLo2 - AfLo1)*(slat-AfLa1)/(AfLat-AfLa1)
##  Wrapping to [0, 360) range after interpolation.
            AfLon = np.mod(AfLmn + 360.0, 360.0)
            MAfLn = int(int(AfLon/dxlon)/8)*8 
##  Australia-Asia line is inclined so AuLon has to be calculated row by row.             
            AuLon = AuLo1 + (AuLo2 - AuLo1)*(slat-AuLa1)/(AuLat-AuLa1)
            MAuLn = int(int(AuLon/dxlon)/8)*8 

##  Pacf parts between MAuLn and MAmLn.
            if( MAuLn <= icel < MAmLn ):
                Pacfc.append( list(cel[i,:]) ) 
##  Soth grid boundary points within Pacf grid below 3N along AuLon:
                if( slat < 3.1 and icel < MAuLn+LB ):
                    South.append( list(cel[i,:]) ) 
                    SBndy.append( list(cel[i,:]) ) 
##  Soth grid boundary points within Pacf grid between 64S and 54S along AmLon:
                if( (-64.0 <= slat < -54.0) and (MAmLn-LB <= icel < MAmLn) ):
                    South.append( list(cel[i,:]) ) 
                    SBndy.append( list(cel[i,:]) ) 
##  Soth parts between MAfLn and MAuLn.
            if( (MAfLn > MAuLn and (MAfLn <= icel or icel < MAuLn)) or 
                (MAfLn < MAuLn and (MAfLn <= icel < MAuLn))         ): 
                South.append( list(cel[i,:]) ) 
##  Pacf grid boundary points within Soth grid below 3N along AuLon:
                if( slat < 3.0 and (MAuLn-LB <= icel < MAuLn) ):
                    Pacfc.append( list(cel[i,:]) ) 
                    PBndy.append( list(cel[i,:]) ) 
##  Pacf grid boundary points within Soth grid below 54S along AmLon:
                if( (-64.0 <= slat < -54.0) and (MAfLn <= icel < MAfLn+LB) ):
                    Pacfc.append( list(cel[i,:]) ) 
                    PBndy.append( list(cel[i,:]) ) 
##  Atln grid boundary points within Soth grid between 10S and 10N along AfLon:
##  Extended to 3 columns boundary layer as it is an oblique line.
                if( abs(slat) <= 10.0 and (MAfLn <= icel < MAfLn+LB+8) ):
                    Atlns.append( list(cel[i,:]) ) 
                    ABndy.append( list(cel[i,:]) ) 
##  Atln grid boundary points within Soth grid at Gibraltar Strait, size-8: 
                if( (35.0 < slat < 39.0) and (MAfLn <= icel < MAfLn+8) ):
                    Atlns.append( list(cel[i,:]) ) 
                    ABndy.append( list(cel[i,:]) ) 
##  Atln parts between MAmLn and MAfLn.
            if( (MAfLn >= MAmLn and (MAmLn <= icel < MAfLn)) or 
                (MAfLn <  MAmLn and (MAmLn <= icel or icel < MAfLn)) ): 
                Atlns.append( list(cel[i,:]) ) 
##  Soth grid boundary points within Atln grid between 10S and 10N along AfLon:
##  Extended to 3 columns boundary layer as it is an oblique line.
                if( abs(slat) <= 10.0 and (MAfLn-LB-8 <= icel < MAfLn) ):
                    South.append( list(cel[i,:]) ) 
                    SBndy.append( list(cel[i,:]) ) 
##  Soth grid boundary points within Atln grid at Gibraltar Strait, size-8: 
                if( (35.0 < slat < 39.0) and (MAfLn-8 <= icel < MAfLn) ):
                    South.append( list(cel[i,:]) ) 
                    SBndy.append( list(cel[i,:]) ) 

##  Atln grid boundary cells within 1 deg latitude along BndBring.
            if( (BndBring-32 <= jcel < BndBring) and
                     ( 188.0 <= slon < 194.0 ) ):
                Atlns.append( list(cel[i,:]) ) 
                if( jcel < BndBring - 16 ):
                    ABndy.append( list(cel[i,:]) ) 
                else:
                    PBndy.append( list(cel[i,:]) ) 

##  Convert cell lists and save into two cell files.
    fmtcel='%6d %5d %4d %3d %5d'

    Atcels = np.array(Atlns)
    np.savetxt(Tmpdir+"AtlnCels.dat", Atcels, fmt=fmtcel, comments='')

    Pacels = np.array(Pacfc)
    np.savetxt(Tmpdir+"PacfCels.dat", Pacels, fmt=fmtcel, comments='')

    Socels = np.array(South)
    np.savetxt(Tmpdir+"SothCels.dat", Socels, fmt=fmtcel, comments='')

    ABcels = np.array(ABndy)
    np.savetxt(Tmpdir+"AtlnBdys.dat", ABcels, fmt=fmtcel, comments='')

    PBcels = np.array(PBndy)
    np.savetxt(Tmpdir+"PacfBdys.dat", PBcels, fmt=fmtcel, comments='')

    SBcels = np.array(SBndy)
    np.savetxt(Tmpdir+"SothBdys.dat", SBcels, fmt=fmtcel, comments='')

    print( " Program finished at %s " % datetime.now().strftime('%F %H:%M:%S') )

##  End of main() function.

if __name__ == '__main__':
    main()

##  End of Sub61250splt3.py program. 

