"""
Read data arrays from a tabled text file. Missing values in the
table will be filled as none.

Function readftxt(filestring) read the cell file specified by
the filestring, which includes path/file_name.txt

The main() function demonstration how the readftxt could be called
as a stand alone function.

Modified to use numpy.genfromtext function and flexible way to 
skip given number of lines or none at all.  JGLi10Feb2020

First created:       JGLi18Feb2019 
Last modified:       JGLi03Apr2024

"""

##  Lines to be skipped are defined by skiprows, default 1 line.
##  If skiprows=0 is specfied, no line will be skipped.
##  If skiprows=n(>1) is gien, total of n lines will be skipped
##  but only the last skipped line is returned as a list.

def readftxt(textfile, dtype=float, skiprows=1):
    """  
    Read tabled data from a text file.  Skip 1 header line or more 
    if named variable skiprows is provided.  Default data type float.
    """

    import numpy  as np

    print (" Read table from ", textfile)
##  Read header line if skiprows > 0
    if( skiprows > 0 ):
        archd=open(textfile, 'r') 
##  Assume last line in skiprows contains the header parameters.
        for i in range(skiprows):
            hdrskp=archd.readline()

##  Split the last one of skipped lines as header parameters.
        hdlist = hdrskp.split()
        archd.close()
    else:
        hdlist = ' '

##  Read the table file but skip the specified rows.
    table=np.genfromtxt(textfile, dtype=dtype, skip_header=skiprows)

    return hdlist, table

def main():

    import numpy  as np

    textfile = input(" Please enter the text file as 'path/file.dat' > ")
    skiprows = input(" Please enter how many header lines to skip' > ")
    skipped = int(skiprows)
    hdr, fdat = readftxt( textfile, dtype=float, skiprows=skipped )

##  readtext returns a default float values so integer needs a conversion.
#   cel = np.array(fdat).astype(np.int)
    nlns = len(fdat[:,0])

    print ("Last header line is ", hdr)
    print ("Total lines in cels ", nlns)
    print ("First text line is ", fdat[0,:])
    print (" Last text line is ", fdat[nlns-1,:])

if __name__ == '__main__':
    main()

