##  Created to draw a 3km bathymetry file created from GEBCO_2022
##  saved in ../Bathys/.   JGLi20Apr2023

def main():

    import sys
    import numpy    as np
    import netCDF4  as nc
    import matplotlib.pyplot as plt
    from rgbcolor import rgbcolor

##  Read online argument for input bathymetry file.
    if len(sys.argv) > 1:
       bathyfile = sys.argv[1]
    else:
       bathyfile = 'Bathy088_059deg.nc'

##  Use own color map and defined depth colors 
    colrfile = './rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

#   bathy = '../Bathys/Bathy044_033deg.nc'
    bathy = '../Bathys/'+bathyfile
    datas = nc.Dataset(bathy)

    print(datas)            ## Print information about the dataset.

    print(datas.__dict__)

    print(datas.__dict__['description'])

    for var in datas.dimensions.values(): print(var)

    nlat = datas.dimensions['lat'].size
    nlon = datas.dimensions['lon'].size
    dlat = 180.0 / float(nlat)
    dlon = 360.0 / float(nlon)

    print(" nlat, nlon, dlat, dlon =", nlat, nlon, dlat, dlon )

    lonout = datas.variables['lon'][:]
    latout = datas.variables['lat'][:]
    bathym = datas.variables['elevation'][:,:]
    depthmax = np.amin(bathym)
    hightmax = np.amax(bathym)
    print(' bathy range=', depthmax, hightmax)

    print(lonout[0:nlon:int(nlon/10)])
    print(latout[0:nlat:int(nlat/10)])

    datas.close()

##  Draw a pcolormesh bathymetry plot.
    sztpxy=[ 16.0, 9.0,-10.2,-10.3]
    fig=plt.figure(figsize=sztpxy[0:2])
    plt.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)
    ax=fig.add_subplot(1,1,1)

    print(' drawing pcolormesh plot ...')
    plt.pcolormesh(lonout, latout, bathym, vmin=depthmax, cmap=colrs)
#   plt.colorbar()

    print(' drawing overlapping coastline ...')
    plt.contour(lonout, latout, bathym, [0], colors='k', linewidths=0.5)

    psfile='../tmpfls/'+bathyfile[0:-3]+'.jpg'
    print(' saving ps file '+psfile )
    plt.savefig(psfile, dpi=200.0,facecolor='w',edgecolor='w', \
                orientation='landscape')

#   plt.show()
    
## End of main function.

if __name__ == '__main__':
    main()

## End of BathymetryView.py program.

