#!/usr/bin/python
# -*-coding:Utf-8 -*

# Read bottom

import numpy as np
import sys, os
import matplotlib.pyplot as plt

#filedir = sys.argv[1]

#fullfile= filedir + '/africa_10m.depth_ascii'
fullfile1 = sys.argv[1]
fullfile2 = sys.argv[2]
modif = sys.argv[3]  # 0: no modif ; 1: modif

mod = fullfile2.split('.')[-2].split('/')[-1]
print "mod:", mod

mask1 = np.loadtxt(fullfile1)
mask2 = np.loadtxt(fullfile2)

#print "shape(mask1):", np.shape(mask1)
#print "shape(mask2):", np.shape(mask2)


fig = plt.figure(1)
fileout1 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_mask1.png'
plt.pcolormesh(mask1)
plt.colorbar()
plt.savefig(fileout1)

fig = plt.figure(2)
fileout2 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_mask2.png'
plt.pcolormesh(mask2)
plt.colorbar()
plt.savefig(fileout2)

# compute difference
diff=mask2-mask1
#print "type(diff):", type(diff)

fig = plt.figure(3)
fileout3 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_diff_mask.png'
plt.pcolormesh(diff)
plt.colorbar()
plt.title('mask2 - mask1')
plt.savefig(fileout3)


# Create zoom on CRB zone

lonminzoom = -66
lonmaxzoom = -58.8
latminzoom = 9 
latmaxzoom = 19.5

# knowing the grid ranges from -180° to 179.5° with 0.5° res in longitudes,
# and from -78° to 80° with 0.5° res in latitudes:
ilonmin = int((lonminzoom + 180)/0.5) #-30
ilonmax = int(((lonmaxzoom + 180)/0.5) +1) #+10
ilatmin = int((latminzoom + 78)/0.5)
ilatmax = int(((latmaxzoom + 78)/0.5)+1) #+30

print "ilonmin, ilonmax, ilatmin, ilatmax:", ilonmin,ilonmax,ilatmin,ilatmax

fig = plt.figure(4)
fileout4 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_diff_mask_zoom.png'
plt.pcolormesh(diff[ilatmin:ilatmax,ilonmin:ilonmax])
plt.colorbar()
plt.title('mask2 - mask1')
plt.savefig(fileout4)

# check that it's the right zone
fig= plt.figure(5)
fileout5 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_mask1_zoom.png'
plt.pcolormesh(mask1[ilatmin:ilatmax,ilonmin:ilonmax])
plt.colorbar()
plt.savefig(fileout5)

fig= plt.figure(6)
fileout6 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_mask2_zoom.png'
plt.pcolormesh(mask2[ilatmin:ilatmax,ilonmin:ilonmax])
plt.colorbar()
plt.savefig(fileout6)


# superimpose new mask AND where it has changed ?
idiff= np.where(diff!=0) # size: 2*ndiff
print "type(idiff):", type(idiff)
print "shape(idiff):", np.shape(idiff)
#print "idiff:", idiff

diff2 = np.ma.masked_array(diff, diff==0)

fig = plt.figure(7)
fileout7='/export/home/data/GRIDGEN/PYTHON/'+mod+'_diff_mask_zoom_layers.png'
plt.pcolormesh(mask2[ilatmin:ilatmax,ilonmin:ilonmax],alpha=0.5)
plt.colorbar()
plt.pcolormesh(diff2[ilatmin:ilatmax,ilonmin:ilonmax],alpha=0.5)
plt.title('mask2 - mask1')
plt.savefig(fileout7)


# Create new glob mask (1 pixel to modify)
if modif==1:
	# create lon, lat vectors
	lonmin=-180
	lonmax=179.5
	latmin=-78
	latmax=80
	dlon=0.5
	dlat = 0.5
	lon1 = np.arange(lonmin,lonmax+dlon,dlon)
	lat1 = np.arange(latmin,latmax+dlat,dlat)
	[lon,lat] = np.meshgrid(lon1,lat1)

	#print "shape(lon):", np.shape(lon)

	# in the zoom part, determine which pixels have changed
	indices = [ i for i in range(np.shape(idiff)[1]) if lon1[idiff[1][i]]>lonminzoom and lon1[idiff[1][i]]<lonmaxzoom and lat1[idiff[0][i]]>latminzoom and lat1[idiff[0][i]]<latmaxzoom]
	print "type(indices):", type(indices)
	print "shape(indices):", np.shape(indices)
	print "indices:", indices
	indx = [idiff[0][i] for i in indices]
	#print "type(indx):", type(indx)
	print "shape(indx):", np.shape(indx)
	indy = [idiff[1][i] for i in indices]
	print "shape(indy):", np.shape(indy)
	print "indx:", indx
	print "indy:", indy

	# indx is the position of the item in the latitude vector to switch from 0 to 1
	# indy is the position of the item in the longitude vector to switch from 0 to 1

	new_mask = np.copy(mask2)
	new_mask[indx,indy] = mask1[indx,indy]
	new_mask2 = np.ma.array(new_mask, mask=False)
	new_mask2.mask[indx,indy] = True

	#
	# Save new_mask in file
	#
	np.savetxt('/export/home/data/GRIDGEN/PYTHON/new/glob_30m.mask.new', new_mask, delimiter='  ', newline=' \n ', fmt='%i')

	fig = plt.figure(8)
	fileout='/export/home/data/GRIDGEN/PYTHON/'+mod+'_new_mask_zoom.png'
	plt.pcolormesh(new_mask[ilatmin:ilatmax,ilonmin:ilonmax], alpha=0.5)
	plt.colorbar()
	plt.plot(new_mask[indx,indy],'+')
	plt.savefig(fileout)

