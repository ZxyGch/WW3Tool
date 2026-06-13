"""
## Program to define regular grid parameters for SMC grid.
## SMC61250 grid is used as an example by default.
##
## Converted from IDL to Python.  JGLi26Feb2019
## First created:   25 Feb 2015   Jian-Guo Li
## Last modified:   26 Jun 2025   Jian-Guo Li
##
"""
 
def main():
    """  Generate regular grid parameters for a SMC grid. """

    import sys
    import numpy as np
    from regulrinfo import regulrinfo

    print(" Input argvs =", sys.argv[1:])
    Gridfile='GridInfo61250.txt'
    FLRegulr= -79.8
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 2 ): Gridfile=sys.argv[1] 
    if( len(sys.argv) > 2 ):
        if( len(sys.argv[2]) > 2 ): FLRegulr=float(sys.argv[2]) 
    print(" GridInfo file and first regular grid latitude = \n",
            Gridfile, FLRegulr)

##  Define sub-grids and parameters. 
    Wrkdir='./'

##  Read SMC61250 grid info from Grindifo.dat 
    with open( Gridfile, 'r' ) as flhdl:
## First line contains grid name and number of resolution levels.
        nxlne = flhdl.readline().split()
        Model = nxlne[0]
        Level = int(nxlne[1])
        print(" Input model name and number of levl= ", Model, Level)
## Second line contains zlon zlat dlon dlat of size-1 cell parameters.
        nxlne = flhdl.readline().split()
        zdlnlt = np.array(nxlne, dtype=float)
        print(" Input grid zlon zlat dlon dlat = \n", zdlnlt) 

    NRLv= Level
    NLon= int( round( 360.0/zdlnlt[2] ) )
    NLat= int( round( 180.0/zdlnlt[3] ) )
    NLvLnLt=[ NRLv, NLon, NLat ]

    print("\n Model NRLv NLon NLat = ", Model, NRLv, NLon, NLat ) 

    NRLout = regulrinfo( Model, zdlnlt, NLvLnLt, FLat=FLRegulr )

##  End of main program.

if __name__ == '__main__':
    main()

##  End of program SMCGridRInfo.py.

