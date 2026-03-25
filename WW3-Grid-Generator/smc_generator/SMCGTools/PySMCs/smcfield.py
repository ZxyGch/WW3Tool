"""
## Draw a field on SMC grid from given verts and indexes.
##
## First created:    JGLi28Feb2019
## Last modified:    JGLi18Apr2025
##
"""

def smcfield(ax, nidxs,verts,ncels,colrs,config, 
        fntsz=10.0, vscle=[], vunit=' ', 
        nmrks=0, ncstr=0, nclrm=256):

## Import relevant modules and functions
    import numpy as np
    from matplotlib.collections import PolyCollection
    from colrboxy import colrboxy

## Degree to radian conversion parameter.
    d2rad=np.pi/180.0

## Local plot configuration parameters
    rdpols=config[0]
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

## Maximum mapping radius.
    radius=rdpols[0]
    pangle=rdpols[1]

## Alternative font sizes.
    fntsa=1.20*fntsz
    fntsb=1.50*fntsz

##  Set up plotting axis parameters. 
    ax.set_xlim(rngsxy[0:2])
    ax.set_ylim(rngsxy[2:4])
    ax.set_aspect('equal')
    ax.set_autoscale_on(False)
    ax.set_axis_off()

## Add an outline circle at equator.
    if( pangle >= 90.0 ):
        ciran=np.arange(1081)*d2rad/3.0
        xcirc=radius*np.cos(ciran)
        ycirc=radius*np.sin(ciran)
        ax.plot(xcirc, ycirc, 'k-', linewidth=0.2)

## Prepare PolyCollection for this plot.
    polynorth = PolyCollection(verts)

## Create color array for this plot
    pcface = []
    pcedge = []
    ncall= len(ncels)
    for k in range( ncall ):
        i = ncels[k]
        if( nidxs[i] != nidx0 ): 
            pcface.append(colrs(nidxs[i]))
            pcedge.append(colrs(nidxs[i]))
        elif( k >= ncall - nmrks ): 
            pcface.append(colrs(254)) 
            pcedge.append(colrs(254)) 
        else:
            pcface.append(colrs(255)) 
            pcedge.append(colrs(0)) 

## Set polygon verts edge and face colors.
    polynorth.set_facecolor(pcface)
    polynorth.set_edgecolor(pcedge)
    polynorth.set_linewidth( 0.2 )

## Drawing the polygons on given axis. 
    ax.add_collection(polynorth)  

## Define and draw colorbar inside plot.
    xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks, 
                                    ncstr=ncstr, nclrm=nclrm)
    ax.add_collection(clrply)
    dkx=clrbxy[2]; dky=clrbxy[3]

    for i in range(len(vtcks)):
        m = marks[i]
        if( dkx < dky ): 
            ax.text(xkeys[0]+1.15*dkx, ykeys[m], 
                str(vtcks[i]), fontsize=fntsz, color='b',  
                verticalalignment='center', rotation=90)
        else:
            ax.text(xkeys[m], ykeys[0]+1.15*dky, 
                str(vtcks[i]), fontsize=fntsz, color='b', 
                horizontalalignment='center')

    if( dkx < dky ):
        ax.text(xkeys[0]+1.6*dkx, ykeys[marks[1]], vunit,
            verticalalignment='center', rotation=90,  
            fontsize=fntsa, color='b' )
    else:
        ax.text(xkeys[marks[1]], ykeys[0]+1.6*dky, vunit,
            horizontalalignment='center', 
            fontsize=fntsa, color='b' )

## End of smcfield function. 

