"""
Function readtext(filestring) read the text data file specified by
the filestring, which includes path/file_name.txt

Missing values in the table will be filled as none.

The main() function demonstration how the readtext could be called
as a stand alone function.

First created:      JGLi18Feb2019 
Last modified:      JGLi06Mar2025 

"""

##  Assume to skip the first line [0]. If more than one
##  lines to skip, specifiy the line indexes in the
##  parameter list skiprows=[0,1], for first two lines.
##  But only the last skipped line is returned as a list.

def readtext(textfile, skiprows=[0]):
    import numpy  as np
    import pandas as pd

    archd=open(textfile, 'r') 
##  Assume last line in skiprows contains the header parameters.
    for i in range(len(skiprows)):
        hdrskp=archd.readline()

##  Split the last one of skipped lines as header parameters.
    hdlist = hdrskp.split()
    archd.close()

    print (" Reading", textfile, str(hdlist[0]) )

    arcel=pd.read_csv(textfile, sep='\s+',skiprows=skiprows,header=None)
    table=arcel.values

    return hdlist, table

def main():

    import numpy  as np
    import pandas as pd

    textfile = input(" Please enter the cell file as 'path/file.dat' > ")
#   textfile='./G50SMCels.dat'
    hdr, dat = readtext( textfile )

    print ("Header line contains", hdr )
    print ("First data line is ", dat[ 0,:])
    print (" Last data line is ", dat[-1,:])

if __name__ == '__main__':
    main()

