"""
##  Program to draw a selection of SMC grid cells as rectangular boxes. 
##  Water depths are printed at cell centres for wet/dry checking.
##
##  First created:        JGLi11Nov2014
##  Last modified:        JGLi05Feb2025
##
##  Converted into Python.        JGLi02Nov2020
##
"""

import sys

def smcviewdep(cell_file, levels=5, nxwrap=0, skprow=0 ):
    """
    Read cells from cell_file (if given) or the default 'tempcell.dat'
    Assume no header to be skipped or skip first skprow (>0) lines.
    Draw the cells as rectangular cells within its ranges.
    Wrap around if nxwrap > 0 is provided, usually NX for global grid.
    """

    import numpy as np
    import matplotlib.pyplot as plt
    from rgbcolor import rgbcolor
    from scale_depth import scale_depth

    PySMCs='./'

##  Use default cell file if not defined
    if( len(cell_file) < 2 ):
        cellfile = 'tempcels.dat'
    else:
        cellfile = cell_file

    print(" Read cells from ", cellfile)

##  Read cells with s by a procedure
    cels = np.genfromtxt(cellfile, skip_header=skprow)
    cel  = np.array( cels ).astype(int)
    ncs  = cel.shape[0]
    print(" Total number of cells =", ncs)

##  Wrap cel[:,0] values if nxwrap > 0 
    if( nxwrap > 0 ):
        cel[:,0] = np.where(cel[:,0]>nxwrap/2, cel[:,0]-nxwrap, cel[:,0])

##  Default base cell size 16 or level 5.
    mb=2**(levels -1)

##  Range of selected cells
    ixmin=min(cel[:,0])-1
    ixmax=max(cel[:,0]+cel[:,2])+1
    jymin=min(cel[:,1])-1
    jymax=max(cel[:,1]+cel[:,3])+1
    print( ' Cel i, j range =', ixmin, ixmax, jymin, jymax )
    figx=(ixmax-ixmin)/4 
    figy=(jymax-jymin)/4 
    print( 'Figure size =',figx, figy)

##  Use color to show depth
    colrfile = PySMCs+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )
##  Use only first 131 colors in colrs(0:255). 
    depth, factr, cstar, marks, ncstr, nclrm = scale_depth(nclrm=136)
    ndeps = np.zeros( (ncs), dtype=int )
    ndep0 = ncstr + np.rint( (cstar-np.log10(11))*factr ).astype(int)

    fig, ax=plt.subplots(figsize=[figx,figy])
    fig.subplots_adjust(left=0.01,right=1.00,bottom=0.01,top=1.00)
#   ax.set_xlim(ixmin,ixmax) 
#   ax.set_ylim(jymin,jymax)
    ax.set_xlim(left=ixmin, right=ixmax)
    ax.set_ylim(bottom=jymin, top=jymax)
    ax.set_aspect('equal')
#   ax.set_autoscale_on(False)
    ax.set_axis_off()

    for i in range(ncs):
        xc=[cel[i,0],cel[i,0]+cel[i,2],cel[i,0]+cel[i,2],cel[i,0],cel[i,0]]
        yc=[cel[i,1],cel[i,1],cel[i,3]+cel[i,1],cel[i,3]+cel[i,1],cel[i,1]]
        if( cel[i,4] > -11 ): 
            ndeps[i] = ncstr + np.rint( (cstar-np.log10(cel[i,4]+11))*factr ).astype(int)
        if( ndeps[i] >= ndep0 ):
            ax.plot(xc, yc, linestyle='-', linewidth=1.0, color='k')
            plt.text( (xc[0]+xc[2])*0.5, yc[0]+0.3*cel[i,3], f'{cel[i,4]:d}', 
                horizontalalignment='center', fontsize=9, color='r' )
        else:
            ax.plot(xc, yc, linestyle='-', linewidth=1.0, color=colrs(ndeps[i]))
            plt.text( (xc[0]+xc[2])*0.5, (yc[0]+yc[2])*0.5, '.', 
                horizontalalignment='center', fontsize=11, color='r' )
            plt.text( (xc[0]+xc[2])*0.5, yc[0]+0.3*cel[i,3], f'{cel[i,4]:d}', 
                horizontalalignment='center', fontsize=9, color='b' )

##  Readjust axis range in case not exactly as specified.
    plt.subplots_adjust(left=0.01,bottom=0.01,right=0.99,top=0.99,
                    wspace=0, hspace=0)

##  Put i, j index at central cross 
    istar = int(round(ixmin/8))*8
    jcntr = int((jymin + jymax)/8)*4
    for i in range(istar, ixmax, 8): 
        ii = i
        if( nxwrap > 0 and i < 0): ii = i + nxwrap
        plt.text( i, jcntr, str(ii), rotation=90, 
            horizontalalignment='right', fontsize=11, color='r' )

    jstar = int(round(jymin/8))*8
    icntr = int((ixmin + ixmax)/8)*4
    for j in range(jstar, jymax, 8):
        plt.text( icntr, j+0.2, str(j), 
            horizontalalignment='right', fontsize=11, color='r' )

    plt.savefig('./tmpsmcgrd.png', dpi=None,facecolor='w',edgecolor='w',
                 orientation='portrait')
                 
    plt.show()

##  End of smcviewdep function.


def main():
    print(sys.argv[1:])
    infile=' '
    levels=5
    nxwrap=0
    skprow=0
    nagv = len(sys.argv) 
    if( nagv > 1 ):
        if( len(sys.argv[1]) > 2 ): infile=sys.argv[1] 
    if( nagv > 2 ):
        if( int(sys.argv[2]) > 0 ): levels=int(sys.argv[2])
    if( nagv > 3 ):
        if( int(sys.argv[3]) > 0 ): nxwrap=int(sys.argv[3])
    if( nagv > 4 ):
        if( int(sys.argv[4]) > 0 ): skprow=int(sys.argv[4])

    smcviewdep(infile, levels=levels, nxwrap=nxwrap, skprow=skprow )

##  End of main() function.

if __name__ == '__main__':
    main()

##  End of smcviewdep.py program.

