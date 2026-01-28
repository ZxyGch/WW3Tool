%%  FORTRAN_NAMELIST v1.0 Readme File
%   Written by: S. Lazerson (lazerson@pppl.gov)
%   Date:   02/03/2011 

%%  Installation Instructions
%   After extracting the contents of the FORTRAN_NAMELISTv1.0.zip file you 
%   should have a FORTRAN_NAMELIST directory and this file.  This file will
%   walk you through using the FORTRAN_NAMELIST routines.  In order to 
%   effectively use these routines they'll need to be added to your 'path'.  
%
%   1) Move the FORTRAN_NAMELIST directory to a more permanent location.
%   2) Under the menu 'File' select 'Set path'.  Now select the add with
%      subfolders and select the FORTRAN_NAMELIST directory.
%
%   Now the FORTRAN_NAMELIST routines can be called from any working 
%   directory.

%%  Reading a FORTRAN Namelist file
%   A fortran namelist is a text file containing varialbe names and values.
%   It attempts to automate the data input process for programs written in
%   FORTRAN.  The read_namelist function pulls the variables and their
%   values out of a text file into a MATLAB structure.  Namelists are
%   always specified with a name.  This way multiple namelists can be
%   placed in one text file.  Here is an example:
%
%   INDATA&
%   var1 = 100.
%   var2 = 200.
%   array1 = 1 2 3 4 5
%   array2(1) = 5.0
%   array2(2) = 6.9
%   array2(3) = 2.7
%   \
%   OTHERSTUFF&
%   vara = 2.0E-05  2.5E-06 -4.5E+03
%   varb = 5
%   \
%
%   In this example there are two namelists (INDATA and OTHERSTUFF).  The
%   read_namelist function requires that you specify the filename and the
%   specific namelist you wish to extract.  For example:
    indata=read_namelist('test.txt','INDATA');
    otherstuff=read_namelist('test.txt','OTHERSTUFF');
%   Note we can also pass a file id number instead.
    fid = fopen('test.txt','r');
    indata = read_namelist(fid,'INDATA');
    fclose(fid);
%   Each variable is stored as a field of the returned array.  Please note
%   that at this time read_namelist does not support the colon feature for
%   array indexing in the namelist variables specified like
%   var(5,:)= 4.0 3.1 2.6
%   will be ignored.

%%  Writing a FORTRAN Namelist file
%   A fortran namelist is a text file.  The included functions automate the
%   usage of fprintf to output variables to a fortran input namelist.  In
%   all cases the user must still open a file for writing, use the
%   appropriate output functions, and then close the file.  For example to
%   place the 'INDATA' namelist in the file test.txt:
%
    var1=100;
    var2=200;
    array1=1:5;
    array2=[5.0 6.9 2.7];
    fid=fopen('test.txt','w');
    fprintf(fid,'%s\n','&INDATA');
    write_namelist_flt(fid,'VAR1',var1);
    write_namelist_flt(fid,'VAR2',var2);
    write_namelist_vec(fid,'ARRAY1',array1,'int');
    write_namelist_arr(fid,'ARRAY2',array2);
    fprintf(fid,'%s\n\n','/');
    fclose(fid);
%   Use the help command on the various routine to better understand how to
%   use them.