#!/usr/bin/python
# -*-coding:Utf-8 -*

# Read bottom

import numpy as np
import sys, os
import matplotlib.pyplot as plt

fullfile = sys.argv[1]

mod = fullfile.split('.')[-2].split('/')[-1]
print "mod:", mod

workdir = os.path.dirname(fullfile)
workdir = os.path.dirname(workdir)
print "workdir:", workdir

mask = np.loadtxt(fullfile)

print "type(mask):", type(mask)
print "shape(mask):", np.shape(mask)



fig = plt.figure(1)
fileout = workdir+'/'+mod+'_mask.png'
plt.pcolormesh(mask)
plt.colorbar()
plt.savefig(fileout)
