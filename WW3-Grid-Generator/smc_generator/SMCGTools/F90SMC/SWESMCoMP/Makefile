## Makefile created to compile the dynamic SWEs model on  
## SMC grid for different tests.    JGLi22Jul2022
## Syntax:  make -f Makefile 
##

#FC = ftn
#FCFLAGS = -e Z -h noacc
 FC = gfortran
 FCFLAGS = -fdefault-real-8 -fopenmp 
#FC = ifort
#FCFLAGS = -r8 
CPPFLAGS= 

SWEsnSMCeP: SWEsCnstMD.o  SWEsInitMD.o  SWEsDynaMD.o  SWEsnSMCPM.o 
	@ echo "Linking $@ $^"
	$(FC) $(FCFLAGS) -o $@ $^

SWEsCnstMD.o: SWEsCnstMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c SWEsCnstMD.f90

SWEsInitMD.o: SWEsCnstMD.o SWEsInitMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c SWEsInitMD.f90

SWEsDynaMD.o: SWEsCnstMD.o SWEsDynaMD.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c SWEsDynaMD.f90

SWEsnSMCPM.o: SWEsCnstMD.o SWEsInitMD.o SWEsDynaMD.o SWEsnSMCPM.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c SWEsnSMCPM.f90

%.o: %.F90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c $<

%.o: %.f90
	@ echo "Compiling $<"
	$(FC) $(FCFLAGS) $(CPPFLAGS) -c $<

clean:
	@ echo "Cleaning up ..."
	rm -f *.o *.mod 

