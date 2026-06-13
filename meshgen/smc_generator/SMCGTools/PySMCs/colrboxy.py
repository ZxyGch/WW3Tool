"""
Generate a colour bar polycollection with given key box 
cboxy=[x, y, dx, dy] and colormap, plus marks.
The colour index arrays will generated out of given colormap.

              JGLi01Mar2019 

"""

##  Input variables include x, y as Numpy Arrays or lists for the 
##  colorbar locations, the colormap to be plotted, integer list 
##  or Numpy Array marks for key scale ticks as enlarged polygon. 
##  Tick labels should be added outside this program when the 
##  colorbar PolyCollection is drawn in a corresponding plot. 

def colrboxy(cboxy, colrmap, marks, ncstr=0, nclrm=256):

    import numpy  as np

    from matplotlib.collections import PolyCollection

## Workout color bar orientaion by x and y sizes
## and generate poly verts and colors. 
    x0=cboxy[0]
    y0=cboxy[1]
    bx=cboxy[2] 
    by=cboxy[3] 
    verts = []
    pcolr = []
    ic = ncstr

    if( bx > by ):  ## Horizontal color bar
        dx = bx/nclrm
        xkeys=np.arange(nclrm)*dx + x0
        ykeys=np.array([y0, y0+by])
        syc=[y0,y0,y0+by,y0+by]
        for xi in xkeys:
            sxc=[xi, xi+dx, xi+dx, xi]
            verts.append(list(zip(sxc,syc)))
            pcolr.append(colrmap(ic))
            ic += 1

        dm = 1.1*by
        sym=[y0,y0,y0+dm,y0+dm]
        for i in marks:
            xi=xkeys[i]
            sxc=[xi, xi+dx, xi+dx, xi]
            verts.append(list(zip(sxc,sym)))
            pcolr.append(colrmap(i))
 
    else:           ## Vertical color bar
        dy = by/nclrm 
        xkeys=np.array([x0, x0+bx])
        ykeys=np.arange(nclrm)*dy + y0
        sxc=[x0,x0+bx,x0+bx,x0]
        for yj in ykeys:
            syc=[yj, yj, yj+dy, yj+dy]
            verts.append(list(zip(sxc,syc)))
            pcolr.append(colrmap(ic))
            ic += 1

        dm = 1.1*bx
        sxm=[x0,x0+dm,x0+dm,x0]
        for j in marks:
            yj=ykeys[j]
            syc=[yj, yj, yj+dy, yj+dy]
            verts.append(list(zip(sxm,syc)))
            pcolr.append(colrmap(j))

## Generate PolyCollection
    cbarpoly = PolyCollection(verts)
    cbarpoly.set_color(pcolr)

    return ( xkeys, ykeys, cbarpoly )


if __name__ == '__main__':
    main()

