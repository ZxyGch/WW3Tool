## Makefile created to compile the spectral propagation model 
## for hybrid parallelization test on Cray X40.   JGLi18Aug2019
## Syntax:  make -f Makefile 
##

FC = ftn
FCFLAGS = -e Z -h noacc 
CPPFLAGS= 

SMCPropW3M: Constants.o  W3DispMD.o  W3MPInitMD.o  W3PSMCMD.o  SMCPropWW3Hyb.o 
	@ echo "Linking $@ $^"
	$(FC) $(FCFLAGS) -o $@ $^

Constants.o: Constants.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c Constants.f90

W3DispMD.o: Constants.o W3DispMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c W3DispMD.f90

W3MPInitMD.o: Constants.o W3MPInitMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c W3MPInitMD.f90

W3PSMCMD.o: Constants.o W3PSMCMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c W3PSMCMD.f90

SMCPropWW3Hyb.o: Constants.o W3DispMD.o W3MPInitMD.o W3PSMCMD.o SMCPropWW3Hyb.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c SMCPropWW3Hyb.f90

%.o: %.F90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c $<

%.o: %.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c $<

clean:
	@ echo "Cleaning up ..."
	rm -f *.o *.i *.mod 

