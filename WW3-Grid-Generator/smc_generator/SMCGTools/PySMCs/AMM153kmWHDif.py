"""
##  Program to draw SWH difference for AMM153 model.
##  First created:    JGLi16Feb2012
##  Converted into Python.    JGLi20Dec2018
##  Modified for AMM153km.    JGLi26Jul2023
##  Last modified:    JGLi18Nov2025
##
"""

def main():
## Import relevant modules and functions
    import sys
    import numpy  as np
    import pandas as pd

## Only use Figure, not pyplot any more.  JGLi06Nov2025
    from matplotlib.figure import Figure

    from datetime import datetime 
    from readtext import readtext
    from readcell import readcell
    from rgbcolor import rgbcolor
#   from smcswhcv import smcswhcv 
    from whtdfsqr import whtdfsqr 
    from smcfield import smcfield 
    from addtexts import addtexts 

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
        print(" Working directory and DatGMC = \n", nxlne) 
## Forth line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl) 
## Fifth line stores the rotated polon and polat values.
        nxlne = flhdl.readline().split()
        Polon = float(nxlne[0])
        Polat = float(nxlne[1])
        print(" Rotated N Polon Polat = ", Polon, Polat) 
## Final line is the SWH files and propagation test output directories.
        nxlne = flhdl.readline().split()
        SWHdir=nxlne[0]
        OutDat=nxlne[1]
        print(" SWH and Prop OutDat = \n", nxlne)
## End of reading grid information file.

## Read global and Arctic part cells. 
    Cel_file = DatGMC+Gname+'Cels.dat'

    headrs, cel = readcell( [Cel_file] )
    numbrs = np.array( headrs[0].split() ).astype(int)
    print( numbrs )

    ng = int( headrs[0].split()[0] )
    na = nb = 0
    nc = ng 
    print (' Merged total cel number = %d' % nc )

##  Use own color map and defined depth colors 
    colrfile = MCodes+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

##  Read start and end datetime from fdate
    datefl = open( Wrkdir+'strendat', 'r')
    strend = datefl.read().split()
    datefl.close()

##  Convert into datetime variables
    start = datetime.strptime(strend[0], '%y%m%d%H')
    endat = datetime.strptime(strend[1], '%y%m%d%H')
    timdx = pd.date_range(start=start, end=endat, freq=strend[2])

    print (" Draw SWH plots for "+Gname)

##  Choose global or local verts from different files.
    vrfile = DatGMC+Gname+'Vrts.npz'
    vrtcls = np.load( vrfile )

    nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel'] 
    config = vrtcls['cnfg']
    print (' nvrts, ncels and config read ') 
    
## Selected plot configuration parameters.
    sztpxy = config[1]
    rngsxy = config[2]

## Alternative font sizes.
    fntsz=12.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz

##  Loop over datetime of swh files
    print (" SWH file loop started at ", datetime.now())

##  Use ijk to count how many times to draw.
    ijk=0

## Wave height difference scale used for WHtDiff plot.
    whtdifs=[-1.0, -0.5, -0.1, 0, 0.1, 0.5, 1.0]

#   for i in range( ndays*4 ):
    for dt in timdx:
        swhfl = SWHdir + dt.strftime('%y%m%d%H') + '.hs'

        hdlist, swh2d = readtext(swhfl)
        mc = int(hdlist[4])
        swhr = swh2d.flatten()[0:mc]

## Read SWnd run SWHt from a sub-directory.
        swhfl = SWHdir[0:-4]+'zSWndSWHs/ww3.' + dt.strftime('%y%m%d%H') + '.hs'

        hdlist, swh2d = readtext(swhfl)
        mc = int(hdlist[4])
        swhs = swh2d.flatten()[0:mc]

## SWHt difference between two runs.
        swhdif = swhs - swhr

##  Calculate statistical parameters.
        swhmean = np.mean(swhdif, axis=0)
        swhstdv = np.std( swhdif, axis=0)
        swhrmse = np.sqrt((swhdif**2).mean())
        meanrms =f'Mean {swhmean:.4f}  RMSE {swhrmse:.4f} m'
        print(meanrms, " StDv ", swhstdv)

##  Skip Arctic polar cell if nc = nga
        if( mc != nc ):
            print ( ' Unmatching mc/nc = %d %d' % (mc, nc) ) 
            exit()
        else:
            print (' Plotting cell number mc = %d' % mc )

##  Convert time step for output file
        datms = dt.strftime('%Y%m%d%H')

## Convert whdf into square root difference colour scales.
        nwhts, whdmnx, whdscl = whtdfsqr(swhdif, whtdifs, 
               nclrm=255, nczro=123) 

        txtary=[ [Gname+' SWHDif',      'k', fntsb],
                 ['SWHDfmn='+whdmnx[0], 'b', fntsz],
                 ['SWHDfmx='+whdmnx[1], 'r', fntsz],
                 [ datms,               'k', fntsa], 
                 [ meanrms,             'g', fntsa] ] 

## Convert swh field into color indexes.
#       nswh, swhmnx, swhscl = smcswhcv( swhs )

#       txtary=[ [Gname+' SWH',    'k', fntsb],
#                ['SWHmn='+swhmnx[0], 'b', fntsa],
#                ['SWHmx='+swhmnx[1]+' m', 'r', fntsa],
#                [datms,     'k', fntsb] ] 

##  Call function to draw the swh plot.
        epsfl = Wrkdir+'swhdif'+Gname[0:3]+dt.strftime('%y%m%d%H') + '.eps'
        fig = Figure( figsize=sztpxy[0:2] )
        ax = fig.subplots()

## Draw the water height difference on given axis panel.
        smcfield(ax, nwhts, nvrts, ncels, colrs, config,
            vscle=whdscl[0:3], fntsz=fntsz, vunit='SWHDif m')

#       smcfield(ax, nswh, nvrts, ncels, colrs, config,
#                vscle=swhscl, vunit='SWH m')

## Draw maximum and minimum cell location marks if within ncels list.
        maxidx=minidx=0
        if( len(whdmnx) > 3 ): 
            minidx=int(whdmnx[2])
            maxidx=int(whdmnx[3])
            kfnd=0
            for k in range( len(ncels) ):
                if( ncels[k] == maxidx ): 
                    mxpoly=nvrts[k][0]
                    ax.text(mxpoly[0], mxpoly[1], 'M', color='b', 
                        horizontalalignment='left', fontsize=fntsz)
                    kfnd += 1
                if( ncels[k] == minidx ): 
                    mnpoly=nvrts[k][0]
                    ax.text(mnpoly[0], mnpoly[1], 'n', color='r', 
                        horizontalalignment='left', fontsize=fntsz)
                    kfnd += 1
                if( kfnd >=2 ): break

## Put statistic information inside plot ax.
        xydxdy=[sztpxy[2], sztpxy[3]-0.5, 0.0, -0.6]
        addtexts(ax, xydxdy, txtary)
        fig.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

## Save plot and clear figure contents.
        print(" ... Saving plot as", epsfl )
        fig.savefig(epsfl, dpi=None,facecolor='w',edgecolor='w', 
            orientation='portrait')
        fig.clear()

##  Increase ijk for next plot
        ijk += 1
        print (" Finish plot No.", ijk," at ", datetime.now())

##  End of date loop

##  End of main program  ##

if __name__ == '__main__':
    main()

