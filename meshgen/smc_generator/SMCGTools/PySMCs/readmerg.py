"""
##  Read a text file and merge all lines into a string.
##
##  First created:  JGLi06Apr2020
##  Last modified:  JGLi20Apr2023
##
"""

def readmerg(inpfile, KeepNewline=True):
    """ Read a text file line by line until the end and merge into a string.
    """ 
    vary = ''
    with open( inpfile, 'r' ) as flhdl:
        nxline = flhdl.readline()
        while ( len(nxline) > 1 ):
            if( KeepNewline ):
                vary = vary + nxline 
##  To remove the last Newline character, set KeepNewline=False for 
##  a single line string vary.    JGLi20Apr2023 
            else:
                vary = vary + nxline[0:-1]   

            nxline = flhdl.readline()

    return vary

##  End of readmerg function.


def main():

    Newfile = input(' *** Please enter your file name > ')
    Newline = input(' *** Do you like to keep Newline? Y/N > ')
    if( Newline.lower() == 'y' ): Lines=True
    else:                         Lines=False 

    vary = readmerg( Newfile, KeepNewline=Lines )
    print(" Read done for file ", Newfile )
    print( vary )
    print( eval(vary) )

##  End of main().

if __name__ == '__main__':
    main()

##  End of readmerg.py program. 


