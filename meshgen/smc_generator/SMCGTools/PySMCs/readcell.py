"""
Read SMC grid cell arrays from text files.

Function readcell(filestring_list) reads the cell file specified by
each filestring, which includes path/file_name.

If Arctic cell file is also needed, the filestring will be a
list of both global and Arctic cell files.  It will merge the 
two parts together and return a merged header lines.

It could read more than 2 cell array files if needed.

The main() function demonstrates how the readcell could be called
as a stand alone function and merge the Arctic part manually.

Use Numpy genfromtxt to read cell array.  JGLi26Feb2025

First created:              JGLi18Feb2019 
Last modified:              JGLi26Feb2025 

"""

##  Input celfiles as a list even if there is only one file.
##  For instance celfiles=['path/celfile.dat', 'path/arcfile.dat']
def readcell(celfiles):
    import numpy  as np
    
    nfls = 0 
    for celfile in celfiles:
        print( " Read cel from ", celfile)
        archd=open(celfile, 'r') 
        hdlin=archd.readline()
        archd.close()
         

##  Read the cell array as Numpy integers but skip first count line.
        celin=np.genfromtxt(celfile, dtype=int, skip_header=1)
        nfls += 1

        if( nfls <= 1):
            headrs = [ hdlin ]
            cel = celin.copy()
        else:
            headrs.append( hdlin )
            cel = np.vstack( (cel, celin) )
        
    return headrs, cel

##  End of readcell function.

## 
def main():

    import numpy  as np

    cellfile = input(" Please enter the cell file as 'path/file.dat' > ")
    
    Arctic = input(" Is there an Arctic part cell file? 'Yes' or 'No' > ")
    if Arctic.strip()[0] == 'Y':
        Arcfile = input(" Please enter the Arctic part cell file > ")
        cellfiles = [ cellfile, Arcfile ]
        hdr, cel = readcell( cellfiles )
        ng = int( headrs[0].split()[0] )
        na = int( headrs[1].split()[0] )
        nc = ng + na
    else:
        hdr, cel = readcell( [ cellfile ] )
        nc = int( headrs.split()[0] )

    print( "Total number of cells nc =", nc)
    print( "First cell array is ", cel[0,:])
    print( " Last cell array is ", cel[nc-1,:])

##  End of main() function.

if __name__ == '__main__':
    main()

