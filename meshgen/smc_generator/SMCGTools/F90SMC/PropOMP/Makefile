## Makefile created to compile the spectral propagation test
## program.  Options are special for this program  as it is 
## too large for normal compilation.   JGLi18Dec2017
## Syntax:  make -f Makefile 
##

FC = gfortran
FCFLAGS = -fdefault-real-8 -fopenmp
#FC = ifort
#FCFLAGS = -r8 -qopenmp -mcmodel medium -shared-intel -integer-size 64 
#FCFLAGS = -r8 -qopenmp -mcmodel medium -shared-intel -integer-size 64 -check bounds
CPPFLAGS= 


SMCGProp: Constants.o  W3DispMD.o  W3PSMCMD.o  SMCGPropMP.o 
	@ echo "Linking $@ $^"
	$(FC) $(FCFLAGS) -o $@ $^

Constants.o: Constants.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c Constants.f90

W3DispMD.o: Constants.o W3DispMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c W3DispMD.f90

W3PSMCMD.o: Constants.o W3PSMCMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c W3PSMCMD.f90

SMCGPropMP.o: Constants.o W3DispMD.o W3PSMCMD.o SMCGPropMP.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c SMCGPropMP.f90 

%.o: %.F90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c $<

%.o: %.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c $<

clean:
	@ echo "Cleaning up ..."
	rm -f *.o *.mod 

