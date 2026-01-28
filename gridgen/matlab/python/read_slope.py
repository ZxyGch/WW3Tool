#!/usr/bin/python
# -*-coding:Utf-8 -*

# Read bottom

import numpy as np
import sys, os
import matplotlib.pyplot as plt
import math

#filedir = sys.argv[1]

#fullfile= filedir + '/africa_10m.depth_ascii'
fullfile = sys.argv[1]

workdir = os.path.dirname(fullfile)
workdir = os.path.dirname(workdir)
print "workdir:", workdir
mod = fullfile.split('.')[-2].split('/')[-1]
print "mod:", mod

slope = np.loadtxt(fullfile)
new_slope = np.copy(slope)

print "type(slope)", type(slope)
print "shape(slope):", np.shape(slope)

diff= np.where(np.isnan(slope))
difflist=zip(diff[0],diff[1])
print "type(diff):", type(diff)
print "shape(diff):", np.shape(diff)
print "diff[0]:", diff[0]
print "diff[1]:", diff[1]

print ""
print "diff:", diff

for ix,iy in difflist:
	print "***** ix,iy:", ix, iy, " *****"
#	print "slope[ix,iy]:", slope[ix,iy]
#	print "slope[ix-1,iy]:", slope[ix-1,iy]
#	print "slope[ix+1,iy]:", slope[ix+1,iy]
#	print "slope[ix,iy-1]:", slope[ix,iy-1]
#	print "slope[ix,iy+1]:", slope[ix,iy+1]
	neighbours=np.zeros((4,))
#	print "shape(neighbours):", np.shape(neighbours)
	neighbours[0]=slope[ix-1,iy]
	neighbours[1]=slope[ix+1,iy]
	neighbours[2]=slope[ix,iy-1]
	neighbours[3]=slope[ix,iy+1]
#	print 'OK'
	print "neighbours:", neighbours
	weights=np.zeros((4,))
	weights[:]=np.where(np.isnan(neighbours[:]),0,1)
	neighbours[:]=np.where(np.isnan(neighbours[:]),0,neighbours[:])
	count = np.sum(weights[:])
	print "neighbours:", neighbours
	print "weihgts:   ", weights
	print "count:", count
	slope_tmp = np.sum(np.multiply(neighbours[:],weights[:]))/count
	new_slope[ix,iy] = int(np.round(slope_tmp,decimals=0))
	print "new_slope[ix,iy]:", new_slope[ix,iy]


#
# Save new slope
#
np.savetxt(workdir+'/new/'+mod+'.slope.new', new_slope, delimiter='  ', newline=' \n ',fmt='%i')

fig = plt.figure(1)
fileout1 = workdir+'/'+mod+'_slope.png'
plt.pcolormesh(slope[0:50,:],vmin=0.05, vmax=10000)
plt.colorbar()
plt.plot(diff[1],diff[0], 'g+')
plt.savefig(fileout1)

slope2 = np.ma.masked_array(slope, slope==float('NaN'))
fig = plt.figure(2)
fileout2 = workdir+'/'+mod+'_slope_no-nan.png'
plt.pcolormesh(slope2)
plt.colorbar()
plt.savefig(fileout2)


slope3= np.ma.masked_invalid(slope)
fig = plt.figure(3)
fileout3 = workdir+'/'+mod+'_slope_3.png'
plt.pcolormesh(slope3)
plt.colorbar()
plt.savefig(fileout3)


slope4 = np.where(np.isnan(slope),np.ones(np.shape(slope)),np.zeros(np.shape(slope)))
print "shape(slope4):", np.shape(slope4)
fig = plt.figure(4)
fileout4 = workdir+'/'+mod+'_slope_4.png'
plt.pcolormesh(slope4)
plt.colorbar()
plt.savefig(fileout4)


maxslope = np.amax(slope)
maxnonan = np.nanmax(slope)
minnonan = np.nanmin(slope)

print "max value in slope:", maxslope
print "max value in slope (except NaN):", maxnonan
print "min  value in slope (except NaN):", minnonan
