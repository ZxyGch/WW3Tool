"""
Generate a colour bar polycollection with given x, y location.
The colour index arrays will generated out of given colormap.

              JGLi04Feb2019 

"""

##  Input variables include x, y as Numpy Arrays or lists for the 
##  colorbar locations, the colormap to be plotted, integer list 
##  or Numpy Array marks for key scale ticks as enlarged polygon. 
##  Tick labels should be added outside this program when the 
##  colorbar PolyCollection is drawn in a corresponding plot. 

def colrpoly(x, y, colrmap, marks, ncstr=0):

    import numpy  as np

    from matplotlib.collections import PolyCollection

## Workout color bar orientaion by x and y sizes
## and generate poly verts and colors. 
    nx=len(x) 
    ny=len(y) 
    verts = []
    pcolr = []
    ic = ncstr

    if( nx > ny ):  ## Horizontal color bar
        syc=[y[0],y[0],y[1],y[1]]
        y1 = y[0]+1.1*(y[1]-y[0])
        sym=[y[0],y[0],y1,  y1]
        dx = x[1] - x[0]
        for xi in x:
            sxc=[xi, xi+dx, xi+dx, xi]
            verts.append(list(zip(sxc,syc)))
            pcolr.append(colrmap(ic))
            ic += 1
        for i in marks:
            xi=x[i]
            sxc=[xi, xi+dx, xi+dx, xi]
            verts.append(list(zip(sxc,sym)))
            pcolr.append(colrmap(i))
 
    else:           ## Vertical color bar
        sxc=[x[0],x[1],x[1],x[0]]
        x1 = x[0]+1.1*(x[1]-x[0])
        sxm=[x[0],x1,  x1,  x[0]]
        dy = y[1] - y[0]
        for yj in y:
            syc=[yj, yj, yj+dy, yj+dy]
            verts.append(list(zip(sxc,syc)))
            pcolr.append(colrmap(ic))
            ic += 1
        for j in marks:
            yj=y[j]
            syc=[yj, yj, yj+dy, yj+dy]
            verts.append(list(zip(sxm,syc)))
            pcolr.append(colrmap(j))

## Generate PolyCollection
    cbarpoly = PolyCollection(verts)
    cbarpoly.set_color(pcolr)

    return cbarpoly 


if __name__ == '__main__':
    main()

