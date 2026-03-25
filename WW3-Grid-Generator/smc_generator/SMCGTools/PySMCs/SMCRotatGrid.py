"""
##  This program draws rotated SMC grid regional plots.
##  It reads cell files and uses own projection to draw 
##  the SMC grid. Projected polygons are collected into 
##  vert variables for grid and subsequent swh plots. 
##
##  First created:    JGLi26Nov2008
##  Converted into a Python function.     JGLi05Dec2018
##  Modified for AMM153km grid plot.      JGLi06Jul2023
##  Add Atctic rotated grid plot.         JGLi18Nov2025
##  Last modified:    JGLi19Nov2025
##
"""

def main():

## Import relevant modules and functions
    import sys
    import numpy as np

    from matplotlib.figure import Figure
    from datetime import datetime
    from readcell import readcell   
    from rgbcolor import rgbcolor
    from eq2lldeg import eq2lldeg
    from smcgrids import smcgrids
    from addtexts import addtexts
    from smcelvrts import smcelvrts
    from smcellmap import smcell, smcmap, smcids

    print( " Program started at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Check input information file name if provided.
    print(sys.argv)
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 3 ):
            gridfile = sys.argv[1]
    else:
        gridfile = 'GridInfoAMM153.txt'

## Read global grid information file. 
    with open( gridfile, 'r' ) as flhdl:
## First line contains grid name and number of resolution levels.
        nxlne = flhdl.readline().split()
        Gname = nxlne[0]
        Level = int(nxlne[1])
        print(" Input grid name and number of levl= ", Gname, Level)
## Second line contains zlon zlat dlon dlat of size-1 cell parameters.
        nxlne = flhdl.readline().split()
        zdlnlt = np.array(nxlne, dtype=float)
        print(" Input grid zlon zlat dlon dlat = \n", zdlnlt) 
## Third line is the working directory and cell array subdirectory.
        nxlne = flhdl.readline().split()
        Wrkdir=nxlne[0]
        DatGMC=nxlne[1]
        MCodes=nxlne[2]
        print(" Wrkdir, DatGMC and MCodes = \n", nxlne) 
## Forth line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl) 
## Fifth line stores the rotated polon and polat values.
        nxlne = flhdl.readline().split()
        Polon = float(nxlne[0])
        Polat = float(nxlne[1])
        print(" Rotated N Polon Polat = ", Polon, Polat) 
## Final line is the WW3SWH path, propagation SWH dir and number of steps per hour.
        nxlne = flhdl.readline().split()
        print(" SWH and Prop OutDat = \n", nxlne)
## End of reading grid information file.

## Read global and Arctic part cells. 
    Cel_file=DatGMC+Gname+'Cels.dat'
    Bndyfile=DatGMC+Gname+'Bdys.dat'
    Dry_file=DatGMC+Gname+'Drys.dat'

    headrs, cel = readcell( [Cel_file] ) 
    numbrs=headrs[0].split()
    ng = int( numbrs[0] )
    n1 = int( numbrs[1] )
    n2 = int( numbrs[2] )
    print( numbrs )

    na = nb = 0
    nc = ng + na
    print( Gname+' total cell number = %d' % nc )
    print( Gname+' N1 and N2 numbers = %d, %d' % (n1,n2) )

## Find out cell covered range.
    ic0=cel[:,0]; ic2=cel[:,2]
    istr = np.min(ic0)
    iend = np.max(ic0 + ic2) 
    jc1=cel[:,1]; jc3=cel[:,3]
    jstr = np.min(jc1)
    jend = np.max(jc1 + jc3)
    print (" Cell i range:", istr, iend)
    print (" Cell j range:", jstr, jend)

## Read grid boudnary cell array.
    headrs, bcel = readcell( [Bndyfile] )
    nbdy = int( headrs[0].split()[0] )
    print( Gname+' bdy cell number = %d' % nbdy )

## Read dry (depth <= 0) cell array, if any.
    headrs, dcel = readcell( [Dry_file] )
    ndry = int( headrs[0].split()[0] )
    print( Gname+' dry cell number = %d' % ndry )

## Append dry cells to boundary cell list.
    if( ndry > 0 ):
        bdcel = np.vstack( (bcel, dcel) )
        print(" Merged boundary and dry cell array shape ", bdcel.shape)
    else:
        bdcel = bcel


## Initial txtary list as [txt, colr, fontsize].
    fntsz = 12.0
    fntsa = 1.25*fntsz
    fntsb = 1.50*fntsz

    txtary = [ [Gname+' Grid', 'k', fntsb],
               ['NC='+str(nc), 'r', fntsa],  
               ['NBdy='+str(nbdy), 'r', fntsa], 
               ['NDry='+str(ndry), 'r', fntsa] ] 

## Use own color map and defined depth colors 
    colrfile = MCodes+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Maximum mapping radius.
    radius=10.0

    print (" Draw SMC grid for "+Gname)

## Projection parameters are different for grids.
    if( Gname == 'AMM153km' ):
## European AMM153km regional plot
        pangle=9.5 
        plon= -1.0
        plat=  2.0
        clrbxy=[ 8.5, -9.5,  0.6,  9.0]
        sztpxy=[ 14.5, 13.0, 5.0, -6.0]
        rngsxy=[-11.0, 11.0,-10.3,10.0]
#       bufile=MCodes+'ECBuoys.dat'
        bufile=''
    
    elif( Gname == 'RtdArc' ):
## Arctic6125 rotated regional plot
        pangle=28.0 
        plon= 0.0
        plat= 0.1 
        clrbxy=[ 10.0, 1.0,  0.8,  9.0]
        sztpxy=[ 10.0, 10.0, 5.0, 10.0]
        rngsxy=[ -9.0, 12.0,-10.3,10.6]
        bufile=Wrkdir+'RtdArcBuoysRtd.txt'

    else:
        print(" Not defined grid domain: ", Gname)
        exit()
 
    papror='portrait'

    print( " Start loop over cells at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Projection pole lon-lat and angle
    rdpols=[radius, pangle, plon, plat]

## Find boundary cell ids for the sub-grid.
    nbdry = smcids(bdcel, cel)
    ncbdy = nbdry[0:nbdy]
    print(" len(nbdry), len(ncbdy), nbdy =", len(nbdry), len(ncbdy), nbdy)

## Find boundary cell central xlon ylat in rotated grid. 
    xlon, ylat = smcell(ncbdy, cel, zdlnlt)

## Convert rotated lat-lon into standard lat-lon values.
    SLat, SLon = eq2lldeg( ylat, xlon, Polat, Polon )

## Create cell vertices
    nvrts, ncels, svrts, scels, nsmrk = smcelvrts( cel, zdlnlt, rdpols, 
                  rngsxy, excids=nbdry)

    print(" nsmrk, nbdy, ndry =", nsmrk, nbdy, ndry)

## Save boundary cell sequential number list for the sub-grid.
    fmt = '%8d '
    Bndylist = Wrkdir+Gname+'Blst.dat'
## Boundary cell sequential numbers have to increase by 1 for WW3. JGLi06Oct2020
    np.savetxt(Bndylist, np.array(ncbdy)+1, fmt=fmt, header='',  comments='')

## Save the boundary cell SLon, SLat to generate boundary condition in WW3.
    hdr = f'{nbdy:8d} \n'
    fms = '%s '
    Bndylnlt = Wrkdir+Gname+'Blnlt.dat'
    with open(Bndylnlt, 'w') as flhd:
        flhd.writelines(hdr)
        for j in range(nbdy):
            if( ncbdy[j] >= 0 ):
                flhd.write(f'{SLon[j]:9.3f} {SLat[j]:8.3f}   0.0  0.0  1 \n' )
    print(" Boundary cells saved in "+Bndylnlt )

## Obstruction ratio is all 0 for this grid.
    kobstr = np.zeros((nc), dtype=int)
    hdrline = f"{nc:8d} {1:5d}"
    Obsfile = Wrkdir+Gname+'Obst.dat'
    np.savetxt(Obsfile, kobstr, fmt='%4d', header=hdrline, comments='')

## Set plot size and limits and message out anchor point.
    ngabjm=[nc, npl, nbdy+ndry, ndry]
    config=np.array([rdpols, sztpxy, rngsxy, clrbxy, ngabjm])
    pzfile=DatGMC+Gname+'Vrts.npz'

## Store selected north and south verts and cell numbers for swh plots.
## Use the np.savez to save 3/5 variables in one file.  JGLi22Feb2019 
    np.savez( pzfile, nvrt=nvrts, ncel=ncels, cnfg=config) 

## These variables could be loaded back by
#   vrtcls = np.load(DatGMC+Gname+'Vrts.npz')
#   nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']; config=vrtcls['cnfg']; 

## Draw your selected grid plot.
    epsfile=Wrkdir+Gname+'grd.eps' 

    fig = Figure(figsize=sztpxy[0:2])
    ax = fig.subplots()
    smcgrids(ax, cel, nvrts,ncels,colrs,config, 
             buoys=bufile, nmark=nsmrk[0]) 

    xydxdy=[sztpxy[2],sztpxy[3], 0.0, -0.6]
    addtexts(ax, xydxdy, txtary)

    fig.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

## Save the selected plot.
    print(" ...... Saving file ", epsfile)
    fig.savefig(epsfile, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)
    fig.clear()

    print( " Program finished at %s " % datetime.now().strftime('%F %H:%M:%S') )

## End of main function.


if __name__ == '__main__':
    main()

## End of SMCRotatGrids program.

