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

mod = fullfile2.split('.')[-3].split('/')[-1]
print "mod:", mod

bot1 = np.loadtxt(fullfile1)
bot12 = np.ma.masked_array(bot1, bot1>10)
bot2 = np.loadtxt(fullfile2)
bot22 = np.ma.masked_array(bot2, bot2>10)

print "shape(bot1):", np.shape(bot1)
#print "shape(bot2):", np.shape(bot2)


fig = plt.figure(1)
fileout1 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_bot1.png'
plt.pcolormesh(bot12)
plt.colorbar()
plt.savefig(fileout1)

fig = plt.figure(2)
fileout2 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_bot2.png'
plt.pcolormesh(bot22)
plt.colorbar()
plt.savefig(fileout2)

# compute difference
diff=bot22-bot12
#print "type(diff):", type(diff)

fig = plt.figure(3)
fileout3 = '/export/home/data/GRIDGEN/PYTHON/'+mod+'_diff_bot.png'
plt.pcolormesh(diff)
plt.colorbar()
plt.title('bot2 - bot1')
plt.savefig(fileout3)

