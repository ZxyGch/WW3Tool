"""
#; WAVE Version 8.00 (Linux i386)
#; Date: Fri Sep 16 09:55:18 2005
#; To plot NAEbathy.pp as a contour gif file
#; First created:   16 Sep 2005   Jian-Guo Li
#; To smooth out land/sea for the final bathymetry
#; Prepare mask, depth and trans files for GSMC model. 
#; Use multi-resolution cell to modify base grid depth.
#; Last modified:     8 Jan 2013   Jian-Guo Li
#; SMC6125 grid with refined UK waters.  JGLi28Feb2013
#; SMC36125 grid with refined 3km UK waters.  JGLi28Feb2014
#; SMC24816 grid with refined 2km UK waters.  JGLi05Sep2014
#; SMC36125 grid with 3km European waters.    JGLi19Sep2014
#; Generate sub-grid obstruction for SMC36125 grid.  JGLi14Oct2014
#; Updated to used mylib/global25km to set up grid.  JGLi27Feb2015
#; Maximum obstruction ratio 90% for SMC36125 gird.  JGLi19May2016
#; Adapted for CMA SMC6125 grid obstruction ratios.  JGLi31Jul2018
#; Adapted for CMA SMC61250 grid obstruction ratios.  JGLi18Oct2018
## Converted from IDL to Python.    JGLi26Feb2019
## Modified for updated SMC61250 grid.  JGLi10May2021
## Modified for SMCGTools package.      JGLi06Oct2021
## Adapted to use Bathy088_059deg.nc obstruction ratio.  JGLi28Apr2023
##
"""

def main(): 
##  Import relevant modules and functions

    import numpy   as np
    import netCDF4 as ncd4

    from readcell import readcell   
    from readtext import readtext   

##  Read global and Arctic part cells. 
    Wrkdir='../tmpfls/'
    Cel_file = '../DatGMC/SMC61250Cels.dat'
    Arc_file = '../DatGMC/SMC61250BArc.dat'

    headrs, Cel = readcell( [Cel_file, Arc_file] ) 
    ng = int( headrs[0].split()[0] )
    na = int( headrs[1].split()[0] )
    nb = int( headrs[1].split()[1] )
    nga = ng + na
    print (' Merged total cel number = %d' % nga )
    jmxglb = Cel[ng-1, 1]
    print (' Maximum j row = %d' % jmxglb )
    jmin = np.min(Cel[:,1])
    dlat1 = 0.025
    ymin = jmin*dlat1
    print(' Minimum j row and ymin =', jmin, ymin )
  
#;; Multi-resolution levels and factor
    MRLv=4
    MFct=2**(MRLv-1)
    print (" Multi-Resol Level, MFct=", MRLv, MFct) 

#;; Read in land percentage data from Glob6kmObstr.dat. JGLi19Sep2014
#    4096    3072    0.043950  -89.970703   8.789062E-02   5.859375E-02
    bathyf = "../Bathys/Bathy088_059deg.nc"

##  Open and read obstruction ratio in bathymetry file.
    datas = ncd4.Dataset(bathyf)

    print(datas)            ## Print information about the dataset.

    NCobs = datas.dimensions['lon'].size
    NRobs = datas.dimensions['lat'].size
    DLonb = 360.0 / float(NCobs)
    DLatb = 180.0 / float(NRobs)

    xlon = datas.variables['lon'][:]
    ylat = datas.variables['lat'][:]

    FLonb = xlon[0]
    FLatb = ylat[0]
    print (" NCobs, NRobs, FLonb, FLatb, DLonb, DLatb = \n", 
             NCobs, NRobs, FLonb, FLatb, DLonb, DLatb )

    Fobsin = datas.variables['obstruction'][:,:]
    print (' Raw Obstr shape =', Fobsin.shape )

    datas.close()

#;; Declare global part cell obstruction array, excluding Arctic part.
#;; Arctic part is set no sub-grid obstruction.
    Kobstr=np.zeros(ng, dtype=int)

#;; Work out iShft and jEqut index for Global 6 km obstruction data
    EqtDlt= 0.0 - FLatb + 0.5*DLatb
    jEqut = int( round( EqtDlt/DLatb ) )
    ShtDlt= 0.0 - FLonb + 0.5*DLonb
    iShft = int( round( ShtDlt/DLonb ) )
    print (' Global 6 km iShft and jEqut =', iShft, jEqut )

#;; Create sub-grid obstruction ratio for all cells, excluding Arctic part 
    print (' Generating obstruction ratios for ng =', ng )

    for n in range(ng):
        i=Cel[n,0] + iShft
        j=Cel[n,1] + jEqut
        if( i >= NCobs ): i = i - NCobs 
        if( j >= NRobs or j < 0 ): print ('n, j=', n, j)
        mi=Cel[n,2]
        nj=Cel[n,3]

#;; Loop over merged cells if any
        avrobs = 0.0
        for ii in range(i, i+mi):
            if( ii >= NCobs ): ii = ii - NCobs 
            avrobs += np.sum( Fobsin[j:j+nj,ii] ) 

#;; Maximum 90% blocking is enforced to avoid full blocking.
        Kobstr[n] = np.min( [90, int(round( 100.0*avrobs/float(nj*mi)))] )

#;; WW3 read in obstruction rather transparency so 1.0 mean complete blocking!
#;; The value will be from 0.0 for transparent sea point to 1.0 for full land 
#;; blocking with a scaling factor 1.0 at the input line.   JGLi  26 Nov 2009
#;; The obstruction will be equal in both x and y direction.
    Obstrout = Wrkdir+"SMC61250Obst.dat"
    hdrline = "{:8d} {:5d}".format(ng, 1)
    np.savetxt(Obstrout, Kobstr, fmt='%4d', header=hdrline, comments='')

    print(" Subgrid obstruction saved in \n"+Obstrout) 

    print (" All done! " )

##  End of SMC61250Obstr.py main function.

if __name__ == '__main__':
    main()


