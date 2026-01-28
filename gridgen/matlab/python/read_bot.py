#!/usr/bin/python
# -*-coding:Utf-8 -*

# Read bottom

import numpy as np
import sys, os
import matplotlib.pyplot as plt


fullfile = sys.argv[1]
mod = fullfile.split('.')[-2].split('/')[-1]
print("mod:", mod)

workdir = os.path.dirname(fullfile)
workdir = os.path.dirname(workdir)
print("workdir:", workdir)

bot = np.loadtxt(fullfile)

print("type(bot):", type(bot))
print("shape(bot):", np.shape(bot))


bot2 = np.ma.masked_array(bot, bot>10)

fig = plt.figure(1)
fileout = workdir+'/'+mod+'_dpt.png'
plt.pcolormesh(bot2)
plt.colorbar()
plt.savefig(fileout)
