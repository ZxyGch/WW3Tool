"""
##  Draw local swh plot with given polycollections and cell
##  array. Output as A3 ps file.        JGLi28Feb2019
#;
"""

def swhlocal(swhs,verts,ncels,colrs,config, fsize=12.0,
        mdlname='SMC',datx='2018',psfile='output.ps', 
        paprorn='portrait', paprtyp='a3'):


##  Import relevant modules and functions

    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    from matplotlib.collections import PolyCollection

    from readtext import readtext
    from colrboxy import colrboxy
    from scale_swh import scale_swh

##  Degree to radian conversion parameter.
    d2rad=np.pi/180.0

##  Local plot configuration parameters
    rdpols=config[0]
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]

##  Maximum mapping radius.
    radius=rdpols[0]

##  Set up wave height scale and marks with colrs.N.
##  colrs.N returns colrs' total number of colors 256.
    waveht, factor, residu, marks, ncstr, nclrm = scale_swh(nclrm=colrs.N)

    resmn1=residu - 1.0
    nswh0= ncstr+ int( factor*np.log(-resmn1 + residu) )

#   print ' nswh0 and marks = ', nswh0, marks
#   print ' factor, residu, resmn1 = %f, %f, %f' % (factor, residu, resmn1) 

##  Alternative font sizes.
    asize=1.25*fsize
    bsize=1.50*fsize

##  Some constant variables for plots.
    xprop={'xlim':rngsxy[0:2], 'xlabel':''}
    yprop={'ylim':rngsxy[2:4], 'ylabel':''}
    
##  Use ijk to count how many times to draw.
    ijk=0

    if True:
##  Work out max and min values, excluding missing data (-999.0)
        cmax = swhs.max()
        cmin = swhs[ swhs > -999.0 ].min()
        print ( ' swh range %f, %f' % (cmin, cmax) )
        cmxs = 'SWHmx = %6.2f m' % cmax
        cmns = 'SWHmn = %10.3E' % cmin

##  Reset missing values (-999.0) to be -resmn1 
        swhs[ swhs < -resmn1] = -resmn1

##  Trim large values into plot range if any
        swhs[ swhs > 32.0 ] = 32.0 

##  Convert swhs with logarithm scale.
        icnf = ncstr+ np.rint( factor*np.log(swhs+residu) )
        nswh = np.array( icnf, dtype=int )

        print (" Drawing "+psfile)

##  Set up first subplot and axis for northern hemisphere

        fig=plt.figure(figsize=sztpxy[0:2])
        ax=fig.add_subplot(1,1,1)
        ax.set(**xprop)
        ax.set(**yprop)
        ax.set_aspect('equal')
        ax.set_autoscale_on(False)
        ax.set_axis_off()
        plt.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

## Prepare PolyCollection for this plot.
        polynorth = PolyCollection(verts)

## Create color array for this plot
        pcface = []
        pcedge = []
        for i in ncels:
            if( nswh[i] != nswh0 ): 
                pcface.append(colrs(nswh[i]))
                pcedge.append(colrs(nswh[i]))
            else:
                pcface.append(colrs(255)) 
                pcedge.append(colrs(0)) 

#   smcpoly.set_color(pcolr)    ## This line defines both edge and face color.
        polynorth.set_facecolor(pcface)
        polynorth.set_edgecolor(pcedge)
        polynorth.set_linewidth( 0.2 )
#       print (" Drawing north hemisphere cells ... ")
        ax.add_collection(polynorth)  

##  Draw colorbar inside plot.
        xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks)
        ax.add_collection(clrply)
        dkx=clrbxy[2]; dky=clrbxy[3]
        for i in range(len(waveht)):
            m = marks[i]
            if( dkx < dky ): 
                plt.text(xkeys[0]+1.15*dkx, ykeys[m], str(waveht[i]),
                    verticalalignment='center', fontsize=fsize, color='b' )
            else:
                plt.text(xkeys[m], ykeys[0]+1.15*dky, str(waveht[i]),
                    horizontalalignment='center', fontsize=fsize, color='b' )

        if( dkx < dky ):
            plt.text(xkeys[0]+2.0*dkx, ykeys[marks[3]], 'SWH m',
                rotation=90,verticalalignment='center', fontsize=asize, color='k' )
        else:
            plt.text(xkeys[marks[3]], ykeys[0]+2.0*dky, 'SWH m',
                rotation=0,horizontalalignment='center', fontsize=asize, color='k' )

##  Put cell information inside plot
        tpx= sztpxy[2]
        tpy= sztpxy[3]
        dpy= 0.6
        plt.text(tpx, tpy-dpy*1., mdlname, 
             horizontalalignment='center', fontsize=bsize, color='g' )
        plt.text(tpx, tpy-dpy*2., datx,
             horizontalalignment='center', fontsize=asize, color='k' )
        plt.text(tpx, tpy-dpy*3., cmxs,
             horizontalalignment='center', fontsize=fsize, color='r' )
        plt.text(tpx, tpy-dpy*4., cmns,
             horizontalalignment='center', fontsize=fsize, color='b' )

##  Refresh subplots and save them.
        plt.savefig(psfile, dpi=None,facecolor='w',edgecolor='w', 
                    orientation=paprorn,papertype=paprtyp)


        plt.close()


##  End of swhlocal 

