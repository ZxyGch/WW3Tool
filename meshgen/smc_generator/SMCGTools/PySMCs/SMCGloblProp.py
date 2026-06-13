"""
## Program to draw SMC global grid propagation test results.
##
## First created:    JGLi12Sept2005
## Converted into Python.    JGLi20Dec2018
## Last modified:    JGLi12Aug2025
##
"""

def main( ):

## Import relevant modules and functions
    import sys
    import numpy as np
    import matplotlib.pyplot as plt

    from datetime import datetime, timedelta

    from readtext import readtext
    from readcell import readcell
    from rgbcolor import rgbcolor
    from smcswhcv import smcswhcv 
    from smcfield import smcfield 
    from addtexts import addtexts 

## Check input information file name if provided.
    print(sys.argv)
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 3 ):
            gridfile = sys.argv[1]
    else:
        gridfile = 'GridInfo61250.txt'

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
        print(" Working directory and DatGMC = \n", nxlne)
## Fourth line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl)
## Fifty line is the SWH files and propagation test output directories.
        nxlne = flhdl.readline().split()
        SWHdir=nxlne[0]
        OutDat=nxlne[1]
        snhour=nxlne[2]
        print(" SWHdir OutDat and nhr = \n", nxlne)

## Read the cell array and Arctic part if any.
    Cel_file = [ DatGMC+Gname+'Cels.dat' ]
    if( npl > 0 ):
        Arc_file = DatGMC+Gname+'BArc.dat'
        Cel_file.append( Arc_file )

    headrs, cel = readcell( Cel_file )
    ng = int( headrs[0].split()[0] )
    nc = ng
    if( npl > 0 ):
        NArB = headrs[1].split()
        na = int( NArB[0] )
        nb = int( NArB[1] )
        nbg= int( NArB[2] )
        nc = ng + na
    print (' Merged total cel number = %d' % nc )

## Default Python library path of MyCodes.
    MyCodes='./'

## Use own color map and defined depth colors 
    colrfile = MyCodes+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Possible selection of your plot types. 
    gorloc={0:'Global',1:'EuroArc',2:'Pacific',3:'Regular'}

## Prompt selection choices and ask for one input
    print (" \n ", gorloc)
    instr = input("\n *** Please enter your selected number here > ")
    m = int(instr)
    pltype=gorloc.get(m, 'Invalid_selection')
    if( pltype == 'Invalid_selection' ): 
        print ("Invalid selection, program terminated.")
        exit()

    print (" Draw SWH plots "+pltype)

## Choose global or local verts from different files.
    vrfile = DatGMC+Gname+'Vrts'+pltype[0:4]+'.npz'
    vrtcls = np.load( vrfile )

    if( pltype == 'Global' ):
        nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']
        svrts = vrtcls['svrt'] ; scels = vrtcls['scel']
        config = vrtcls['cnfg']
        print (' n/svrts/cels config read ' )

    else:
        nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel'] 
        config = vrtcls['cnfg']
        print (' nvrts, ncels and config read ' )

## All eps file output in portrait format.
    papror='portrait'

## Figure size and text positions.
    sztpxy=config[1]
    rngsxy=config[2]
    tpx = sztpxy[2]; tpy = sztpxy[3]

## Alternative font sizes.
    fntsz=12.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz

## Define spectral direction
    ndir=36
    theta=np.arange(ndir)*np.pi*2.0/ndir

## Add a spectral array plots for the Northern stripe 
    x0= 3.0
    y0= 5.0
    t0=np.pi*0.25
    cs=np.cos(theta + t0)
    xn=theta*0.0+x0
    yn=theta*0.0+y0
    for i in range(ndir):
        if( cs[i] > 0.0 ): 
            spc=1.2*cs[i]*cs[i]
            xn[i]=x0+spc*np.cos(theta[i])
            yn[i]=y0+spc*np.sin(theta[i])

## Add another spectral array plots for the Southern stripe 
    x1=-2.0
    y1=-8.0
    cs=np.cos(theta - t0)
    xs=theta*0.0+x1
    ys=theta*0.0+y1
    for i in range(ndir):
        if( cs[i] > 0.0 ): 
            spc=1.2*cs[i]*cs[i]
            xs[i]=x1+spc*np.cos(theta[i])
            ys[i]=y1+spc*np.sin(theta[i])

## Polar disk spectral array uses the Southern one but new location
    xp= 3.0
    yp= 8.0

## Atlantic disk spectral array uses the Southern one but new location
    xt=-1.0
    yt=-1.0

## Specify number of steps per hour from GridInfo file.
    nhr= int(snhour)
    vunit='SWH m'

## Read in cell concentration data files from a list file
    hdr, cnfiles = readtext(OutDat+'cfiles.txt')
    cfiles = cnfiles.astype(str).reshape(len(cnfiles))

## loop over available files 
#   for nn in range(0,len(cnfiles),2):
    for nn in range(0,len(cnfiles),1):
        dfile=OutDat+cfiles[nn] 

        hdlist, swh2d = readtext(dfile)
        mt = int(hdlist[0])
        mc = int(hdlist[1])
        swhs = swh2d.flatten()[0:mc]

        print (' Plotting cell number mc = %d' % mc )

## Convert time step for output file
        ntsp='NTS = %5d' % (mt)
        thrs='T = %6.2f hr' % (float(mt)/nhr) 

## Convert swh field into color indexes.
        nswh, swhmnx, swhscl = smcswhcv( swhs )

        txtary=[ ['SWHmn='+swhmnx[0], 'b', fntsa],
                 ['SWHmx='+swhmnx[1], 'r', fntsa],
                 [ thrs,              'k', fntsa],
                 [ Gname+' SWH m',    'r', fntsb] ]

## Call function to draw the swh plot.
        epsfl = Wrkdir+'Hs'+pltype[0:2]+cfiles[nn][2:7]+'.eps'
        fig = plt.figure( figsize=(sztpxy[0:2]) )

        if( pltype == 'Global' ):

## Draw SWH field on northern heimisphere panel.
            ax1=fig.add_subplot(1,2,1)
            smcfield(ax1, nswh, nvrts, ncels, colrs, config,
                     vscle=swhscl, vunit=vunit)
## Add spectral array plots for the northern region
            for i in range(ndir):
                ax1.plot([x0,xn[i]], [y0,yn[i]], 'r-', linewidth=1)
                ax1.plot([xp,xp-x1+xs[i]], [yp,yp-y1+ys[i]], 'r-', linewidth=1)
                ax1.plot([xt,xt-x1+xs[i]], [yt,yt-y1+ys[i]], 'r-', linewidth=1)

## Draw field on southern hemisphere subplot panel.
            ax2=fig.add_subplot(1,2,2)
            smcfield(ax2, nswh, svrts, scels, colrs, config,
                     vscle=swhscl, vunit=' ')

## Add a spectral array plots for the southern region
            for i in range(ndir):
                ax2.plot([x1, xs[i]], [y1, ys[i]], 'r-', linewidth=1)

## Put statistic information inside subplot ax2
            ax2.text(sztpxy[2], -sztpxy[3]-0.9, txtary[3][0],
                horizontalalignment='center', fontsize=fntsb, color='r')

            xydxdy=[sztpxy[2], sztpxy[3], 0.0, 0.6]
            addtexts(ax2, xydxdy, txtary[0:3])

            plt.subplots_adjust(left=0.01, bottom=0.00, right=0.99, 
                                 top=1.00, wspace=0.01, hspace=0.0)

        elif( pltype == 'Regular'):

## Draw global field on regular box format.
            ax=fig.add_subplot(1,1,1)
            from smcfrglr import smcfrglr

            smcfrglr(ax, nswh, nvrts, ncels, colrs, config,
                     fntsz=fntsz, vscle=swhscl, vunit=vunit) 

            tpx=(rngsxy[1] - rngsxy[0])*0.5
            tpy=rngsxy[2]+1.0
            ax.text(tpx, tpy, Gname+' '+thrs+' WHmn='+swhmnx[0]+' WHmx= '+swhmnx[1],
                horizontalalignment='center', fontsize=fntsb, color='k')
            plt.subplots_adjust(left=0.03, bottom=0.04, \
                               right=0.99, top=0.98)

        else:
            ax=fig.add_subplot(1,1,1)

            smcfield(ax, nswh, nvrts, ncels, colrs, config,
                     vscle=swhscl, vunit='SWH m')

            xydxdy=[sztpxy[2], sztpxy[3], 0.0, -0.6]
            addtexts(ax, xydxdy, txtary) 

            plt.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)


        print(" ... saving file as "+epsfl)
        plt.savefig(epsfl, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)
        plt.close()

        print (" Finish plot No.", nn," at ", datetime.now())

## End of date loop

## End of main function.

if __name__ == '__main__':
    main()

## End of SMCGloblProp.py main program ##

