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
## Modified for Sub36125 sub grids.    JGLi30Sep2020
## Adapted for 3 sub-grids split from SMC36125.    JGLi12Jan2021
## Adapted for 3 sub-grids split from SMC61250.    JGLi08Oct2021
##
"""

def main(): 
##  Import relevant modules and functions

    import numpy as np

    from readcell import readcell   
    from readtext import readtext   

##  Read global and Arctic part cells. 
    DatGMC='../DatSub/'
    Obstfile="../Bathys/Glob6kmObstr.dat"

#;; Read in land percentage data from Glob6kmObstr.dat. JGLi19Sep2014
#    4096    3072    0.043950  -89.970703   8.789062E-02   5.859375E-02
    print (" Read Glob6kmObstr.dat ..." )
    hdr, obstrin = readtext(Obstfile, skiprows=[0,1])
    NCobs = int( hdr[0] )
    NRobs = int( hdr[1] )
    FLonb = float( hdr[2] )
    FLatb = float( hdr[3] )
    DLonb = float( hdr[4] )
    DLatb = float( hdr[5] )
    print ( NCobs, NRobs, FLonb, FLatb, DLonb, DLatb)

##  As formated input was read as a table of 2-D arrays 
##  and blank spaces in the table are changed into none
##  the read array need to be reshaped to original shape
##  and trailing nones are removed.
    nrocos = obstrin.shape
    print (' Readin obstrin shape =', obstrin.shape )
    ncolin = nrocos[0]*nrocos[1]//NRobs
    Fobsin = obstrin.reshape((NRobs,ncolin))[:,:NCobs]
    print (' Coverted Obstr shape =', Fobsin.shape )

#;; Work out Equator index for Global 6km obstruction data
    EqtDlt= 0.0 - FLatb + 0.5*DLatb
    NEqutr= int( round( EqtDlt/DLatb + 0.001 ) )
    print (' G6km Equator index NEqutr =', NEqutr)
##  Cell origin i=0 is assumed the same as obstration data  
##  x-origin from zero meridian.

#;; SMC61250 sub grid share the same multi-resolution levels and factor
    MRL=4
    MFct=2**(MRL-1)
    print (" Multi-Resol MRL, MFct=", MRL, MFct) 

#;; Test mode function %
    print ('  6 % 10 =',  6 % 10)
    print (' 16 % 10 =', 16 % 10)

#;; Test max and min functions
    print (' np.min([0.5,1.0])=', np.min([0.5,1.0]))
    print (' np.max([0.5,1.0])=', np.max([0.5,1.0]))

    for grid in ['Soth', 'Pacf', 'Atln']:
        Cel_file = DatGMC+grid + '61250Cels.dat'
        headrs, Cel = readcell( [Cel_file] ) 
        nc = int( headrs[0].split()[0] )
        print ( Cel_file+' total cel number = %d' % nc )
 
#;; Declare sub-grid obstruction array, excluding Arctic part.
#;; Arctic part is set no sub-grid obstruction.
        Kobstr=np.zeros(nc, dtype=int)

#;; Create sub-grid obstruction ratio for all cells, excluding Arctic part 
        for n in range(nc):
##  All cell indexes have to be halved as they are in unit of 3 km
            i=Cel[n,0]
            j=Cel[n,1] + NEqutr
            if( j >= NRobs or j < 0 ): print ('n, j=', n, j)
            mi=Cel[n,2]
            nj=Cel[n,3]

#;; Loop over merged cells if any
            avrobs = 0.0
            for ii in range(i, i+mi):
                for jj in range(j, j+nj):
                    avrobs += Fobsin[jj,ii] 

#;; Maximum 90% blocking is enforced to avoid full blocking.
            Kobstr[n] = np.min( [90, int(round( 100.0*avrobs/float(nj*mi)))] )

#;; WW3 read in obstruction rather transparency so 1.0 mean complete blocking!
#;; The value will be from 0.0 for transparent sea point to 1.0 for full land 
#;; blocking with a scaling factor 1.0 at the input line.   JGLi  26 Nov 2009
#;; The obstruction will be equal in both x and y direction.
        Obstrout = DatGMC+grid+"61250bstr.dat"
        hdrline = "{:8d} {:5d}".format(nc, 1)
        np.savetxt(Obstrout, Kobstr, fmt='%4d', header=hdrline, comments='')

        print(" Subgrid obstruction saved in \n"+Obstrout) 

##  End of sub-grid loop

    print (" All done! " )

##  End of Sub61250bstr3.py main program ##


if __name__ == '__main__':
    main()

