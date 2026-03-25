!!
!!  FORTRAN 90 propagation model for testing of SMC grid face arrays.
!!  For single or two cores computer with OpenMP parallelization.  
!! 
!!  First created:        JGLi26Nov2008
!!  Last modified:        JGLi05Feb2025
!!

      PROGRAM SMCPropMP
       USE omp_lib
       USE constants
       USE W3PSMCMD 

       IMPLICIT NONE

       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST8
       REAL (Kind=8) :: TM1, TM2

! Check command arguments.
!      II = COMMAND_ARGUMENT_COUNT()
!      IF( II < 1 )THEN
!         WRITE(*,*)' *** ERROR, SMCGSide input file should be provided. ***'
!         STOP
!      ELSE
!         WRITE(*,*)' Number of argument = ', II
!      ENDIF

! Get InpFile name from argument 
!      CALL GET_COMMAND_ARGUMENT(1, InpFile, Status=K)
!      WRITE(*,*) " *** InpFile is ",  TRIM(InpFile)

! Open input file and read grid parameters.
       OPEN(UNIT=8,FILE= './PropInput.txt',STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,InpFile//' was not opened! '

          READ(8,*)   GridName
         WRITE(6,*)   GridName
          READ(8,*)   DataPath
         WRITE(6,*)   DataPath
          READ(8,*)   NCL,  NFC,  MRL 
         WRITE(6,*)   NCL,  NFC,  MRL 
          READ(8,*)   NLon, NLat, NPol
         WRITE(6,*)   NLon, NLat, NPol
          READ(8,*)   NDir, NFrq, NTS, NWP
         WRITE(6,*)   NDir, NFrq, NTS, NWP
          READ(8,*)   ZLon, ZLat, DLon, DLat
         WRITE(6,*)   ZLon, ZLat, DLon, DLat
          READ(8,*)   DTG,  DTCFL 
         WRITE(6,*)   DTG,  DTCFL 
          READ(8,*)   SSLat,SNLat
         WRITE(6,*)   SSLat,SNLat 
          READ(8,*)   Arctic
         WRITE(6,*)   Arctic

       CLOSE(8)

!! Allocate cell and face arrays.
       ALLOCATE( ICE(4,-9:NCL), ISD(1:7,NFC), JSD(1:7,NFC), KG(NCL) ) 
       ALLOCATE( NRLCel(0:MRL), NRLUFc(0:MRL), NRLVFc(0:MRL) )

!! Read Global and Arctic part Multiple-Cell info
       CALL READCELL

!! Allocate grid related variables.
       ALLOCATE( CLats(-9:NC), CTHG0S(-9:NC), RCELA(-9:NC), CLatF(NV) )

!!  Evaluate cell centre and V-face latitude cosine
          CNST=0.5*DLAT
!$OMP Parallel DO Private(CNST2)
       DO n=1, NC-NPol
          CNST2=Real( 2*ICE(2,n)+ICE(4,n) )*CNST + ZLat
          CLats(n)=COS(  CNST2*D2RAD )
          CTHG0S(n)= - TAN( CNST2*D2RAD ) / REARTH
       ENDDO
!$OMP END Parallel DO

!$OMP Parallel DO Private(CNST3)
       DO j=1, NV
          CNST3=Real( JSD(2,j) )*DLat + ZLat
          CLatF(j)=COS( CNST3*D2RAD )
       ENDDO
!$OMP END Parallel DO
     
!!  Define cell area for cell update
       DX0=DLON*D2RAD
       DY=DLAT*D2RAD
       DYR=1.0/DY

       IF( NPol .GT. 0 ) THEN 
!!  Polar cells are round cell of radius R=PCRDY*DY*ICE(4,NNor)
!!  The RCELA(NC) represent the net V-flux factor for the polar cell.
!!  Net V-flux are all divided by the CLats factor for cell update
!!  but it is not needed for polar cell.  To avoid zero-dividing 
!!  polar cell CLats values are evaluated at cell edge rather than centre 
!!  and are set equal for south polar cell if any. 
!!  Add polar cell GCT factor CTHG0S though it will be overwritten in sub ArctAngd.
          CNST2=Real( ICE(2,NNor) )*DLat + ZLat
          CLats(NNor)=COS(  CNST2*D2RAD )
          CNST1=Real(ICE(4,NNor))*DY*PCRDY
          CNST2=Pie*CNST1*CNST1
          RCELA(NNor)=DX0*DY*CLats(NNor)/CNST2 
          CTHG0S(NNor)= 0.0 
!!  Double the polar cell dj if PCRDY = 1.0.   JGLi15Mar2023
          IF( PCRDY .GT. 0.9 ) ICE(4,NNor) = 2*ICE(4,NNor)
       ENDIF
!!  Duplicate north polar cell area for south polar cell if NPol = 2
       IF( NPol .GT. 1 ) THEN
          CLats(NSou)= CLats(NNor)
          RCELA(NSou)= RCELA(NNor)
          CTHG0S(NSou)= 0.0 
!!  Double the polar cell dj if PCRDY = 1.0.   JGLi15Mar2023
          IF( PCRDY .GT. 0.9 ) ICE(4,NSou) = 2*ICE(4,NSou)
       ENDIF

!!   Duplicated ICE3/4 elements.  JGLi26Aug2021
       ALLOCATE( ICE3(-9:NCL), ICE4(-9:NCL) )
       ICE3(:)=ICE(3,:)
       ICE4(:)=ICE(4,:)

!!   Evaluate other cell dx length in rad and cell area in rad**2
!!   except for the polar cell(s).
!$OMP Parallel DO
       DO L=-9, NC-NPol
          RCELA(L)=1.0/REAL( ICE3(L)*ICE4(L) )
       ENDDO
!$OMP END Parallel DO

!! Allocate direction related variables.
       ND = NDir
       ALLOCATE( Theta(ND),ESIN(ND),ECOS(ND),EC2(ND),ES2(ND),ESC(ND) )

!!  Directional bins in rad, shifted by half-width from axises
       DThta=2.0*Pie/REAL(NDIR)
       DO K=1, NDIR
         Theta(K)=(REAL(K) - 0.5)*DThta
         ECOS(K)=COS(Theta(K))
         ESIN(K)=SIN(Theta(K))
         EC2(K) = ECOS(K)**2
         ES2(K) = ESIN(K)**2
         ESC(K) = ECOS(K)*ESIN(K)
       ENDDO

!!   Allocate frequency and depth related variables.
       ALLOCATE( SIG(0:NFrq+1), DSIP(0:NFrq+1), SpecPM(0:NFrq+1) )
       ALLOCATE( HCel(-9:NC), DHDX(-9:NC), DHDY(-9:NC) )
       ALLOCATE( CGrp(0:NFrq+1,-9:NC), REFR(0:NFrq+1,-9:NC),  &
                   Wnmk(0:NFrq+1,-9:NC), DHLMT(NDir,NC) )

!!  Set up frequency bands and work out wave number and group speed
       WRITE(6,*)  " Set up frequency bands ..." 
       CALL SgmCgWnK

!!  Multiple factor for multi-resolution loops
        MRFct=2**(MRL - 1)
        WRITE(6,*) ' Multi-Resolution level and factor=', MRL, MRFct

!!  Some duplicated variables for WW3 model
        SX = DLon*MRFct
        SY = DLat*MRFct
        NSEA = NC
        NSpc = NDir*NFrq
      
!!  Specify run start time step and writeup interval
        NS =  0
        NHr=INT(3600.0/DTG)

        IF( Arctic )  THEN 
!! Allocate and calculate Arctic cell rotation boundary arrays.
            ALLOCATE( AngArc(NArc), MBGlo(NGLB), MBArc(NArB) )
            CALL ArctAngd
        ENDIF

!! Allocate and initialise spectral array WSpc(NDir,NFrq,NC)
        ALLOCATE( WSpc(NDir,NFrq,NC) )
        WSpc = 0.0

!  Initialise wave spectra and bin velocities,
!  including GCT and refraction Courant numbers.
        WRITE(6,*) ' Initializing wave spectra ... '
        CALL SPECUUVV

!! Allocate HS variable and save the initial SWH.
        ALLOCATE( HS(NC) ) 
        CALL WRITESWH( NS )

!!  Calculate bathymetry gradient DHDX/DY and refraction coefficient.
        WRITE(6,*) " Calculating DHDX/Y ... "
        CALL SMCDHXY 

!!  Read current velocity and calculate gradients if available.
        IF ( FLCUR ) THEN
           ALLOCATE( CX(NC), CY(NC), DCXDX(NC), DCXDY(NC),  &
                                     DCYDX(NC), DCYDY(NC) )
           CALL READCURNT(NS)
           CALL SMCDCXY
        ENDIF

!    Define cell and face sub-step counts.  JGLi18Jan2012
         NRLCel(0)=0
         NRLUFc(0)=0
         NRLVFc(0)=0
         DO i=1,MRL-1
         NRLCel(i)=NRLCel(i)+NRLCel(i-1)
         NRLUFc(i)=NRLUFc(i)+NRLUFc(i-1)
         NRLVFc(i)=NRLVFc(i)+NRLVFc(i-1)
         ENDDO
         NRLCel(MRL)=NC
         NRLUFc(MRL)=NU
         NRLVFc(MRL)=NV
         
!     Open files to store writups
       OPEN(UNIT=16,FILE=TRIM(Tempath)//'CMesgs.txt',STATUS='UNKNOWN', &
            IOSTAT=nn, ACTION='WRITE')
       IF(nn /= 0) PRINT*,' File CMesgs.txt was not opened! '

!     Header messages and configuration information 
       WRITE(UNIT=16,FMT='(1x/   &
        &  "  Global Multiple-Cell 2-D Spherical Advection Model" /    &
        &  "         SMC Version 2.0   J G  Li  Mar 2010  " /)' )

       CALL DATE_AND_TIME(CDate, CTime)
       WRITE(UNIT=16,FMT="(1x,' Run time date ',A10,2x,A10)") CTime, CDate

       WRITE(UNIT=16,FMT='(1x," Size-1 Units DLON DLAT = ",2f14.10)')  DLON, DLAT
       WRITE(UNIT=16,FMT='(1x," Equatorial PoLat PoLon = ",2f8.2)')  PoLat, PoLon
       WRITE(UNIT=16,FMT='(1x," Standard grid ZrLatLon = ",2f9.5)')  ZLat, ZLon
       WRITE(UNIT=16,FMT='(1x," Global time step DTG s = ",f8.1)' )  DTG
       WRITE(UNIT=16,FMT='(1x," CFL limited step DTCFL = ",f8.1)' )  DTCFL
       WRITE(UNIT=16,FMT='(1x," Swell age diffusion  s = ",f8.1)' )  DTME
       WRITE(UNIT=16,FMT='(1x," Initial integrated SWH = ",f8.3)' )  SWH0
       WRITE(UNIT=16,FMT='(1x," Init Wave Peak Freqncy = ",f8.4)' )  PkFrq
       WRITE(UNIT=16,FMT='(1x," Initial integrated SWH = ",f8.3)' )  SWH0
       WRITE(UNIT=16,FMT='(1x," Nos. of Dirs and Frqcy = ",2i8)' ) NDir, NFrq
       WRITE(UNIT=16,FMT='(1x," Start & Total timestes = ",2i8)' ) NS, NTS
       WRITE(UNIT=16,FMT='(1x," Writeup steps and  NHr = ",2i8)' ) NWP, NHr
       WRITE(UNIT=16,FMT='(1x," Multi-reso levl factor = ",2i8)')  MRL, MRFct
       WRITE(UNIT=16,FMT='(1x," Horizontal cell number = ",2i8)')  NC, NCL
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic cell No.s = ",2i8)')  NGLo, NArc
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic bndy No.s = ",2i8)')  NGLB, NArB
       WRITE(UNIT=16,FMT='(1x," Total number of U-face = ",2i8)')  NU, NFC
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic U-face No = ",2i8)')  NUGL, NUAr
       WRITE(UNIT=16,FMT='(1x," Total number of V-face = ",2i8)')  NV, NFC
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic V-face No = ",2i8)')  NVGL, NVAr
       WRITE(UNIT=16,FMT='("Sub-step cell count NRLCel(0:MRL)=",6i8)') NRLCel
       WRITE(UNIT=16,FMT='("Sub-step Ufce count NRLUFc(0:MRL)=",6i8)') NRLUFc
       WRITE(UNIT=16,FMT='("Sub-step Vfce count NRLVFc(0:MRL)=",6i8)') NRLVFc

 3912 FORMAT(1x,i4,3F9.1,ES12.3)

       WRITE(16,FMT='(/1x," Frequency 0:NFrq+1 in Hz")' )
       WRITE(16,FMT='((10F8.5))')  (0.5*Sig(k)/Pie,k=0,NFrq+1)
       WRITE(16,FMT='(/1x," Initial PM frequency factor")' )
       WRITE(16,FMT='((10F8.5))')  (SpecPM(k),k=0,NFrq+1)
       WRITE(16,FMT='(/1x," First and last ICE values ")' ) 
       WRITE(16,FMT='(1x,6i8)')  1,(ICE(i, 1),i=1,5)
       WRITE(16,FMT='(1x,6i8)') NC,(ICE(i,NC),i=1,5)
       WRITE(16,FMT='(/1x," First and last ISD values ")' ) 
       WRITE(16,FMT='(1x,8i8)')  1,(ISD(i, 1),i=1,7)
       WRITE(16,FMT='(1x,8i8)') NU,(ISD(i,NU),i=1,7)
       WRITE(16,FMT='(/1x," First and last JSD values ")' ) 
       WRITE(16,FMT='(1x,9i8)')  1,(JSD(i, 1),i=1,8)
       WRITE(16,FMT='(1x,9i8)') NV,(JSD(i,NV),i=1,8)
       WRITE(16,FMT='(1x,8i8)') 

       CALL DATE_AND_TIME(CDate, CTime)
       WRITE(6,"(' Loop start time ',A,'  ',A)")  CTime

!$     TM1= OMP_GET_WTIME()
!$OMP Parallel  Private(i, j, m, n)
!$    i=omp_get_thread_num()
!$    j=omp_get_num_procs()
!$    m=omp_get_max_threads()
!$    n=omp_get_num_threads()
!$    IF(i .LE. 1) THEN 
!$       WRITE( 6,*) "Num_Threads to be used =", n, m, j, i 
!$       WRITE(16,*) "Num_Threads to be used =", n, m, j, i
!$    ENDIF
!$OMP END Parallel

!     Start of major time step loop
 TSLoop:  DO  NT=NS, NS+NTS

!!    Space propagation for every spectral component.
       IF ( FLCXY ) THEN

  FrqLop:  DO  NF=1, NFrq
  DirLop:  DO  ND=1, NDir

!!    Propagation for the given spectral component
         CALL W3PSMC( ND, NF, NT, WSpc(ND,NF,:) )           

!!    End of directional and frequency bin loops
           ENDDO  DirLop
           ENDDO  FrqLop

!!    End of spatial propagation FLCXY block.
       ENDIF 

!!    Refraction part for every cell except for polar cell(s).
       IF ( FLCTH .OR. FLCK ) THEN

!!    Great circle turning (GCT) for lower part cells at 4 times of substeps,
!!    Extended to include Arctic part if any
!      CALL GMCGtCrTn(1, NC, MRFct)
           CALL W3KRTN( NT )

!!    End of refraction FLCTH or FLCK block.
       ENDIF 


!!    Update boundary cells after proper rotation if Arctic part is
!!    included. 
       IF( Arctic ) THEN

!!    Arctic cells for global boundary cells
       DO i=1,NGLB
          ii=i+NGLA
          kk=MBGLo(i)
          DO j=1,NFrq

!!   Rotate the Arctic spectra by -AnglD before assigning to the lower part
!!   Note that it is equivalent to rotated the directional bins by AnglD.
          Spectr=WSpc(1:NDir,j,kk)
          Alpha=  AngArc(kk-NGLo)

          CALL Specturn( NDir, 1, Alpha, Spectr )

          WSpc(1:NDir,j,ii)=Spectr

          ENDDO
       ENDDO

!!    Global cells for Arctic boundary cells
       DO i=1,NArB
          kk=MBArc(i)
          DO j=1,NFrq

!!   Rotate the lower part spectra by AnglD before assigning to the Arctic part
!!   Or turn the directional bins by -AnglD.   21 Jul 2009
          Spectr=WSpc(1:NDir,j,kk)
!!   Note only the Arctic cells are assigned the AngArc value
          Alpha= -AngArc(i)

          CALL Specturn( NDir, 1, Alpha, Spectr )

          WSpc(1:NDir,j,i+NGLo)=Spectr

          ENDDO
       ENDDO

!!   End of updating boundary cells IF( Arctic ). 
       ENDIF


!  Output tracer concentration if at selected writeup time steps
       IF( (NT+1 .LT. 10*NWP .AND. MOD(NT+1,NWP/2) .eq. 0) .OR.    &
      &    (MOD(NT+1,NWP) .eq. 0) )  THEN
           CALL WRITESWH( NT+1 )
       ENDIF

!!  End of time step loop
      ENDDO  TSLoop

       CALL DATE_AND_TIME(CDate, CTime)
       WRITE(6,"(' Loop ended time ',A,'  ',A)")  CTime

!$     TM2= OMP_GET_WTIME()
!$     WRITE(UNIT= 6,FMT='(1x," Total loop time (s) = ",ES16.5)' ) TM2-TM1
!$     WRITE(UNIT=16,FMT='(1x," Total loop time (s) = ",ES16.5)' ) TM2-TM1

 9999  PRINT*, ' SMCPrDRG completed '

       CALL DATE_AND_TIME(CDate, CTime)
       WRITE(UNIT= 6,FMT="(1x,' End time date ',A10,2x,A10)") CTime, CDate
       WRITE(UNIT=16,FMT="(1x,' End time date ',A10,2x,A10)") CTime, CDate

       END PROGRAM SMCPropMP
!  End of main program


! Subroutine that calculate mid-flux values for x dimension 
       SUBROUTINE SgmCgWnK
         USE Constants
         USE W3DISPMD
         IMPLICIT NONE
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
         LOGICAL:: WW3DIS = .true. 

!!   Add option for single frequency propagation test.
         IF( NFrq .EQ. 1 ) THEN
             SIG(1)=Frqc1*2.0*Pie
             SIG(0)=SIG(1)/XFR
             SIG(2)=SIG(1)*XFR
            DSIP(0:2) = 1.0 
             FLCTH = .FALSE.
             FLCK  = .FALSE.
!           WW3DIS = .FALSE. 
         ELSE
!!   Setup frequency bands.
         CNST5=0.5*(XFR - 1.0/XFR)
          SIG(0)=Frqc0*2.0*Pie/XFR
         DSIP(0)=SIG(0)*CNST5
         DO n=1, NFrq+1
             SIG(n) = SIG(n-1)*XFR 
            DSIP(n) = SIG(n)*CNST5 
         END DO

         ENDIF
!!   End single frequency option IF-block.

!!   Assign water depth to HCel from KG integer values but DMIN.
!!   Set all depth half minimum depth for negative cells.
         HCel(-9:0) = 0.5*DMIN
         HCel(1:NC)=REAL( KG(1:NC) )
         DO n=1, NC
            IF(HCel(n) .LT. DMIN) HCel(n)=DMIN 
         ENDDO

!!   Assign group speed to be zero for negative cells.  
         CGRP(0:NFrq+1,-9:0)=0.0

!!   Calculate group speed and refaction factor for all cells
         CNST0=1.0E-6

!!   Use WW3 interpolation scheme if selected
         IF( WW3DIS ) THEN
!!   Setup interpolation table for dispersion relationship. 
            CALL DISTAB
         ENDIF 

!!   Frequency loop
         DO k=0, NFrq+1

!      CNST=2.0*GeoPie*Frqcy
         CNST=SIG(k)
         CNST4=CNST*CNST/GRAV

!!   Cell loop
         DO n=1, NC
            CNST3=HCel(n)

!!  Use WW3 interpolation scheme 
          IF( WW3DIS ) THEN

!         Calculate wavenumbers and group velocities.
            CALL WAVNU1(CNST,CNST3, WNmk(k,n),CGrp(k,n))

!!  Othewise, use iteration scheme.
          ELSE

!!  Iteration to calculate kH value for this cell
            CNST1=CNST4/TANH(CNST4*CNST3)
            CNST2=CNST4/TANH(CNST1*CNST3)
            DO WHILE ( ABS(CNST2 - CNST1) .GT. CNST0 )
               CNST1=CNST2
               CNST2=CNST4/TANH(CNST1*CNST3)
            ENDDO
            
!!  Save wave number 
            Wnmk(k,n) = CNST2

            CNST1=CNST2*CNST3 
            CNST2=1.0/COSH(CNST1)
!!  Group speed
            CGrp(k,n)=(GRAV*0.5/CNST)*(TANH(CNST1)+CNST2*CNST2*CNST1)

!!  End of selected dispersion scheme
          ENDIF

!!  Refraction rate factor, without the dt/d(theta) factor
            REFR(k,n)=CNST/SINH(2.0*CNST3*Wnmk(k,n))

!!  End of both cell and frequency loops
         ENDDO
         ENDDO

! 999  PRINT*, ' Sub SgmCgWnK ended.'

       RETURN
       END SUBROUTINE SgmCgWnK


! Subroutine that initialise C U V UC VC for rotating or deform 
!   flow field, using the same grid and time step.

      SUBROUTINE SPECUUVV
        USE Constants
        IMPLICIT NONE
        REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
        REAL:: Spec1D(NDir), Spec2D(NDir)
        REAL:: Spec1F(NFrq), Spec2F(NFrq), VSpc(NDir, NFrq)

!!  All velocities are in unit of basic cell length and time step or 
!!  divided by the grid velocity BX/DT or BY/DT

!! Initialise C U V for spherical rotation test in Arctic

!! All spectra are identical to a cosine distribution with main direction
!! at 45 deg NE and total wave energy equal to 25.0 so SQRT(E)=5.0.
!! or at -45 deg SE
!       CNST=50.0/Pie
!! Wave spectral factor is doubled (for SWH0 ~ 7m) as frequency profile is 
!! normalised for full range so its limited range integration is < 1.
!!      CNST=100.0/Pie
!! Parameter ENGY0 is set in Constants.f90 for user-defined initial SWH0.
        CNST=ENGY0
        Spec1D = 0.0
        Spec2D = 0.0
        CNST6 = 0.0
        DO k=1, NDir
           CNST1=COS(Theta(k) + Pie/4.0)
           CNST2=COS(Theta(k) - Pie/4.0)
           IF(CNST1 .GT. 0.0) THEN
              Spec1D(k)=CNST*CNST1*CNST1
           ENDIF
           IF(CNST2 .GT. 0.0) THEN
              Spec2D(k)=CNST*CNST2*CNST2
           ENDIF
           CNST6 = CNST6 + Spec1D(k)
        ENDDO
        SWH0=SQRT(CNST6*DThta)
        
!! Single frequency option 
        IF( NFrq .EQ. 1 ) THEN
            SpecPM= 1.0
            PkFrq = Frqc1 
        ELSE

!! Frequecy variable will be defined using the well-developed 
!! Pierson-Moskowitz (P-M) spectrum and normalised for full range
!! as (4*beta/omega)*(x^4)*EXP(-beta*x^4), where x=Ompeak/omega)
        CNST1=5.0
        CNST2=CNST1/4.0
        CNST3=SIG(NFrq/2)
        PkFrq=CNST3*0.5/Pie

!!   Frequency factors as P-M spectral.
        DO k=0, NFrq+1
           CNST=SIG(k)/CNST3
           CNST4=CNST*CNST*CNST*CNST
           SpecPM(k)=(CNST1/CNST)*CNST4*EXP(-CNST2*CNST4)
        ENDDO

        ENDIF
!!   End of single frequency option IF-block.

        Spec1F=SpecPM(1:NFrq)
        Spec2F=Spec1F

!! Initialise non-zero strips below SSLat and above SNLat upto north edge. 
!! Add round patches in the Arctic and around Equator if Arctic is included.
!! Also put a non-zero spectral zone within Arctic above 86N and a matching 
!! round patch near Equtor in the Atlantic.
!! Note ICE(2,*) is on SW cell corner.
      jk=NINT( (SSLat - ZLat)/DLat )
      kl=NINT( (SNLat - ZLat)/DLat )
      lm=MAXVAL( ICE(2,:)+ICE(4,:) )
      IF( Arctic ) THEN
          lm = ICE(2,NC-NArc+1) - MRFct*15
          mn = NINT( (86.0 - ZLat)/(DLat*MRFct) )*MRFct
      ENDIF
      WRITE(6,*) '  Initial non-zero S/N belt and ArcPatch j ranges =', jk, kl, lm, mn
      WRITE(6,*) '  Cell array j range =', MINVAL(ICE(2,:)), MAXVAL(ICE(2,:)+ICE(4,:))

!! N Atlantic centre at one size-8 cell centre.
      ijk=NINT(330.0/(MRFct*DLon))*MRFct + MRFct/2
      lmn=NINT(  5.0/(MRFct*DLat))*MRFct + MRFct/2

!! Loop over all cells to select strip points. 
      ii = 0
      jj = 0
      DO i=1,NC
         ll=ICE(2,i)
         mm=ICE(2,i) + ICE(4,i)

!!  Spectral frequency factor for all directions
         DO j=1,NFrq

!!  Northern strip above SNLat, use Spec1D
            IF( kl .LT. ll  .AND.  ll .LT. lm ) THEN
                WSpc(1:NDir,j,i)=Spec1D*Spec1F(j)
                ii = ii + 1
            ENDIF
!!  South strip below SSLat, use Spec2D
            IF( mm .LT. jk ) THEN
                WSpc(1:NDir,j,i)=Spec2D*Spec2F(j)
                jj = jj + 1
            ENDIF

!!  For global grid with Arctic part, use stripes.
            IF( Arctic ) THEN
!!  Work out cell centre distance from N Atlantic round patch centre.
                kk=ICE(1,i) + ICE(3,i)/2 - ijk
                nn=ICE(2,i) + ICE(4,i)/2 - lmn
                CNST5=REAL(kk)*DLon/5.0
                CNST6=REAL(nn)*DLat/5.0
                CNST7=CNST5*CNST5 + CNST6*CNST6
!!  Add a round patch at the Pole or in the Atlantic near the Equator.
                IF( (mm .GT. mn .AND. i .GT. NGLo ) .OR. (CNST7 < 1.01) ) THEN
                    WSpc(1:NDir,j,i)=Spec2D*Spec2F(j)
                ENDIF
            ENDIF

         ENDDO

      ENDDO

      WRITE(6,*) '  Initial non-zero S/N belt points =', ii/NFrq, jj/NFrq

      WRITE(6,*) '  Wind file conversion done!'

! 999  PRINT*, ' Sub SPECUUVV ended.'

      RETURN

      END SUBROUTINE SPECUUVV


!  This subroutine turn the wave spectrum by an fixed angle anti-clockwise
!  so that it may be used in the rotated or stanadard system.
!  First created:   26 Aug 2005   Jian-Guo Li
!  Last modified:   20 Jul 2009   Jian-Guo Li
!
! Subroutine Interface:

      Subroutine Specturn( NDirc, NFreq, Alphad, Spectr )
 
! Description:
!   Rotates wave spectrum anticlockwise by angle alphad
!
! Subroutine arguments
       IMPLICIT NONE
       INTEGER, INTENT(IN) :: NFreq, NDirc         ! No. frequ and direc bins
       REAL,    INTENT(IN) :: Alphad               ! Turning angle in degree
       REAL, INTENT(INOUT) :: Spectr(NDirc,NFreq)  ! Wave spectrum in and out

! Local variables
       INTEGER :: ii, jj, kk, nsft
       REAL    :: Ddirc, frac, CNST
       REAL, Dimension(NFreq)      ::  Wrkfrq, Tmpfrq
       REAL, Dimension(NDirc,NFreq)::  Wrkspc

! Check input bin numbers
       IF( (NFreq .LT. 0) .OR. (NDirc .LT. 0) )  THEN
          PRINT*, " Invalid bin number NF or ND", NFreq, NDirc
          RETURN
       ELSE
          Ddirc=360.0/REAL(NDirc)
       ENDIF

! Work out shift bin number and fraction

      CNST=Alphad/Ddirc
      nsft=INT( CNST )
      frac= CNST - REAL( nsft )
!     PRINT*, ' nsft and frac =', nsft, frac

! Shift nsft bins if >=1
        IF( ABS(nsft) .GE. 1 )  THEN
      DO ii=1, NDirc

! Wave spectral direction bin number is assumed to increase clockwise from North
! So shift nsft bins anticlockwise results in local bin number increases by nsft
         jj=ii + nsft
 
! As nsft may be either positive or negative depends on alphad, wrapping may
! happen in either ends of the bin number train
         IF( jj > NDirc )  jj=jj - NDirc
         IF( jj < 1     )  jj=jj + NDirc

! Copy the selected bin to the loop bin number
         Wrkspc(ii,:)=Spectr(jj,:)
 
      Enddo

! If nsft=0, no need to shift, simply copy
        ELSE
        Wrkspc = Spectr
        ENDIF

! Pass fraction of wave energy in frac direction
! Positive or anticlock case, larger bin upstream
        IF( frac > 0.0 ) THEN
      Tmpfrq=Wrkspc(1,:)*frac
      DO kk=NDirc, 1, -1
         Wrkfrq=Wrkspc(kk,:)*frac 
         Spectr(kk,:)=Wrkspc(kk,:) - Wrkfrq + Tmpfrq 
         Tmpfrq=Wrkfrq
      ENDDO
        ELSE
! Negative or clockwise case, smaller bin upstream
      Tmpfrq=Wrkspc(NDirc,:)*frac
      DO kk=1, NDirc
         Wrkfrq=Wrkspc(kk,:)*frac
         Spectr(kk,:)=Wrkspc(kk,:) + Wrkfrq - Tmpfrq
         Tmpfrq=Wrkfrq
      ENDDO
        ENDIF

! Specturn completed

       Return 
       End Subroutine Specturn
!

! Subroutine that generates the Arctic reference direction angle
      SUBROUTINE ArctAngd
        USE Constants
        IMPLICIT NONE
        REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        REAL, DIMENSION(NArc)::  XLon, WLat, ELon, ELat, AnglD
        REAL ::  DfPolat, DfPolon, Omega, DfSpeed

!!    Note only the Arctic part needs the rotation angles.
!     Work out u-face central position XLon, WLat in standard grid
      CNST1=DLon*0.5
      CNST2=DLat*0.5
      DfPolat=Polat
      DfPolon=Polon

!! All cells include the polar cell
!! Note the wlat is not at 90N for the polar cell as direction will be undefined.
!! Here Wlat is half dlat from the polar cell edge and half dlat from the NP.
      DO L=1, NArc-1
         i=L+NGLo

!!  Cell centre latitude equal to west side centre latitude.
!!  Cell centre longitude with half cell width increase from West side centre
!!  Although the polar cell is of angular radius dlat (not dlat/2) the 
!!  transformation location is still used dlat/2 from its SW corner. The error
!!  will be negeligible as only the AnglD is used.
         XLon(L)= REAL( ICE(1,i) )*DLon + CNST1*REAL( ICE(3,i) ) + ZLon 
         WLat(L)= REAL( ICE(2,i) )*DLat + CNST2*REAL( ICE(4,i) ) + ZLat

      END DO

!! North Polar cell centre coincide with NP but roation angle is specified for
!! its edge to avoid the singularity at Pole.
         XLon(NArc)=0.0
         WLat(NArc)=REAL( ICE(2, NC) )*DLat + ZLat
!! AnglD will be undefined with NP location as no local east at NP.

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NArc )

      DO L=1, NArc
!!  Keep the AnglD in Deg and store in AngArc(L).  Spectral rotation for
!!  boundary cell update will use this angle later.
         AngArc(L)=  AnglD(L) 
!!Li   Redefine GCT term factor for Arctic part or the netative of 
!!Li   tangient of rotated latitude divided by radius.  JGLi14Sep2015
         CTHG0S(L+NGLo)= - TAN( ELat(L)*D2RAD ) / REARTH
      END DO

!!  Output AngArc for checking
      WRITE(6,'(8ES12.3)') (AngArc(L), L=1, NArc, NArc/4)

!! Matching boundary cells for links between global and Arctic parts.
!! Assuming global boundary cells are at the end and Arctic boundary
!! cells are at the begginning of their cell list files.

!!   Match global boundary cells with Arctic inner cells
       DO i=1, NGLB
          ii=i+NGLA
!!   Search arctic part cells to match global part boundary cells
          mm=0
          DO k=NArA+NArB+1, NC-NPol
             IF(ICE(1,ii) .EQ. ICE(1,k) .AND. ICE(2,ii) .EQ. ICE(2,k)) THEN
                MBGLo(i)=k
                mm=1
             ENDIF
          ENDDO
          IF( mm .EQ. 0 ) PRINT*,' Miss global part boundary cell i=',i
       ENDDO

!!   Match Arctic boundary cells with global inner cells
       DO i=1, NArB
          ii=i+NArA
!!   Search global part to match arctic part boundary cells
          mm=0
          DO k=NGLA-2*NArB, NGLA
             IF(ICE(1,ii) .EQ. ICE(1,k) .AND. ICE(2,ii) .EQ. ICE(2,k)) THEN
                MBArc(i)=k
                mm=1
             ENDIF
          ENDDO
          IF( mm .EQ. 0 ) PRINT*,' Miss Arctic part boundary cell i=',i
       ENDDO
       PRINT*, ' Boundary cells matched for', NGLB, NArB

 999  PRINT*, ' Sub ArctAngd ended.'

      RETURN

      END SUBROUTINE ArctAngd


!Li
!Li  Merged UM source code for rotated grid, consiting the following
!Li  original subroutines in UM 6.1
!Li    LLTOEQ1A  WCOEFF1A  and  LBCROTWINDS1
!Li  The last subroutine is modified to process only one level winds
!Li  cpp directives are removed and required header C_Pi.h inserted.
!Li	    Jian-Guo Li     26 May 2005
!Li
!Li  The WCOEFF1A subroutine is merged into LLTOEQ to reduce repetition
!Li  of the same calculations. Subroutine interface changed to 
!Li  LLTOEQANGLE
!Li	    Jian-GUo Li     23 Aug 2005
!Li
!LL  Subroutine LLTOEQANGLE--------------------------------------------    
!LL                                                                        
!LL  Purpose:  Calculates latitude and longitude on equatorial             
!LL            latitude-longitude (eq) grid used in regional               
!LL            models from input arrays of latitude and                    
!LL            longitude on standard grid. Both input and output           
!LL            latitudes and longitudes are in degrees.                    
!Li	       Also calculate rotation angle in degree to tranform
!Li            standard wind velocity into equatorial wind.
!Li	       Valid for 0<PHI_POLE<90 or new pole in N. hemisphere.
!LL                                                                        
!* Arguments:--------------------------------------------------------    
      SUBROUTINE LLTOEQANGLE( PHI, LAMBDA, PHI_EQ, LAMBDA_EQ,     &  
     &                 ANGLED, PHI_POLE, LAMBDA_POLE, POINTS )       

      IMPLICIT NONE 

      INTEGER:: POINTS    !IN  Number of points to be processed             

      REAL :: PHI_POLE,  & !IN  Latitude of equatorial lat-lon pole
     &        LAMBDA_POLE  !INOUT  Longitude of equatorial lat-lon pole

      REAL, DIMENSION(POINTS) ::         &
     &        PHI,       & !IN  Latitude
     &        LAMBDA,    & !IN  Longitude
     &        ANGLED,    & !OUT turning angle in deg for standard wind
     &        LAMBDA_EQ, & !OUT Longitude in equatorial lat-lon coords
     &        PHI_EQ       !OUT Latitude in equatorial lat-lon coords

! Define local varables:-----------------------------------------------
      REAL :: A_LAMBDA, A_PHI, E_LAMBDA, E_PHI, SIN_PHI_POLE, COS_PHI_POLE,  &
     &        TERM1, TERM2, ARG, LAMBDA_ZERO, LAMBDA_POLE_KEEP
      INTEGER   :: I   
      REAL, PARAMETER :: SMALL=1.0E-6

! Constants from comdecks:---------------------------------------------

      Real, Parameter :: Pi = 3.14159265358979323846  , &
     &                   Pi_Over_180 = Pi/180.0       , &
     &                   Recip_Pi_Over_180 = 180.0/Pi        

!*----------------------------------------------------------------------   

! 1. Initialise local constants
! Scale lambda pole to range -180 to 180 degs
      LAMBDA_POLE_KEEP=LAMBDA_POLE
      IF (LAMBDA_POLE.GT. 180.0) then
          LAMBDA_POLE=LAMBDA_POLE-360.0
      ENDIF

! Latitude of zeroth meridian
      LAMBDA_ZERO=LAMBDA_POLE+180.0
! Sine and cosine of latitude of eq pole
      IF (PHI_POLE >= 0.0) THEN
        SIN_PHI_POLE =  SIN(PI_OVER_180*PHI_POLE)
        COS_PHI_POLE =  COS(PI_OVER_180*PHI_POLE)
      ELSE
        SIN_PHI_POLE = -SIN(PI_OVER_180*PHI_POLE)
        COS_PHI_POLE = -COS(PI_OVER_180*PHI_POLE)
      ENDIF

! 2. Transform from standard to equatorial latitude-longitude

      DO 200 I= 1, POINTS

! Scale longitude to range -180 to +180 degs

      A_LAMBDA=LAMBDA(I)-LAMBDA_ZERO
      IF(A_LAMBDA.GT. 180.0) A_LAMBDA=A_LAMBDA-360.
      IF(A_LAMBDA.LE.-180.0) A_LAMBDA=A_LAMBDA+360.

! Convert latitude & longitude to radians

      A_LAMBDA=PI_OVER_180*A_LAMBDA
      A_PHI=PI_OVER_180*PHI(I)

! Compute eq latitude using equation (4.4)

      ARG=-COS_PHI_POLE*COS(A_PHI)*COS(A_LAMBDA)   &
     &    +SIN_PHI_POLE*SIN(A_PHI)
      ARG=MIN(ARG, 1.0)
      ARG=MAX(ARG,-1.0)
      E_PHI=ASIN(ARG)
      PHI_EQ(I)=RECIP_PI_OVER_180*E_PHI

! Compute eq longitude using equation (4.6)

      TERM1 = SIN_PHI_POLE*COS(A_PHI)*COS(A_LAMBDA)   &
     &       +COS_PHI_POLE*SIN(A_PHI)
      TERM2 = COS(E_PHI)
      IF(TERM2 .LT. SMALL) THEN
        E_LAMBDA=0.0
      ELSE
        ARG=TERM1/TERM2
        ARG=MIN(ARG, 1.0)
        ARG=MAX(ARG,-1.0)
        E_LAMBDA=RECIP_PI_OVER_180*ACOS(ARG)
        E_LAMBDA=SIGN(E_LAMBDA,A_LAMBDA)
      ENDIF

! Scale longitude to range 0 to 360 degs

      IF(E_LAMBDA.GE.360.0) E_LAMBDA=E_LAMBDA-360.0
      IF(E_LAMBDA.LT.  0.0) E_LAMBDA=E_LAMBDA+360.0
      LAMBDA_EQ(I)=E_LAMBDA

!Li  Calculate turning angle for standard wind velocity

      E_LAMBDA=PI_OVER_180*LAMBDA_EQ(I)

! Formulae used are from eqs (4.19) and (4.21)

      TERM2=SIN(E_LAMBDA)
      ARG= SIN(A_LAMBDA)*TERM2*SIN_PHI_POLE      &
     &    +COS(A_LAMBDA)*COS(E_LAMBDA)
      ARG=MIN(ARG, 1.0)
      ARG=MAX(ARG,-1.0)
      TERM1=RECIP_PI_OVER_180*ACOS(ARG)
      ANGLED(I)=SIGN(TERM1,TERM2)
!Li

 200  CONTINUE

! Reset Lambda pole to the setting on entry to subroutine
      LAMBDA_POLE=LAMBDA_POLE_KEEP

      RETURN
      END SUBROUTINE LLTOEQANGLE
!Li


! Subroutine to read cell and face arrays and to define grid variables.
!  First created:    1 Apr 2015   Jian-Guo Li
!  Last modified:   18 Oct 2021   Jian-Guo Li

      SUBROUTINE ReadCell
        USE Constants
        IMPLICIT NONE
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        CHARACTER(Len=136):: PathName

!  Read Global and Arctic part Multiple-Cell info
       PathName=TRIM(DataPath)//TRIM(GridName)//'Cels.dat'
       OPEN(UNIT=8, FILE=TRIM(PathName), STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, PathName//' was not opened! '
          READ (8,*) NGLo, NRLCel(1:MRL) 
       DO J=1,NGLo
          READ (8,*) (ICE(N,J), N=1,4), KG(J)
       END DO
       CLOSE(8)
       PRINT*, PathName//' read done ', NGLo, NRLCel(1:MRL) 

!!  Arctic part becomes optional.  JGLi12Dec2011
       IF( Arctic ) THEN
       PathName=TRIM(DataPath)//TRIM(GridName)//'BArc.dat'
       OPEN(UNIT=8, FILE=TRIM(PathName), STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, PathName//' was not opened! '
          READ (8,*) NArc, NArB, NGLB
       DO J=NGLo+1, NGLo+NArc
          READ (8,*) (ICE(N,J), N=1,4), KG(J) 
       END DO
       CLOSE(8)
       PRINT*, PathName//' read done  NArc=', NArc

!!  Total Arctic boundary cells
          NB=NArB+NGLB
          PRINT*, ' With Arctic part', NArc, NArB, NGLB

       ELSE
          NArc = 0
          NArB = 0
          NGLB = 0
          PRINT*, ' No Arctic part', NArc, NArB, NGLB
       ENDIF

!  Total cell number will be sum of two parts
       NC = NGLo + NArc

!!   Set boundary cell counts.  Boundary cells for the global part are at the end
!!   of SMC625Cels.dat and for the Arctic part at the start of SMC625Budy.dat.
!!   Boundary cell will then from NGLo-NGLB+1 to NGLo for lower part and NGLo+1 to NGLo+NArB
!!   NGLA and NArA are the extra numbers to be added for boundary loop 1, NGLB and 1, NArB
       NGLA=NGLo-NGLB
       NArA=NGLo

!!    Work out South and North Pole cell number if NPol = 2
      IF (NPol .EQ. 2) THEN
         IF( ICE(2,NC) .GT. ICE(2,NC-1) ) THEN
             NNor = NC
             NSou = NC - 1
         ELSE
             NSou = NC
             NNor = NC -1
         ENDIF
      ELSE
!!    Assume only North Pole in the Arctic is used (NPol = 1).
         NNor = NC
         NSou = 0
      ENDIF

!  Output a few to check input values
       DO J=1, NC, NC/4
          WRITE(6,'(i8,2i6,i5,i4,i6)') J, (ICE(N,J), N=1,4), KG(J)
       END DO

!    Boundary -9 to 0 cells for cell size 2**n
!    Note the position indice for bounary cell are not used.
       ICE(1,-9:0)=0
       ICE(2,-9:0)=0
       ICE(3,   0)=1
       ICE(4,   0)=1
!!   Restrict boundary cell y-size no more than base cell size
!!          2**(MRL-1).
       mm = 2**(MRL-1)
       DO i=1,9
          ICE(3,-i)=ICE(3,-i+1)*2
          ICE(4,-i)=MIN(mm, ICE(3,-i))
       ENDDO

!!  Read sorted ISD JSD variables for global part.
       PathName=TRIM(DataPath)//TRIM(GridName)//'ISid.dat'
       OPEN(UNIT=10, FILE=TRIM(PathName), STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, PathName//' was not opened! '
       READ(10,*) NUGL, NRLUFc(1:MRL)      
       WRITE(6,*) " Read u face numbers NUGL, NRLUFc(1:MRL)"     
       WRITE(6,*)                       NUGL, NRLUFc(1:MRL)      
       DO I=1,NUGL
          READ(10,*)  (ISD(N,I), N=1,7)
       END DO
       CLOSE(10)

       PathName=TRIM(DataPath)//TRIM(GridName)//'JSid.dat'
       OPEN(UNIT=11, FILE=TRIM(PathName), STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, PathName//' was not opened! '
       READ(11,*) NVGL, NRLVFc(1:MRL)     
       WRITE(6,*) " Read v face numbers NVGL, NRLVFc(1:MRL) "
       WRITE(6,*)                       NVGL, NRLVFc(1:MRL)  
       DO J=1,NVGL
!         READ(11,*)  (JSD(N,J), N=1,8)
          READ(11,*)  (JSD(N,J), N=1,7), kk
       END DO
       CLOSE(11)

!!  Read sorted ISD JSD variables for Arctic part.
       IF( Arctic ) THEN

       PathName=TRIM(DataPath)//TRIM(GridName)//'AISd.dat'
       OPEN(UNIT=10, FILE=TRIM(PathName), STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, PathName//' was not opened! '
       READ(10,*) NUAr
       WRITE(6,*) " Read u face numbers NUAr =", NUAr
       DO I=1,NUAr
          READ(10,*)  (ISD(N,I+NUGL), N=1,7)
       END DO
       CLOSE(10)

       PathName=TRIM(DataPath)//TRIM(GridName)//'AJSd.dat'
       OPEN(UNIT=11, FILE=TRIM(PathName), STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, PathName//' was not opened! '
       READ(11,*) NVAr
       WRITE(6,*) " Read v face numbers NVAr =", NVAr
       DO J=1,NVAr
!         READ(11,*)  (JSD(N,J+NVGL), N=1,8)
          READ(11,*)  (JSD(N,J+NVGL), N=1,7) 
       END DO
       CLOSE(11)

!!  Set total face nubmers
       NU=NUGL+NUAr
       NV=NVGL+NVAr

!!  Reset arctic part cell numbers in I/JSD by adding NGLo for positive cells only.
!!  The 0 and negative cells for boundary useage will be shared by the two parts.
       DO I=NUGL+1, NU
         DO M=4,7
            IF(ISD(M,I) > 0) ISD(M,I)=ISD(M,I)+NGLo
         END DO
       END DO

       DO J=NVGL+1, NV
         DO M=4,7
            IF(JSD(M,J) > 0) JSD(M,J)=JSD(M,J)+NGLo
         END DO
       END DO

       WRITE(6,*) " Arctic u v face cell values have been adjusted."

!!  Without Arctic part, set total NU NV equal to global part.
       ELSE

          NUAr = 0
          NVAr = 0
          NU=NUGL
          NV=NVGL

       ENDIF

 999   PRINT*, ' Sub READCELL ended.'

       RETURN

      END SUBROUTINE READCELL


! Subroutine to read current velocity and calculate their gradients.
!  First created:    20 Apr 2017   Jian-Guo Li
!  Last modified:    20 Apr 2017   Jian-Guo Li

      SUBROUTINE ReadCurnt(NTM)
        USE Constants
        IMPLICIT NONE
        INTEGER, INTENT(IN) :: NTM         ! No. of time steps 

        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        CHARACTER(Len=20) :: CurnFile='Curnt100000.dat'

!  Read current velocity from ww3 output text file.
        WRITE(CurnFile(6:11), FMT='(i6)' )  100000+NTM
        OPEN(UNIT=8, FILE="./DatGMC/"//TRIM(CurnFile), STATUS='OLD',IOSTAT=nn,ACTION='READ')
        IF(nn /= 0) PRINT*, CurnFile//' was not opened! '
          READ (8,FMT='(30X,I9)') NSEA 
        IF(NC .NE. NSEA) THEN 
          PRINT*, " *** Inconsistent cell number NC, NSEA =", NC, NSEA
          Return
        ENDIF
          READ (8,*) (CX(I), I=1,NSEA), (CY(J), J=1,NSEA)
        CLOSE(8)

 999  PRINT*, ' Sub READCURNT ended for NT =', NTM

      RETURN

      END SUBROUTINE READCURNT


! Subroutine to write SWH field out at given time step.
!  First created:   15 Aug 2019   Jian-Guo Li
!  Last modified:   18 Oct 2021   Jian-Guo Li

      SUBROUTINE WRITESWH( MT )
        USE Constants
        IMPLICIT NONE

        INTEGER, INTENT(IN):: MT

!!    First calculate SWH on each rank.
        HS(:)=0

!$OMP Parallel DO Default(Shared), Private(i,j,k, CTT, CMX) 
        DO i=1, NC
           CTT=0.0
           DO j=1, NFrq
           DO k=1, NDir 
              CTT = CTT + WSpc(k,j,i)*DSIP(j)
           ENDDO
           ENDDO
           CMX=CTT*DThta
           HS(i) = SIGN( SQRT( ABS(CMX) ), CMX  )

!!   Filter very small C(n) value so it is greater than E-36
           IF( Abs(HS(i)) .LT. 1.0E-36 ) THEN
               HS(i)=SIGN( 1.0E-36, CMX )
           ENDIF

        ENDDO
!$OMP END Parallel DO

!$OMP MASTER

!  Output tracer concentration if at selected writeup time steps
        WRITE(FL9NM(3:7), FMT='(i5)' )  10000 + MT
        OPEN(UNIT=26, FILE=TRIM(Tempath)//FL9NM, STATUS='NEW',IOSTAT=nn)
        IF(nn /= 0) PRINT*,' File FL9NM was not opened! '
        WRITE(UNIT=6,FMT='(2x,"NT= ",i6,3x,A9)') MT,FL9NM

!    All cells are saved 
        WRITE(UNIT=26, FMT='(2x,2i8)' )  MT, NC
        WRITE(UNIT=26, FMT=7113)  (HS(n),  n=1, NC)
        CLOSE(26)
 7113   FORMAT( 1x, 7ES11.3 )

!$OMP END MASTER

!!   Return from subroutine WRITESWH
      RETURN

      END SUBROUTINE WRITESWH
!!
!!  End of program SMCGPropMP.f90 file.
!!

