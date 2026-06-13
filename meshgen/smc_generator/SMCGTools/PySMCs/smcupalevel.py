"""
##  Program to update cell arrays up one level.
##
##  First created:        JGLi02Nov2021
##  Last modified:        JGLi05Feb2025
##
"""

import sys

def smcupalevel(cell_file, skiprows=0 ):
    """
    Read cells from cell_file (if given) or the default 'tempcels.dat'
    Assume no header to be skipped or skip first skiprows (>0) lines.
    Change the cell array up a level by doubling all 4 indexes.
    """

    import numpy as np

##  Use default cell file if not defined
    if( len(cell_file) < 2 ):
        cellfile = 'tempcels.dat'
    else:
        cellfile = cell_file

    print(" Read cells from ", cellfile)

##  Read cells with s by a procedure
    cels = np.genfromtxt(cellfile, skip_header=skiprows)
    cel  = np.array( cels ).astype(int)
    ncs  = cel.shape[0]
    print(" Total number of cells =", ncs)

##  Cell array output format for each cell.
    fmtcel='%6d %5d %4d %3d %5d'

##  Double all cell i,j,di,dj to up a level.
    for i in range(ncs):
        for j in range(4):
            cel[i,j] = cel[i,j]*2

##  Save converted cell array.
    Cell_New = cellfile+"_New"
    np.savetxt(Cell_New, cel, fmt=fmtcel, comments='')

    return (0)

##  End of smcupalevel conversion function.


def main():
    print(" Input argvs =", sys.argv[1:])
    infile=' '
    skprow=0
    nagv = len(sys.argv) 
    if( nagv > 1 ):
        if( len(sys.argv[1]) > 2 ): infile=sys.argv[1] 
    if( nagv > 2 ):
        if( int(sys.argv[2]) > 0 ): skprow=int(sys.argv[2])

    smcupalevel(infile, skiprows=skprow )

##  End of main() function.

if __name__ == '__main__':
    main()

##  End of smcupalevel.py program.

