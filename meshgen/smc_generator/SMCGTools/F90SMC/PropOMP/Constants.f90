!!
!  This module is for SMC Med36125 grid setup and model configuration. 
!  It is for a propagation test and is written in FORTRAN 90 format. 
!                     J G Li   18 Sep 2019
!  Modified for SMC61250 grid as a SMCGTools demonstration test.
!                     J G Li   18 Oct 2021
!!
                      
      MODULE Constants
!         USE mpi
          USE omp_lib
          IMPLICIT NONE

!! Parameters to be read from InpFile:
       CHARACTER(LEN=16):: GridName='SMC61250' 
       CHARACTER(Len=80):: DataPath='../DatGMC/'
       INTEGER:: NCL,  NFC,  MRL,  &
                 NLon, NLat, NPol, & 
                 NDir, NFrq, NTS, NWP  
       REAL   :: ZLon, ZLat, DLon, DLat,  &
                 DTG,  DTCFL,SSLat,SNLat 
       LOGICAL:: Arctic = .True.  

!! Model variables to be defined and working variables.
       INTEGER:: NS, NT, ND, NE, NF, NA, NB, NP, NR, NX, NY, NSEA,  & 
                 NC, NU, NV, NGLo, NGLA, NGLB, NArc, NArA, NArB,    &
                 NUGL, NUAr, NVGL, NVAr, NNor, NSou, NHr, MRFct,    &
                 NSpc
       REAL   :: CMX, CTT, DY, DYR, DX0, DTH, DThta, SWH0, Alpha,  &
                 PkFrq, SX, SY 

!! Allocatable arrays, depending on InpFile parameters.
       INTEGER, DIMENSION(:),   ALLOCATABLE:: ICE3, ICE4, KG,  &
                                NRLCel, NRLUFc, NRLVFc, MBGLo, MBArc   

       INTEGER, DIMENSION(:,:), ALLOCATABLE:: ICE, ISD, JSD

       REAL, DIMENSION(:), ALLOCATABLE:: AngArc, CLatF, CLats,   &
                           DX, DXR, RCELA, HS, HCel, DHDX, DHDY, &
                           CX, CY, DCXDX, DCXDY, DCYDX, DCYDY,   & 
                           Theta, ESIN, ECOS, EC2, ESC, ES2,     &
                           SIG, DSIP, SpecPM, Spectr, SpeGCT,    &
                           CTHG0S 

       REAL, DIMENSION(:,:),   ALLOCATABLE:: REFR, CGrp, Wnmk, DHLMT 
       REAL, DIMENSION(:,:,:), ALLOCATABLE:: WSpc 
                             
!  Some physical and atmospheric constants
       REAL,PARAMETER:: GRAV=9.806, CPVAP=1004.5, CLIGHT=2.99792458E8, &
      &                 RDRY=287.05, CT0=273.16,  CALJO=4.1868,        &
      &                 REARTH=6.371E6, PATM=101325.0, ANGUL=7.2921E-5,&
      &                 Agu36=4.8481E-5, EPSLN=0.6220  

!  Other parameter constants 
       REAL,PARAMETER:: Pie=3.141592654, RAD2D=180.0/Pie, D2RAD=Pie/180.0 

       REAL,PARAMETER:: XFR=1.1, Frqc0=0.04118, Frqc1=0.0625, DTME=36000.0, &
      &         CTMAX=0.7, CLARMN=85.0, DMIN=10.0, PCRDY=1.0, Refran=36.0, &
      &         PoLAT=0.0, PoLON=-180.0, Engy0=128.0/Pie 

! Working variables to be used 
       INTEGER:: icl, jcl, iuf, juf, ivf, jvf, LvR, Lvm 
       INTEGER:: I,II,IJ,IJK,J,JJ,JK,K,KK,KL,L,LL,LM,LMN,M,MM,MN,N,NN

       LOGICAL::  FLCTH = .true., FVERG = .false., FLCUR = .false., &
                  FLCXY = .true., FUNO3 = .false.,  FLCK = .false.

       CHARACTER(LEN=9):: FL9NM='Cn10000.d'

!      Date and time for timing of program by calling Date_And_Time
       CHARACTER(LEN=10):: CDate, CTime

!  Cell and face array files.
       CHARACTER(Len=66):: Tempath ='./'
       CHARACTER(Len=66):: InpFile ='PropInput.txt'

      END MODULE Constants

