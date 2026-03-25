"""
##  The addtexts function prints text messages on a given axis 
##  with specified position, increment, fontsize and colors. 
##
##  First created:    JGLi04Mar2019
##  Last modified:    JGLi31Mar2025
##
"""

def addtexts(ax, xydxdy, txtary, rotate=0.0, hrzlgn='center', vrtlgn='center'): 

## Text start positions and increments
    xst=xydxdy[0]; yst=xydxdy[1]
    dxp=xydxdy[2]; dyp=xydxdy[3]

## Print txtary one by one from x/yst at steps dxp and dyp.
    for k in range(len(txtary)):
        txtk = txtary[k]
        ax.text(xst+k*dxp, yst+k*dyp, txtk[0], color=txtk[1], fontsize=txtk[2],
                verticalalignment=vrtlgn, rotation=rotate, 
                horizontalalignment=hrzlgn)
    
    return

## End of addtexts function. 

