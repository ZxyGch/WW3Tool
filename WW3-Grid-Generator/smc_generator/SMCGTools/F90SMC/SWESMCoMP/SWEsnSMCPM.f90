!  This module is a common block similar in all AFT Model programs and is
!  written in FORTRAN 90.
!                     J G Li   26 Oct 2000
!!
!! Adapted for multiple cell 2D advection tests using UNO schemes.
!!                    J G Li    8 Aug 2007
!! Reformated for global multiple cell advection tests.
!!                    J G Li   16 Nov 2007
!! Modified for extended global SMC grid advection tests.
!!                    J G Li   28 Nov 2008
!! Modified for Arctic 2-D spectral transportation tests.
!!                    J G Li   16 Jul 2009
!! Adapted for UK3km multi-resolution grid spectral transport.
!!                    J G Li    8 Feb 2010
!! Changed for multi-step, multi-resolution G6kSMC grid transport.
!!                    J G Li   23 Feb 2010
!! Adapted for 2-part, 4-step, 8-resolution G6kSMC grid spectral transport.
!!                    J G Li    5 Mar 2010
!! Add great circle turning term in G6kSMC grid spectral transport.
!!                    J G Li   22 Mar 2010
!! Add refraction term and use shallow water wave speed. 
!!                    J G Li   26 Mar 2010
!! Modify refraction term with rotation sub.
!!                    J G Li   18 May 2010
!! Add diffusion term in advection subs.
!!                    J G Li    3 Jun 2010
!! Add Atlantic round patch for comparison with Arctic one.
!!                    J G Li    2 Jun 2011
!! New refraction formulation using cg only.
!!                    J G Li    3 Jun 2011
!! Old refraction plus refraction limiter to gradient direction.
!!                    J G Li   16 Jun 2011
!! Modified for SMC625 global part only spectral transport.
!!                    J G Li   12 Dec 2011
!! Modified to use new cell and face array files.  JGLi28Feb2012
!!
!! Test redued Arctic part on SMC6-25 grid.   JGLi21Mar2012
!!
!! Test refined UK waters on SMC6125 grid.   JGLi08Jan2013
!!
!! Automatic setting of multi-resolution loops  with MRL and MFct.
!! Adapted for UK 3km global 25km SMC36125 grid.   JGLi28Feb2014
!!
!! Adapted for SMC1d full global with 2 poles.    JGLi22Jan2015
!!
!! Modified for SMC1d shallow water equations.    JGLi26Jan2015
!!
!! SWE test of Williamson etal 1992 Case 2.    JGLi12Feb2015
!!
!! Add average smoothing for U V fields.    JGLi19Mar2015
!!
!! Output velocity along zero meridion and the Equator.  JGLi23Mar2015
!!
!! Reduced averaging by increased central weight.  JGLi30Mar2015
!!
!! Readcell sub and polar cell radius parameter.  JGLi01Apr2015
!!
!! Revise gradient sub to use numerical average.  JGLi02Apr2015
!!
!! Adapted for SMChfd grid.    JGLi14Apr2015
!!
!! Set all quantities to be zero for dry points or Hw=0  JGLi03Feb2016
!!
!! Introducing a damping factor -gm*V.   JGLi04Mar2016
!!
!! Modified to match Shalwt50/SWE50HEmFill.f90.   JGLi08Mar2016
!!
!! Restore UVC 1-2-1 average and suspend velocity ceiling 20 m/s.  JGLi09Mar2016
!!
!! Suspend water height update for a steady current field.   JGLi23May2016
!!
!! Adapted for SMC25MR3 grid with 3 levels of refinment.   JGLi01Jun2016
!!
!! Adapted for new SMChfd grid without equatorial centred row.   JGLi15Jun2016
!!
!! Modify READCELL to read cell and face arrays only.    JGLi26Sep2016
!!
!! Output individual terms at selected points.   JGLi18Oct2016
!!
!! Fix quarter gradient bug in DHDX/Y sub.    JGLi20Oct2016
!!
!! Add error calculating sub for l1 l2 and lmx.  JGLi02Dec2016
!!
!! Adapted for Williamson etal (1992) case 6 test.  JGLi06Dec2016
!!
!! Fix bugs in case 6 text initial U V field.  JGLi09Dec2016
!!
!! Half-cell correction for latitudes in ArctAngd.  JGLi14Dec2016
!!
!! To produce h+b output instead of h only.   JGLi06Jan2017
!!
!! Calculate total energy and assess energy conservation.   JGLi09Jan2017
!!
!! Galewsky et al (2004) instable jet test Gsj.   JGLi11Jan2017
!!
!! Add 3rd order UNO3 scheme for propagation.   JGLi12Jan2017
!!
!! Adapted for single resolution hfd grid.    JGLi16Jan2017
!!
!! Add option for polar region and avarage options.   JGLi19Jan2017
!!
!! Use mass-conserving diffusion rather than 1-2-1 average.   JGLi05Jun2017
!!
!! Adapted for W6 test using new diffusion scheme for Hw.   JGLi06Jun2017
!!
!! Adapted for unstable jet test with Hw diffusion scheme.   JGLi07Jun2017
!!
!! Adapted for W2 test with Hw diffusion scheme.   JGLi08Jun2017
!!
!! Change time step loop to every main timestep.   JGLi28Jun2017
!!
!! Adapted for Indian Ocean SWEs tsunami model.    JGLi06Feb2018
!!
!! Adapted for Mediterranean Sea tsunami model.    JGLi12Apr2018
!!
!! New modules to separate dynamic subs from grid parameters.  JGLi28Nov2019
!!
!! Modified to merge all SWEs tests into a single model.  JGLi20Jul2022 
!!
!! Add selected point output for tsunami simulations.     JGLi28Dec2023 
!!
!! Parallelization of SWEs model with OpenMP directives.  JGLi06Feb2024 
!!
!! Replace GmDT with bottom friction coefficent CBFr.     JGLi20Mar2024 
!!
!! Separate potential and kinetic energy integrations.    JGLi25Jul2024 
!!

      PROGRAM SWEsnSMC 
       USE SWEsCnstMD
       USE SWEsInitMD
       USE SWEsDynaMD
!/ Use omp_lib for OpenMP functions if switched on.   JGLi02Feb2024
!$       USE omp_lib

       IMPLICIT NONE

       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST8

!!  Check command arguments.
       II = COMMAND_ARGUMENT_COUNT()
       IF( II < 1 )THEN
          WRITE(*,*)' *** Will use default input file name. ***'
!         STOP
       ELSE
!!  Get InpFile name from command line argument 
          CALL GET_COMMAND_ARGUMENT(1, InpFile, Status=K)
       ENDIF
       WRITE(*,*) " *** Input File is ",  TRIM(InpFile)

! Open input file and read grid parameters.
       OPEN(UNIT=8,FILE= TRIM(InpFile),STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,InpFile//' was not opened! '

          READ(8,*)   GridName
         WRITE(6,*)   GridName
          READ(8,*)   DataPath
         WRITE(6,*)   DataPath
          READ(8,*)   NCL,  NFC,  MRL,  Itrm
         WRITE(6,*)   NCL,  NFC,  MRL,  Itrm
          READ(8,*)   NLon, NLat, NPol, Init
         WRITE(6,*)   NLon, NLat, NPol, Init
          READ(8,*)   NTS,  NWP,  NHrg, NLrg
         WRITE(6,*)   NTS,  NWP,  NHrg, NLrg
          READ(8,*)   ZLon, ZLat, DLon, DLat
         WRITE(6,*)   ZLon, ZLat, DLon, DLat
          READ(8,*)   DFR0, DT,   AKHM, CBFr
         WRITE(6,*)   DFR0, DT,   AKHM, CBFr
          READ(8,*)   PLon, PLat, PAvr, Beta
         WRITE(6,*)   PLon, PLat, PAvr, Beta
          READ(8,*)   Arctic, Source, WHPrts, Restrt
         WRITE(6,*)   Arctic, Source, WHPrts, Restrt

       CLOSE(8)
 
!!  Substitue DFR0 for unused DTG as input and rescale if it is > 1.0. 
!!  It starts diffusion ramping with initial value of DFR0*AKHM.  JGLi16May2025
       IF( DFR0 > 1.0 ) DFR0 = 1.0

!!  Allocate cell and face arrays.
       ALLOCATE( ICE(4,-9:NCL), ISD(1:7,NFC), JSD(1:7,NFC), KG(NCL) )
       ALLOCATE( NRLCel(0:MRL), NRLUFc(0:MRL), NRLVFc(0:MRL) )

!!  Call sub to read cell and face arrays 
       CALL READCELL

!!  Adjust boundary cell index for SWEs model so Arctic link boundary
!!  faces will have open boundary condition.  JGLi10Aug2022
       CALL ArctLink

!! Allocate grid related variables.
       NLat2=NLat/2
       ALLOCATE( YSLat(-NLat2:NLat2), CSLat(-NLat2:NLat2), RCELA(-9:NCL),   &
                 YCLat( -NLat:NLat ), CCLat( -NLat:NLat ), BS2Lat(-NLat:NLat) )
  
!!  Evaluate dx length along latitude in rad
       DX0=DLON*D2RAD
       DO n=-NLat2, NLat2
          YSLat(n)=Real( n )*DLAT + ZLat
          CSLat(n)=COS( YSLat(n)*D2RAD )
          IF(CSLat(n) .LT. ZENO) CSLat(n) = ZENO
       ENDDO
       DO n=-NLat, NLat
          YCLat(n)=Real( n )*DLAT*0.5 + ZLat
          CCLat(n)=COS( YCLat(n)*D2RAD )
          IF(CCLat(n) .LT. ZENO) CCLat(n) = ZENO
          BS2Lat(n)=(1.0 - Beta) + Beta*( SIN( YCLat(n)*D2RAD ) )**2
       ENDDO
     
!!  Define cell area for cell update
       DY=DLAT*D2RAD
       DYR=1.0/DY

!!   Evaluate other cell dx length in rad and cell area in rad**2
!!   except for polar cells.
       DO L=-9,NC-NPol
          RCELA(L)=1.0/Real( ICE(3,L)*ICE(4,L) )
       ENDDO

       IF( NPol .GT. 0 ) THEN 
!!  Polar cells are round cell of radius R=PCRDY*DY*ICE(4,NC), where
!!  the PCRDY factor specifies whether the polar cell takes a full row.
!!  The RCELA(NC) converts the normal V-flux factor for the polar cell 
!!  and it does not need the CCLat factor, which is zero at the Pole.
!!  The normal V-flux factor is 1/(DX0*DY).       JGLi02Dec2016
          CNST1=PCRDY*DY*Real( ICE(4,NNor) )
          CNST2=Pie*CNST1*CNST1
          RCELA(NNor)=DX0*DY/CNST2 
       ENDIF
!!  Duplicate north polar cell parameters for south polar cell if NPol = 2
       IF( NPol .GT. 1 ) THEN
          RCELA(NSou)= RCELA(NNor)
       ENDIF

!!  Polar average setting.   JGLi19Jan2017
        JEqut = INT( (0.0 - ZLat)/DLat )
        JPvrg = INT( PAvr/DLat )
        WRITE(6,*) " Polar average JEqut, JPvrg = ", JEqut, JPvrg

!!  Convert diffusivity into radian^2 s-1 and multiply by 2*DT
!!  The 2.0 factor is added to cancel the 0.5 factor in the gradient.
!!  Ramp factor is introduced to reduce the diffusivity in early hours
!!  with initial value at DFR0 times of the maximum one.  JGLi09Aug2024
        AKHDMX= 2.0*AKHM*DT/(REARTH*REARTH)
        AKHDT2= DFR0*AKHDMX 

!!  Allocate some working variables with MOLD option.
        ALLOCATE( A(-9:NCL),  C(-9:NCL),  D(-9:NCL),  F(-9:NCL), &
                 Hw(-9:NCL), AU(-9:NCL), AV(-9:NCL), DX(-9:NCL), &
                DXR(-9:NCL), UC(-9:NCL), VC(-9:NCL),Hw0(-9:NCL), &
              CSAnC(-9:NCL),UC0(-9:NCL),VC0(-9:NCL),Btm(-9:NCL), &
              SNAnC(-9:NCL),UCL(-9:NCL),UCS(-9:NCL),VCS(-9:NCL), &
              CoriF(-9:NCL),Vort(-9:NCL),Enkn(-9:NCL),BFrc(-9:NCL), & 
              AngCD(-9:NCL),DHDX(-9:NCL),DHDY(-9:NCL),HCel(-9:NCL), & 
               Enpt(-9:NCL),EnkH(-9:NCL) )

        ALLOCATE( U(NFC), UT(NFC),  V(NFC), VT(NFC),  &
                 FU(NFC), FV(NFC), FX(NFC), FY(NFC),  &
              CSAnU(NFC), SNAnU(NFC), CSAnV(NFC), SNAnV(NFC) )

!   Whole array assignment for i=-8,NCL
        C=0.0

!!  Default ocean floor bottom altitude at -KG    JGLi06Jun2016
        Btm = 0.0
        Btm(1:NC) = - FLOAT( KG(1:NC) )
        WRITE(6,FMT='(" Maximum water depth -Btm(1:NC)=",f8.1)') MAXVAL(-Btm(1:NC))
        WRITE(6,FMT='(" Maximum height above sea level=",f8.1)') MAXVAL( Btm(1:NC))
        WRITE(6,FMT='(" Boundary cell Btm(-9:0)=",10f5.1)') Btm(-9:0)

!!  Multiple factor for multi-resolution loops
        MFct=2**(MRL - 1)
        WRITE(6,*) ' Multi-Resolution level and factor=', MRL, MFct
        Frct=1.0/REAL(MFct)

!!  Work out number of timesteps per hour.
        MHr=  INT(3600.0/DT+0.001)
        WRITE(6,*) ' Number of steps per hour=', MHr 

!  Initialise CS/SNAnC/U/V, assuming AngleD = 0.0 
        CSAnC=1.0
        CSAnU=1.0
        CSAnV=1.0
        SNAnC=0.0
        SNAnU=0.0
        SNAnV=0.0


!  Generate flux face and cell rotation Angle for Arctic cells
        IF( Arctic ) THEN
            ALLOCATE( MBGLo(NGLB), MBArc(NArB) )
            CALL ArctAngd
        ENDIF

!  Read selected points cell IDs from WHCellIDs.txt.
        IF( WHPrts ) THEN
        OPEN(UNIT=9,FILE='WHPrtsID.txt',STATUS='OLD',IOSTAT=nn,ACTION='READ')
        IF(nn /= 0) PRINT*,' *** WHPrtsID.txt was not opened! '
        READ(9, *) NPrt 
        ALLOCATE( IDPrt(NPrt) )
        READ(9,*) IDPrt 
        WRITE(6,*) ' Water height difference output at points of NPrt=', NPrt
        CLOSE(9)
        ENDIF

!  Initialise cell centre velocity and water height fields.
        WRITE(6,*) ' Selected test case numbr=', Init
        SELECT CASE( Init )
          CASE( 1 )
              CALL FilOcean
          CASE( 2 )
              CALL W2HfUCVC
          CASE( 3 )
              CALL GsHfUCVC(3)
          CASE( 4 ) 
              CALL W5HfUCVC
          CASE( 5 ) 
              CALL W6HfUCVC(0.0, Hw, UC, VC)
          CASE( 6 )
              CALL TsunamiS
          CASE( 7 )
              CALL TsunamiS
              CALL WRITEOUT(A, 0, 'Ds')
          CASE( 8 )
              CALL TsunCanr
          CASE( 9 )
              CALL GsHfUCVC(0)
          CASE Default
              CALL INITUCVC
        END SELECT
         
!  Assume starting from 0 step.
        NS = 0
!  Use restart file if required, read UC, VC, and Hw 
        IF( Restrt ) THEN
            CALL READUVHs(UC, VC, A, NS)
!  Remove Btm from A before assigne to Hw
            Hw = A - Btm
        ENDIF
        NT = NS
        WRITE(6,*) " Restart time step NS set to be ", NS

!  Save a copy of initial water height at start time step.
        A = Hw +Btm 
        CALL WRITEOUT( A, NT, 'Hb')
!  Relative vorticity and UV output
        CALL UVNTerpo
        CALL Vorticty
        A = (Vort - CoriF)/DT
        CALL WRITEOUT(A, NT, 'Vr')
        CALL Integral(A, Vrint)
        CALL WRITEUVs(UC, VC, NT)
        CALL Integral(Hw, Hwint)

!  Save initial values for later use.
        Hw0 = Hw
        UC0 = UC
        VC0 = VC
 
!  Calculate initial value intergation for errors l1 l2 and lmax 
        CALL Errol12m(Hw0, HEl12m)
        CALL Errol12m(UC0, UEl12m)
        CALL Errol12m(VC0, VEl12m)

!  Calculate initial potential energy integration with Enkn = 0. 
        Enkn = 0.0
!  First excluded initial disturbances by swith to flat surface.
        Hw = -Btm 
        CALL TotlEngy 
        CALL Integral( Enpt, Entgrl )
        Enpt0 = Entgrl
!  Then restore initial disturbance back inot Hw.  JGLi22Jul2024
        Hw = Hw0

! Calculate initial total potential energy and substract Enpt0
        CALL KinetcEn(UC0, VC0)
        CALL TotlEngy 
        CALL Integral( Enpt, Entgrl )
        Enetp = Entgrl - Enpt0
! Calculate initial total kinetic energy, which should be zero if EnkH=0.
        CALL Integral( EnkH, Entgrl )
        Enetk = Entgrl 

! Calculate bathymetry gradient without kinetic energy
        Enkn = 0.0
        Hw = 1.0
        CALL DHDXDHDY
        Hw = Hw0 
        A = DHDX 
        CALL WRITEOUT(A, NT, 'HX')
        C = DHDY
        CALL WRITEOUT(C, NT, 'HY')
!       CALL WRITEUVs(A, C, NT+1)
!! Borrow UV output to save DHDX/Y as NT+1 output, should rename
!! the file afterwards to avoid confusion.

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
       OPEN(UNIT=16,FILE='CMesgs.txt',STATUS='UNKNOWN',IOSTAT=nn, &
        &           ACTION='WRITE')
       IF(nn /= 0) PRINT*,' File CMesgs.txt was not opened! '

!     Header messages and configuration information 
       WRITE(UNIT=16,FMT='(1x/   &
        &  "  Spherical Multiple-Cell Shallow Water Equation Model" /    &
        &  "         SMC Version 3.0   J G  Li  Feb 2018  " /)' )

       CALL DATE_AND_TIME(CDate, STime)
       WRITE(UNIT=16,FMT="(1x,' Run start time date ',A10,2x,A10)") STime, CDate

       WRITE(UNIT=16,FMT='(1x," Lon/Lat/NPol grid No.s = ",3i8)')  NLon, NLat, NPol
       WRITE(UNIT=16,FMT='(1x," Size-1 Units DLON DLAT = ",2f14.10)')  DLON, DLAT
       WRITE(UNIT=16,FMT='(1x," Equatorial PoLat PoLon = ",2f8.2)')  PoLat, PoLon
       WRITE(UNIT=16,FMT='(1x," Rotated grid PLat PLon = ",2f8.2)')  PLat, PLon
       WRITE(UNIT=16,FMT='(1x," Standard grid ZLat/Lon = ",2f9.5)')  ZLat, ZLon
       WRITE(UNIT=16,FMT='(1x," Polar averge lat and j = ",f8.2,i8)') PAvr, JPvrg
       WRITE(UNIT=16,FMT='(1x," Averg intrvl NHrg NLrg = ",2i8)' )    NHrg,   NLrg 
       WRITE(UNIT=16,FMT='(1x," Angular speed36h, GmDT = ",ES12.3,f8.4)' ) Agu36, GmDT
       WRITE(UNIT=16,FMT='(1x," Maximum x-Fourier Nmbr = ",ES12.3,f8.4)' )  AKHDMX*2.0/(DX0*DX0*MFct)
       WRITE(UNIT=16,FMT='(1x," Maximum y-Fourier Nmbr = ",ES12.3,f8.4)' )  AKHDMX*0.5*DYR*DYR/MFct
       WRITE(UNIT=16,FMT='(1x," Horiz. diffusvty, beta = ",ES12.3,f8.4)' )  AKHM, Beta
       WRITE(UNIT=16,FMT='(1x," Initial diff DFR0,DFHr = ",2f8.3)' )  DFR0, DFHr
       WRITE(UNIT=16,FMT='(1x," Basic/Frac timestep (s)= ",2f8.1)' )  DT, Frct*DT
       WRITE(UNIT=16,FMT='(1x," Maximum grid speed s-1 = ",ES12.3)') UMX
       WRITE(UNIT=16,FMT='(1x," Maximum Courant number = ",ES12.3)') CMX
       WRITE(UNIT=16,FMT='(1x," Initial total energy   = ",ES12.3)') Enpt0
       WRITE(UNIT=16,FMT='(1x," Total write time steps = ",2i8)')  NTS, NWP
       WRITE(UNIT=16,FMT='(1x," Start step & test case = ",2i8)' )  NS, Init
       WRITE(UNIT=16,FMT='(1x," Multi-reso levl factor = ",2i8)')  MRL, MFct
       WRITE(UNIT=16,FMT='(1x," Horizontal cell number = ",2i8)')  NC,  NCL
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic cell No.s = ",2i8)')  NGLo, NArc
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic bndy No.s = ",2i8)')  NGLB, NArB
       WRITE(UNIT=16,FMT='(1x," North/South Polar Cels = ",2i8)')  NNor, NSou 
       WRITE(UNIT=16,FMT='(1x," Total number of U-face = ",2i8)')  NU, NFC
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic U-face No = ",2i8)')  NUGL, NUAr
       WRITE(UNIT=16,FMT='(1x," Total number of V-face = ",2i8)')  NV, NFC
       WRITE(UNIT=16,FMT='(1x," Globl/Arctic V-face No = ",2i8)')  NVGL, NVAr
       WRITE(UNIT=16,FMT='(1x," Sub-step cell count NRLCel(0:MRL)=",i3,6i8)') NRLCel
       WRITE(UNIT=16,FMT='(1x," Sub-step Ufce count NRLUFc(0:MRL)=",i3,6i8)') NRLUFc
       WRITE(UNIT=16,FMT='(1x," Sub-step Vfce count NRLVFc(0:MRL)=",i3,6i8)') NRLVFc
       IF( Arctic ) WRITE(UNIT=16,FMT='(i3," polar parts included.")') NPol
       IF( Source ) WRITE(UNIT=16,FMT='("  Source cells No. =",i8 )') NSCR
       IF( WHPrts ) WRITE(UNIT=16,FMT='("  WHPrts cells No. =",i8 )') NPrt
       IF( Restrt ) WRITE(UNIT=16,FMT='("  Model restarts at=",i8 )') NS  

 3912 FORMAT(1x,i4,3F9.1,ES12.3)

       WRITE(16,FMT='(/1x," YS/CS/CC/BS2Lat at step of  ",i6)' )  100
       WRITE(16,FMT='(8F9.3)')  (YSLat(n), n=-NLat2,NLat2,100)
       WRITE(16,FMT='(8F9.5)')  (CSLat(n), n=-NLat2,NLat2,100)
       WRITE(16,FMT='(8F9.5)')  (CCLat(n), n=-NLat, NLat, 200)
       WRITE(16,FMT='(8F9.5)') (BS2Lat(n), n=-NLat, NLat, 200)
       WRITE(16,FMT='(/1x," First and last ICE values ")' ) 
       WRITE(16,FMT='(1x,6i8)')  1,(ICE(i, 1),i=1,4)
       WRITE(16,FMT='(1x,6i8)') NC,(ICE(i,NC),i=1,4)
       WRITE(16,FMT='(/1x," First and last ISD values ")' ) 
       WRITE(16,FMT='(1x,8i8)')  1,(ISD(i, 1),i=1,7)
       WRITE(16,FMT='(1x,8i8)') NU,(ISD(i,NU),i=1,7)
       WRITE(16,FMT='(/1x," First and last JSD values ")' ) 
       WRITE(16,FMT='(1x,9i8)')  1,(JSD(i, 1),i=1,7)
       WRITE(16,FMT='(1x,9i8)') NV,(JSD(i,NV),i=1,7)
       WRITE(16,FMT='(1x)') 

!! Open a file to store error messages if any.
       OPEN(UNIT=17,FILE='CErros.txt',STATUS='UNKNOWN',IOSTAT=nn, &
        &           ACTION='WRITE')
       IF(nn /= 0) PRINT*,' File CErros.txt was not opened! '
       WRITE(17,FMT='(1x," Message to recode number of negative water heights removed.")' )

!! Open a file to store individal terms for selected point
       OPEN(UNIT=18,FILE='CTerms.txt',STATUS='UNKNOWN',IOSTAT=nn, &
        &           ACTION='WRITE')
       IF(nn /= 0) PRINT*,' File CTerms.txt was not opened! '
       WRITE(18,FMT='(1x," Selected point ID, i, j, di, dj, h, Lon, Lat")' )
       n = Itrm 
       CNST1 = (ICE(1,n)+0.5*ICE(3,n))*DLon + ZLON
       CNST2 = (ISD(2,n)+0.5*ICE(4,n))*DLat + ZLat
       WRITE(18,FMT='(1x,6i8, 2F9.3)') n, (ICE(i,n), i=1,4), KG(n), CNST1, CNST2
       WRITE(18,FMT='(" TimeStep, Vorticity, GradientX, GradientY",  &
      &                  ", WaterHt m, VelocityU, VelocityV")')  

!  Output exact terms at 0 time step. 
       WRITE(18,FMT='(i9, 6ES11.3)') 0, (Terms(i), i=1,6) 

!! Open a file to store error l1 l2 and lmx for Hw U and V fields. 
       OPEN(UNIT=19,FILE='CEl12m.txt',STATUS='UNKNOWN',IOSTAT=nn, &
        &           ACTION='WRITE')
       IF(nn /= 0) PRINT*,' File CEl12m.txt was not opened! '

       WRITE(19,FMT='("  NT  HEl12m(3)  UEl12m(3)  VEl12m(3)  Enetp  Hwint  Vrint  Enetk ")')
!  Output initial error norms at 0 time step. 
       WRITE(19,FMT=9123) 0, HEl12m, UEl12m, VEl12m, Enetp, Hwint, Vrint, Enetk 
 9123  FORMAT (1x,i9, 15ES12.3)

!! Open a file to store water height at selected points if WHPrts is selected.
       IF( WHPrts ) THEN
         OPEN(UNIT=20,FILE='CWHPrt.txt',STATUS='UNKNOWN',IOSTAT=nn, &
        &           ACTION='WRITE')
         IF(nn /= 0) PRINT*,' File CWHPrt.txt was not opened! '

         WRITE(20,FMT='((16i8))') NPrt, (IDPrt(i), i=1, NPrt)
!  Output initial error norms at 0 time step. 
         WRITE(20,FMT=8163) 0,(Hw(IDPrt(i))+MIN(Btm(IDPrt(i)),0.0),i=1,NPrt)
       ENDIF
 8123  FORMAT (i8, (12ES11.3))
 8163  FORMAT (i8, (16F8.3))

!     Start timing and major time step loop
       CALL DATE_AND_TIME(CDate, CTime)
       WRITE(6,"(' Loop start time ',A,'  ',A)")  CTime

 TSLoop:  DO  NT=NS+1, NS+NTS

!  Interpolate face velocities and calculate kinetic energy
        CALL UVNTerpo

!  Calculate vorticity and note Vort is Vorticity*DT
        CALL Vorticty

!  Calculate kinetic energy at n time step, divided by GRVTY.
        CALL KinetcEn(UC, VC)

!  Propagation of water height to next time step
        CALL ProUNO2(Hw, Frct)

!  Topup source cells upto sea level.  JGLi03Feb2016
        IF( Source ) THEN
        DO i = 1, NSCR
           n = NSCELS(i)
           Hw(n) = MAX(0.0, FLOAT(KG(n)) )
        ENDDO
        ENDIF

!  For filling ocean test, update Hw0 for next timestep.
        IF( Init .EQ. 1 ) Hw0 = Hw

!  Calculate potential and kinetic energy gradient, divided by GRVTY.
        CALL DHDXDHDY

!  Update UC VC to next time step
        CALL UpdtUCVC(UCS, VCS)

!  Smoothing UC VC Hw by averaging scheme every NHrg steps.
        IF( MOD(NT, NHrg) .eq. 0 )   THEN 
           JAvrg = JPvrg
           IF( MOD(NT, NLrg) .eq. 0 ) JAvrg = 0
           CALL CntrAvrg(UCS)
           CALL CntrAvrg(VCS)
           IF( Arctic ) CALL BondVictr(UCS, VCS)
!  Mass average is replaced by polar biased diffusion.
!          CALL CntrAvrg(Hw )
!          IF( Arctic ) CALL BondScalr(Hw)
        ENDIF

!  Add a 20 m/s limit to velocity for filling test 1.  JGLi04Feb2016
!  Velocity ceiling suspended for other tests.         JGLi09Mar2016
        IF( Init .EQ. 1 ) THEN
            CNST6=20.0 
            DO i = 1, NC
               IF( Abs(UCS(i)) .GT. CNST6 ) UCS(i) = SIGN( CNST6, UCS(i) )
               IF( Abs(VCS(i)) .GT. CNST6 ) VCS(i) = SIGN( CNST6, VCS(i) )
            ENDDO
        ENDIF

!  Assign updated n+1 time step value
        UC = UCS
        VC = VCS

!  Filter out NaN UC VC if any.  JGLi26Jul2022
        ii=0
        jj=0
!$OMP Parallel DO Private(i)
        DO i = 1, NC
           IF( UC(i) .NE. UC(i) ) THEN
               UC(i) = UC0(i)
               IF(MOD(NT-1,5*NWP) == 0) WRITE(18,'(" U",6i6)') ICE(:,i),KG(i)
!$OMP ATOMIC
               ii = ii + 1
           ENDIF
           IF( VC(i) .NE. VC(i) ) THEN
               VC(i) = VC0(i)
               IF(MOD(NT-1,5*NWP) == 0) WRITE(18,'(" V",6i6)') ICE(:,i),KG(i)
!$OMP ATOMIC
               jj = jj + 1
           ENDIF
        ENDDO
!$OMP END Parallel DO

!! Warning if any NaN velocity components appeared.
        IF( ( NT < NWP .OR. MOD(NT,NWP) .eq. 0 ) .AND. ( ii > 0 .OR. jj > 0 ) ) THEN
!           WRITE(6, *) " U V NaN ii, jj at NT =", ii, jj, NT
            WRITE(18,*) " U V NaN ii, jj at NT =", ii, jj, NT
        ENDIF

!  Output water height if at selected writeup time steps
        IF( (NT .LT. 10*NWP .AND. MOD(NT,NWP/2) .eq. 0)     &
      & .OR.(NT .LT. 30*NWP .AND. MOD(NT,NWP)   .eq. 0)     &
      & .OR.(NT .LT. 70*NWP .AND. MOD(NT,2*NWP) .eq. 0)     &
      & .OR. (MOD(NT,4*NWP) .eq. 0) )  THEN
            A = Hw +Btm 
            CALL WRITEOUT(A, NT, 'Hb')
!  Relative vorticity output for case 3
            IF( Init .EQ. 3 .OR. Init .EQ. 9 ) THEN
              A = (Vort - CoriF)/DT
              CALL WRITEOUT(A, NT, 'Vr')
            ENDIF
        ENDIF

!  Save UC VC every 4 NWP times.
!       IF( MOD(NT, 4*NWP) .eq. 0 )   &
!           CALL WRITEUVs(UC, VC, NT)

!  Output terms at every time step. 
        WRITE(18,FMT='(i9, 6ES11.3)') NT, (Terms(i), i=1,6) 

!  Calculate errors l1 l2 and lmax and output every 6 timesteps.
        IF( MOD(NT, 6) .eq. 0 )   THEN 
!! Calculate rotated initial field for W6 test (Case 5) before error norms.
            IF( Init .EQ. 5 ) THEN
          CALL W6HfUCVC(NT*DT, Hw0, UC0, VC0)
            ENDIF
!! Calculate integraton of field differences from initial fields.
          CALL Errol12m(Hw-HW0, HEl12m)
          CALL Errol12m(UC-UC0, UEl12m)
          CALL Errol12m(VC-VC0, VEl12m)

!! Calculate total potential and kinetic energy and integration. 
          CALL TotlEngy
          CALL Integral( Enpt, Entgrl )
          Enetp = Entgrl - Enpt0
          CALL Integral( EnkH, Entgrl )
          Enetk = Entgrl 

!! Total water volume integration.
          CALL Integral( Hw, Hwint )

!  Relative vorticity integration.
          A = (Vort - CoriF)/DT
          CALL Integral(A, Vrint)

          WRITE(19,FMT=9123) NT, HEl12m, UEl12m, VEl12m, Enetp, Hwint, Vrint, Enetk 

!  Update AKHDT2 with ramp factor upto 24*Mhr.   JGLi09Aug2024
!         CNST = 0.4+0.6*NT/FLOAT(24*MHr)
!         AKHDT2 = MIN(1.0, CNST)*AKHDMX
!!  Use new diffusivity initial ratio and increase time scale.  JGLi23Sep2024
          AKHDT2 = AKHDMX*( 1.0 - (1.0-DFR0)*EXP(-NT/(DFHr*MHr)) )

        ENDIF

        IF( WHPrts .AND. MOD(NT, 2) .eq. 0 )  THEN 
          WRITE(20,FMT=8163) NT,(Hw(IDPrt(i))+MIN(Btm(IDPrt(i)),0.0),i=1,NPrt)
        ENDIF

!!  End of time step loop
      ENDDO  TSLoop

       CALL DATE_AND_TIME(CDate, CTime)
       READ(STime, *) CNST1
       READ(CTime, *) CNST6
       CNST = CNST6 - CNST1 
       WRITE(UNIT= 6,FMT="(1x,' End time date ',A10,2x,A10,F12.1)") CTime, CDate, CNST 
       WRITE(UNIT=16,FMT="(1x,' End time date ',A10,2x,A10,F12.1)") CTime, CDate, CNST 

!  Close output files
       CLOSE(16)
       CLOSE(17)
       CLOSE(18)
       CLOSE(19)
       CLOSE(20)

       WRITE(UNIT= 6,FMT="(1x,' SWEsnSMC completed!')") 

       END PROGRAM SWEsnSMC 
!  End of main program

