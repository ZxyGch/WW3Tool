"""
## The smcgrglr function draws a SMC grid as a regular grid box plot.
##
## First created:    JGLi04Mar2019
## Last modified:    JGLi01May2025
##
"""

def smcgrglr(ax, cel, verts, ncels, colrs, config, fntsz=10,  
             nmark=0, ndry=11, vunit='Depth m', buoys=''):

## Import relevant modules and functions
    import numpy as np

    from matplotlib.collections import PolyCollection

    from readtext import readtext
    from colrboxy import colrboxy
    from scale_depth import scale_depth

## Degree to radian conversion parameter.
    d2rad=np.pi/180.0

## Total cell number by cell array
    nc = cel.shape[0]

## Local plot configuration parameters
    zdlnlt=config[0]
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]

## Arctic part cell number if defined.
    Arctic=False
    if( len(config) >4 ): 
        Arctic=True
        nabgpl=config[4]
        na= int(nabgpl[0])
        nb= int(nabgpl[1])
        nbg=int(nabgpl[2])
        npl=int(nabgpl[3])
        ng= nc - na 
        jm=np.max(cel[0:ng, 1])
        j1=cel[ng-1, 3]
        j3=3*j1

## Define depth to color index conversion parameters and marks.
## Use only first 136 colors in colrs(0:255). 
    depth, factr, cstar, marks, ncstr, nclrm = scale_depth(nclrm=136)

## Cell color is decided by its depth value.
    ndeps = np.zeros( (nc), dtype=int )
    for j in range(nc):
        if( cel[j,4] > -ndry ): 
            ndeps[j] = ncstr + np.rint( (cstar - \
                np.log10(cel[j,4]+ndry))*factr ).astype(int)
## Sea level index
    ndep0 = ncstr + np.rint((cstar-np.log10(ndry))*factr).astype(int)
#   print( " Sea level depth index is ", ndep0)

## Use selected cells to draw the plot.
    ax.set_xlim(rngsxy[0:2])
    ax.set_ylim(rngsxy[2:4])
#   ax.set_aspect('equal')
    ax.set_autoscale_on(False)
#   ax.set_axis_off()

## Work out ticks at 30 degree interval.
    x0=int(rngsxy[0]/30.0); xn=int( (rngsxy[1]-rngsxy[0])/30.0 )
    ax.set_xticks( (np.arange(min([13,xn+1]))+x0)*30 )
    ax.tick_params(axis='x', labelsize=fntsz )
    y0=int(rngsxy[2]/30.0); yn=int( (rngsxy[3]-rngsxy[2])/30.0 )
    ax.set_yticks( (np.arange(min([7,yn+1]))+y0)*30 )
    ax.tick_params(axis='y', labelsize=fntsz )

## Create color array for this plot
    pcface = []
    pcedge = []
    kend = len(ncels)
    for k in range(kend):
        i = ncels[k] 
## Mark the Arctic map-east reference region by first and last 
## rings of boundary cells at jm-j3 and jm, same for Antarctic.
        if( Arctic and (cel[i,1] == jm-j3 or cel[i,1] == -jm-j1+j3) ):
            pcface.append(colrs(246))
            pcedge.append(colrs(246))
        elif( Arctic and ( cel[i,1] == jm or cel[i,1] == -jm-j1 ) ):
            pcface.append(colrs(168))
            pcedge.append(colrs(168))
##  Fill last nmark cells to be red.  JGLi03Sep2020
        elif( k >= kend - nmark ):
            pcface.append(colrs(250))
            pcedge.append(colrs(ndeps[i]))
        else:
            pcface.append(colrs(255))
            pcedge.append(colrs(ndeps[i]))

##  Create PolyCollection from selected verts and define edge and face color.
    polynorth = PolyCollection(verts)
    polynorth.set_facecolor(pcface)
    polynorth.set_edgecolor(pcedge)
    polynorth.set_linewidth( 0.2 )

##  Draw the selected cells as colored polygons.
    ax.add_collection(polynorth)

##  Draw colorbar inside plot.
    xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks, nclrm=nclrm)
    ax.add_collection(clrply)
    dkx=clrbxy[2]; dky=clrbxy[3]
    for i in range(len(depth)):
        m = marks[i]
        if( dkx < dky ):    
            ax.text(xkeys[0]+1.15*dkx, ykeys[m], str(depth[i]),
                rotation=-90, verticalalignment='center', fontsize=fntsz, color='b' )
        else:
            ax.text(xkeys[m], ykeys[0]+1.15*dky, str(depth[i]),
                horizontalalignment='center', fontsize=fntsz, color='b' )

    if( dkx < dky ):    
        ax.text(xkeys[0]+1.6*dkx, (ykeys[marks[2]]+ykeys[marks[1]])*0.5, vunit, 
                 rotation=-90,verticalalignment='center', fontsize=fntsz, color='b' )
    else:
        ax.text((xkeys[marks[1]]+xkeys[marks[2]])*0.5, ykeys[0]+1.6*dky, vunit, 
                 rotation=0,horizontalalignment='center', fontsize=fntsz, color='b' )

## Overlay buoy sits on grid map if buoy file is provided.
    if( len(buoys) > 3 ):
        hdr, buoyll = readtext(buoys)
        nmbu=int(hdr[0])
        buoyids=buoyll[:,0].astype(str)
        buoylat=buoyll[:,1].astype(float)
        buoylon=buoyll[:,2].astype(float)

## Mark buoy position on map if it is within plotting range.
## Note regular grid box plot uses lat-lon degree ranges.
        print (' Selected buoys in this plot:')
        for i in range(nmbu):
            if( (rngsxy[0] < buoylon[i] < rngsxy[1]) and 
                (rngsxy[2] < buoylat[i] < rngsxy[3]) ):
                print (' {:6} {:8.3f} {:8.3f}'.format( 
                    buoyids[i], buoylat[i], buoylon[i] ))
                ax.text(buoylon[i], buoylat[i], 'r', fontsize=fntsz, 
                    horizontalalignment='center', color='r')
                ax.text(buoylon[i], buoylat[i], '.', fontsize=fntsz*2,
                    horizontalalignment='center', color='r')

## End of function smcgrglr.py.

