!!
!! Module for variables used in the SWEs model on a SMC grid.  
!! First created:  JGLi12Apr2018
!! Last modified:  JGLi26Jul2024
!!
      MODULE SWEsCnstMD
          IMPLICIT NONE

!! Parameters to be read from InpFile:
       CHARACTER(LEN=16):: GridName='Medi36125' 
       CHARACTER(LEN=80):: DataPath='../Med36125/DatGMC/' 
       INTEGER:: NCL,  NFC,  MRL,  Itrm=1, NPrt=0, &
                 NLon, NLat, NPol, Init=0,  &
                 NTS,  NWP,  NHrg, NLrg
       REAL   :: ZLon, ZLat, DLon, DLat,  &
                 DFR0, DT,   AKHM, CBFr,  &
                 PLon, PLat, PAvr, Beta  
       LOGICAL:: Arctic, Source, WHPrts, Restrt

!! Model variables to be defined and working variables.
       INTEGER:: NS, NT, ND, NE, NF, NA, NB, NP, NR, NBdy,  & 
                 N1, N2, N4, N8, N9, MHr, MFct, NSCR, N16,  &
                 NU1, NV1, NU2, NV2, NU4, NV4, NU8, NV8, NU9, NV9, & 
                 NC, NU, NV, NGLo, NGLA, NGLB, NArc, NArA, NArB,   &
                 NUGL, NUAr, NVGL, NVAr, NNor, NSou, NLat2, &
                 icl, jcl, iuf, juf, ivf, jvf, LvR, Lvm,    & 
                 JEqut, JAvrg, JPvrg, NU16, NV16 

       REAL   :: CMX, CTT, DY, DYR, DX0, AKHDT2, AKHDMX, Frct, UMX,  &
                 Hwint, Vrint, Entgrl, Enpt0, Enetp, Enetk, Terms(6)=0.0
       REAL, DIMENSION(3)::  HEl12m=0.0, UEl12m=0.0, VEl12m=0.0 

!! Allocatable arrays, depending on InpFile parameters.
       INTEGER, DIMENSION(:),   ALLOCATABLE:: ICE3, ICE4, KG, NSCELS, &
                           NRLCel, NRLUFc, NRLVFc, MBGLo, MBArc, IDPrt

       INTEGER, DIMENSION(:,:), ALLOCATABLE:: ICE, ISD, JSD

       REAL, DIMENSION(:), ALLOCATABLE:: A, C, D, F, Hw, AU, AV,  &
                           DX, DXR, UC, VC, Hw0, UC0, VC0, Btm,   &
                           CSAnC, SNAnC, AngCD, RCELA, CoriF,     &
                           Enpt, Enkn, EnkH, Vort, DHDX, DHDY,    &
                           YSLat, YCLat, CSLat, CCLat, BS2Lat,    & 
                           UCL, UCS, VCS, BFrc, HCel
       REAL, DIMENSION(:), ALLOCATABLE ::   U, UT, V, VT, FU, FV, &
                           FX, FY, CSAnU, SNAnU, CSAnV, SNAnV


!! Rotated pole to define Arctic part reference direction and polar cell
!! radius in unit of base dy. 
       REAL,PARAMETER:: PoLAT= 0.0, PoLON=-180.0, PCRDY=1.0,  &
!! Pie value and degree-radian conversion parameters.
        &        Pie=3.141592654, D2RAD=Pie/180.0, ZENO=1.0E-32 

!! Some physical and atmospheric constants
       REAL,PARAMETER:: GRVTY=9.80616, CPVAP=1004.5, RDRY=287.05,    &
        &    CT0=273.16,CALJO=4.1868,PATM=101325.0, ANGUL=7.292E-5,  &
        &    EPSLN=0.6220, CLIGHT=2.99792458E8, Omega2=1.4584E-4,    &
        &    REARTH=6.37122E6, Agu36=4.8481E-5, Agu12d=6.0602E-6,    &
        &    GmDT=0.0, DepMn=5.5, DFHr=12.0  
!!  GmDT is set to be zero and CBFr is moved as input variable.  JGLi21Mar2024

!! Default integers for any loop count or temporary use. 
       INTEGER:: I,II,IJ,IJK,J,JJ,JK,K,KK,L,LL,LM,LMN,M,MM,MN,N,NN

!! Date and time for timing of program by calling Date_And_Time
       CHARACTER(LEN=10):: CDate, CTime, STime

!! Other character variables.
       CHARACTER(LEN=1)::XEXT(6)=(/'S','B','W','E','C','M'/)

!! Default run name and date and input file.
       CHARACTER(LEN=26):: RUNDATE=' SMC251040 12Dec2023 ',  &
                           InpFile='./SWEsInput.txt'
!!

       CONTAINS

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

! 999 PRINT*, ' Sub LLTOEQANGLE ended.'

      RETURN
      END SUBROUTINE LLTOEQANGLE
!Li

!! End of module SWEsCnstMD
      END MODULE SWEsCnstMD

