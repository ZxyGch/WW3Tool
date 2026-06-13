"""
## Function to draw a SMC grid field on a regular box plot.
##
## First created:    JGLi04Mar2019
## Last modified:    JGLi25Apr2025
##
"""

def smcfrglr(ax, nidxs, verts, ncels, colrs, config, 
             fntsz=10, vscle=[], vunit=' '):

## Import relevant modules and functions
    import numpy as np
    from matplotlib.collections import PolyCollection
    from colrboxy import colrboxy

## Degree to radian conversion parameter.
    d2rad=np.pi/180.0

## Alternative font sizes.
    fntsa=1.20*fntsz
    fntsb=1.50*fntsz

## Local plot configuration parameters
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]

## Variable scale parameters.
    if( len(vscle) > 2 ):
        vtcks = vscle[0]
        marks = vscle[1]
        nclrm = vscle[2]
        nidx0 = 0
    if( len(vscle) > 3 ):
        nidx0 = vscle[3]

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
    for i in ncels:
## Mark nidx0 cells to be red.  JGLi03Sep2020
        if( nidxs[i] != nidx0 ):
            pcface.append(colrs(nidxs[i]))
            pcedge.append(colrs(nidxs[i]))
        else:
            pcface.append(colrs(255))
            pcedge.append(colrs(0))

## Create Polygons with selected verts and define edge and face color.
    polynorth = PolyCollection(verts)
    polynorth.set_facecolor(pcface)
    polynorth.set_edgecolor(pcedge)
    polynorth.set_linewidth( 0.2 )

## Draw the selected cells as colored polygons.
    ax.add_collection(polynorth)

## Draw colorbar inside plot.
    xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks, nclrm=nclrm)
    ax.add_collection(clrply)
    dkx=clrbxy[2]; dky=clrbxy[3]
    for i in range(len(vtcks)):
        m = marks[i]
        if( dkx < dky ):    
            ax.text(xkeys[0]+1.15*dkx, ykeys[m], str(vtcks[i]),
                verticalalignment='center', rotation=90, fontsize=fntsz, color='b')
        else:
            ax.text(xkeys[m], ykeys[0]+1.15*dky, str(vtcks[i]),
                horizontalalignment='center', fontsize=fntsz, color='b' )

    if( dkx < dky ):    
        ax.text(xkeys[0]+1.6*dkx, (ykeys[marks[1]]+ykeys[marks[2]])*0.5, vunit,
            verticalalignment='center', rotation=90, fontsize=fntsz, color='b')
    else:
        ax.text((xkeys[marks[1]]+xkeys[marks[2]])*0.5, ykeys[0]+1.6*dky, vunit,
            horizontalalignment='center', fontsize=fntsz, color='b')

## End of function smcfrglr.py. 

