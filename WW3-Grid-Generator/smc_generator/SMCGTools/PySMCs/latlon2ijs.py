"""
##  Converting lat-lon pairs into SMC grid i, j indexes and add an awk script 
##  output for selected area by first two lines.
##
##  First created:        JGLi01Mar2022 
##  Last modified:        JGLi26Jun2025 
##
"""

def latlon2ijs( latlons, zlldll, kround=1 ):
    """
    Loop over lat-lon pairs from latlons (one pair per row) and convert
    each lat-lon pair into SMC grid i, j indexes of nearest multiple of 
    kround, using given zlon zlat dlon dlat values in zlldll[4] list.
    Convert longitude into [0., 360.) range if xlon < 0.0. 
    Save the xlon, ylat, i, j values to New_latlon_file. 
    """

    import numpy as np

##  Workout number of lat-lon paires.
    npairs  = latlons.shape[0]
    print(" Total number of lat-lon pairs =", npairs)

##  SMC grid zlon, zlat, dlon, dlat values.
    x0lon=zlldll[0]; y0lat=zlldll[1]
    dxlon=zlldll[2]; dylat=zlldll[3]
    print(" SMC grid x0lon, y0lat, dxlon, dylat =", 
                     x0lon, y0lat, dxlon, dylat )

##  Round i,j to the nearest kround-multiples for cell selection.
    if(kround < 1): kround=1
    print(" i, j indexes will be rounded to nearest multiple of k =", kround )

    ijpairs=[]
##  Loop over all lat-lon paires and convert them into i, j
    for n in range(npairs):
        ylat = latlons[n,0] 
        xlon = latlons[n,1]
        if(xlon < x0lon): xlon = xlon+360.0
        i = int( round( (xlon - x0lon)/(dxlon*kround) ) )*kround
        j = int( round( (ylat - y0lat)/(dylat*kround) ) )*kround
        ijpairs.append(f'{xlon:9.3f} {ylat:8.3f} {i:6d} {j:6d}')

#   print( ijpairs )

    return ijpairs

##  End of latlon2ijs conversion function.


def main():
    import sys
    import numpy as np

    print(" Input argvs =", sys.argv[1:])
    ltlnfile='Slatlons.dat'
    gridfile='Gridinfo.dat'
    kround=1
    skprow=0
    nagv = len(sys.argv) 
    if( nagv > 1 ):
        if( len(sys.argv[1]) > 2 ): ltlnfile=sys.argv[1] 
    if( nagv > 2 ):
        if( len(sys.argv[2]) > 0 ): gridfile=sys.argv[2]
    if( nagv > 3 ):
        if( int(sys.argv[3]) > 0 ): kround=int(sys.argv[3])
    if( nagv > 4 ):
        if( int(sys.argv[4]) > 0 ): skprow=int(sys.argv[4])

    print(" Read grid info from ", gridfile)

##  Read grid information from gridfile.
    with open( gridfile, 'r' ) as flhdl:
## First line contains grid name and number of resolution levels.
        nxlne = flhdl.readline()
## Second line contains zlon zlat dlon dlat of size-1 cell parameters.
        nxlne = flhdl.readline().split()
        zdlnlt = np.array(nxlne, dtype=float)
        print(" Input grid zlon zlat dlon dlat = \n", zdlnlt) 

##  Read lat-lon pairs from lat-lon_file (one pair per line). 
    print(" Read lat-lon pairs from ", ltlnfile)
    latlons = np.genfromtxt(ltlnfile, dtype=float, skip_header=skprow)
    print( latlons )

##  Call conversion program.
    ijpairs = latlon2ijs( latlons, zdlnlt, kround=kround )

##  Save converted i, j pairs along with xlon, ylat. 
    ltln_ijs = ltlnfile+"_ijs"
    with open(ltln_ijs, 'w') as fhdl:
#       fhdl.write("\n".join(ijpairs))
        for llij in ijpairs:
            fhdl.write(llij+"\n")
            print(llij)
    print(" xlon ylat and converted i j's are saved in ", ltln_ijs )

##  Write out an awk script for selecting cells in the area specified by the
##  first two lines or the SW and NE corner lat-lon pairs.
    with open('awktemp', 'w') as fawk:
        ijsw=ijpairs[0].split()
        ijne=ijpairs[1].split()
        fawk.write("## awk script to select cells for area specified by"+"\n" +
                   "## SW corner: "+ijpairs[0]+"\n" +
                   "## NE corner: "+ijpairs[1]+"\n" +
                   "## Usage:  awk -f awktemp  Cell_file > tempcels.dat"+"\n\n")

        fawk.write(" { if (  ((( $1 >= "+ijsw[2]+" && $1 < "+ijne[2]+" ) && "+ 
                              "( $2 >= "+ijsw[3]+" && $2 < "+ijne[3]+" ))) ) print $0 }"+"\n\n")
        
    print(" Cells in area of the first two lines could be selected with \n"+
          "   awk -f awktemp Cell_file > tempcels.dat "+"\n" )

##  End of main() function.

if __name__ == '__main__':
    main()

##  End of latlon2ijs.py program. 

