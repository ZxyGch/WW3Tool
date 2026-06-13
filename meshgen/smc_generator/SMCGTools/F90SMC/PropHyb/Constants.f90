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
!! Adapted for UK 3km global 25km SMC36125 grid.   JGLi28Feb2014
!!
!! Adapted for global 25km G25SMC grid.   JGLi07Apr2014
!!
!! Add OpenMP directives and Arctic refraction.  JGLi08Jul2015
!!
!! Modifie for UK 2km global 16km SMC24816 grid.   JGLi09Jul2015
!!
!! Modifie for UK124SMC rotated regional grid.   JGLi12Feb2016
!!
!! Modifie for new UK124SMC rotated grid.   JGLi22Sep2016
!!
!! Modifie for new UK12HSMC rotated grid.   JGLi19Dec2016
!!
!! Adapted for refraction test.  JGLi16Feb2017
!!
!! Add READCELL sub to simplify cell and face array input.  JGLi19Apr2017
!!
!! Expand spectrum to 2-D (NDIR, NFRQ).    JGLi20Apr2017 
!!
!! Adapted for UK12H on Cray for OpenMP test.    JGLi23Nov2017 
!!
!! Add hybrid MPI-OpenMP lines for hybrid test.   JGLi12Dec2017 
!!
!! Modified for Med36125 grid propagation test.   JGLi09Jul2019 
!!
!! Move out loop indices and local variables.   JGLi23Oct2019 
!!
!! Finalised for WW3 Memory arrangement model.  JGLi31Oct2019
!!
!! Update Arctic part and add SMC36125 model.  JGLi06Nov2019
!!
!! Test SJpn/Hawa cells in new SMC36125 model.  JGLi28Jan2021
!!
                      
      MODULE Constants
          USE mpi
          USE omp_lib
          IMPLICIT NONE

! Parameters fixed in the program
       INTEGER,PARAMETER::NCL=600000, NFC=645000, NBDY=256, NPol=1,  &
          &               NLat=6140, NLon=8192, MNDPTH=5, MRL=4,   & 
!      INTEGER,PARAMETER::NCL=400000, NFC=410000, NBDY=384, NPol=0,  &
!         &               NLat=1344, NLon=1458, MNDPTH=5, MRL=2,   &
!      INTEGER,PARAMETER::NCL=30000, NFC=36000, NBDY=100, NPol=0,  &
!         &               NLat=6144, NLon=8192, MNDPTH=5, MRL=4,   &
          &               NDir=36, NFrq=30, NSpc=NDir*NFrq, MPIBUF=6 

       REAL,PARAMETER:: Pie=3.141592654, RAD2D=180.0/Pie, D2RAD=Pie/180.0, PCRDY=1.0 

!      REAL,PARAMETER:: XFR=1.1, Frqc0=0.04118, CTMAX=0.7, DTME=3600.0, &
       REAL,PARAMETER:: XFR=1.1, Frqc0=0.04118, CTMAX=0.7, DTME=36000.0, &
      &                 CLARMN=85.0, DMIN=10.0, Refran=36.0    

       REAL,PARAMETER:: PoLAT= 0.0, PoLON=-180.0, DLON=0.0439453125, DLAT=0.029296875, &
         &              ZrLAT= 0.0, ZrLON=-DLON*0.5, SpSouLat=-50.0, SpNorLat=45.0   
!      REAL,PARAMETER:: PoLAT= 0.0, PoLON=-180.0, DLON=0.029296875, DLAT=0.019531250, &
!      REAL,PARAMETER:: PoLAT= 37.50, PoLON= 177.50, DLON=0.013500, DLAT=0.013500,   &
!        &        ZrLAT=-7.300950, ZrLON=-10.896250, SpSouLat=-4.6, SpNorLat=8.2    
!      REAL,PARAMETER:: ZrLAT=0.0, ZrLON=0.0, DLON=0.0439453125, DLAT=0.029296875, &
!        &              PoLAT=0.0, PoLON=-180.0, SpSouLat=35.0, SpNorLat=40.0   

!      REAL,PARAMETER:: DT= 60.0, DTR=1.0/DT, DTF=6.0, AKH=9000.0
!      REAL,PARAMETER:: DTG=600.0, DTR=1.0/DTG, DTCFL=60.0 
       REAL,PARAMETER:: DTG=900.0, DTR=1.0/DTG, DTCFL=150.0 

!  Writeup interval and model run time in hours.
       INTEGER,PARAMETER:: NHr=INT(3600.0/DTG), NWP=6*NHr, NTS=360*NHr, NDay=1700 

!  Some physical and atmospheric constants
       REAL,PARAMETER:: GRAV=9.806,CPVAP=1004.5,RDRY=287.05, &
      &                 CT0=273.16,CALJO=4.1868,PATM=101325.0,ANGUL=7.2921E-5,  &
      &                 EPSLN=0.6220,CLIGHT=2.99792458E8, GeoPie=3.141592654,   &
      &                 REARTH=6.371E6, Agu36=4.8481E-5 

! Array variables to be used for data storage

       REAL::  AMG, CMX, CTT, UMX, DY, DYR, DX0, DTH, DThta, SWH0, Alpha
       REAL::  CGCMX, CRFMX, PkFrq, BACANGL, SX, SY
       REAL, DIMENSION(-9:NCL):: C, D, DX, DXR, RCELA
       REAL, DIMENSION(-9:NCL):: HCel, DHDX, DHDY, AngCD, ELaCD, CLats, CTHG0S 
       REAL, DIMENSION(-9:NCL):: DW, CX, CY, DCXDX, DCXDY, DCYDX, DCYDY
       REAL, DIMENSION( NDir ):: Theta, ESIN, ECOS, EC2, ESC, ES2, Spectr, SpeGCT
       REAL, DIMENSION( 0:NFrq+1 )::  SIG, DSIP, SpecPM 
       REAL, DIMENSION( 0:NFrq+1, -9:NCL)::  REFR, CGrp, Wnmk
       REAL, DIMENSION(NFC)::        CLatF
       REAL, DIMENSION(NDir,NCL)::   DHLMT

       INTEGER:: NS, NE, NA, NB, NR, NX, NY, NSEA, MRFct 
       INTEGER:: NC, NU, NV, NGLo, NBGL, NArc, NBAC, &
      &          NUGL, NUAr, NVGL, NVAr, NNor, NSou
       INTEGER, DIMENSION(5,-9:NCL)::  ICE
       INTEGER, DIMENSION(  -9:NCL)::  ICE3, ICE4
       INTEGER, DIMENSION(3:7,NFC)::  ISD
       INTEGER, DIMENSION(2:7,NFC)::  JSD
       INTEGER, DIMENSION(0:MRL)::  NRLCel, NRLUFc, NRLVFc
       INTEGER, DIMENSION( NBDY)::  MBGlo, MBArc
       INTEGER, DIMENSION( NSpc)::  IAPPRO 
       INTEGER, DIMENSION(MPIBUF)::  BSTAT, BISPL

!  MPI related varialbes
       INTEGER:: MPI_COMM_WAVE, IAPROC, NAPROC, NAPFLD, IERR_MPI, & 
                 NSEAL, NSEALM, NSPEC,  NRQSG1, NRQSG2, IBFLOC,   &
                 NRQRS, NRQMAX, IRQGO,  NRQGO2, ISTAT,  ISPLOC,   &
                 WW3_SPEC_VEC, WW3_FIELD_VEC,   ierr,   NSPLOC

       INTEGER:: malloc, myrank, nprocs, nthreads, provided
       INTEGER:: mpistat(MPI_STATUS_SIZE)         ! MPI status for Recv
!      INTEGER,PARAMETER:: required=MPI_THREAD_FUNNELED 
       INTEGER,PARAMETER:: required=MPI_THREAD_SERIALIZED 
       CHARACTER(len=MPI_MAX_PROCESSOR_NAME):: pname   ! Processor name

!  MPI related allocatables. 
       REAL, Allocatable, Dimension(:)    :: REALLOC1, BACSPEC,  &
                                             ANGARC, HS, XHS
       REAL, Allocatable, Dimension(:,:)  :: REALLOC2, REALandN, VA,  &
                                             SPCBAC, GSTORE, SSTORE 

       INTEGER, Allocatable, Dimension(:)  :: INTALLOC,IRQGO2,STATIO, &
                                              ICLBAC 
       INTEGER, Allocatable, Dimension(:,:):: INTALLO2,STATI2,STATCO, &
                                              IRQSG1,  IRQSG2 

!  Logical variables and file paths 
       LOGICAL:: Arctic = .true., FVERG = .true., FLCUR = .false., &
                  FLCXY = .true., FLCTH = .true.,  FLCK = .true.
       LOGICAL:: FLGMPI(0:6) = .FALSE. 

!  Date and time for timing of program by calling Date_And_Time
       CHARACTER(LEN=10):: CDate, CTime
       CHARACTER(LEN= 9):: FL9NM='Cn10000.d'

!  Cell and face array files.
       CHARACTER(Len=32) :: CelPath='./'
!      CHARACTER(LEN=26)::  CelFile='Med36125Cel0.dat', &
!       &                   ISdFile='Med325GISide.dat', &
!       &                   JSdFile='Med325GJSide.dat', &  
!      CHARACTER(LEN=26)::  CelFile='UK12HSMCels.dat',  &
!       &                   ISdFile='UK12HGISide.dat',  &
!       &                   JSdFile='UK12HGJSide.dat',  &  
!       &                   ArcFile, AISFile, AJSFile       
       CHARACTER(LEN=26)::  CelFile='S36125MCels.dat',  &
        &                   ISdFile='S36125ISide.dat',  &
        &                   JSdFile='S36125JSide.dat',  &  
        &                   ArcFile='S36125MBArc.dat',  &
        &                   AISFile='S36125AISid.dat',  &
        &                   AJSFile='S36125AJSid.dat' 

!      CHARACTER(LEN=20):: RUNDATE=' G25SMCAr 07Apr2014 '
!      CHARACTER(LEN=20):: RUNDATE=' SMC24816  2Sep2014 '
!      CHARACTER(LEN=20):: RUNDATE=' Med36125  9Jul2019 '
!      CHARACTER(LEN=20):: RUNDATE=' UK12HSMC 31Oct2019 '
       CHARACTER(LEN=20):: RUNDATE=' SMC36125 28Jan2021 '

      END MODULE Constants


