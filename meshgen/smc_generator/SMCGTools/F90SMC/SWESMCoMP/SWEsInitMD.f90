!!
!!  First created:   26 Jan 2015   Jian-Guo Li
!!  Last modified:   08 Aug 2022   Jian-Guo Li
!
       MODULE SWEsInitMD
!
!      This module is a collection of subroutines to initialize the 
!      model of shallow-water equations on Spherical Multiple-Cell 
!      (SMC) grid for different tests.         JGLi15Nov2019
!
!      Subroutines included are:
!      INITUCVC    ## Zonal rotation flow.
!      FilOcean    ## Filling oceans with river sources.
!      W2HfUCVC    ## Williamson etal (1992) test 2
!      TsunamHw    ## Initial disturbance tsunami waves.
!      GsHfUCVC    ## Galewsky etal. (2004) zonal jet test.
!      W5HfUCVC    ## Williamson etal (1992) test 5 and
!      W6HfUCVC(DTNTS, Hw6t, Uw6t, Vw6t)  ## test 6.
!
!  Use omp_lib for OpenMP functions if switched on.   JGLi10Jan2018
!$       USE omp_lib
! 

       CONTAINS

! Subroutine that initialise UC VC for shallow water equation model.
!  Solid rotation velocity is used at present. 
!  First created:   26 Jan 2015   Jian-Guo Li
!  Last modified:   17 Dec 2019   Jian-Guo Li

      SUBROUTINE INITUCVC
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
       REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
       REAL ::  DfPolat, DfPolon
       LOGICAL::  Rotated = .true. 

!!  Face velocities are in unit of basic cell length and time step or 
!!  divided by the grid velocity BX/DT or BY/DT.
!!  Cell centre velocities are, however, in conventional unit of m/s.

!!    Half-grid increment
       CNST1=DLon*0.5
       CNST2=DLat*0.5
 
       ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )
       WRITE(6,*) " Calculating UC, VC component ..."

!!  Loop over all cells, excluding polar cells 
       DO L=1, NC-NPol

!!  Cell centre latitude equal to south side plus half cell height.
!!  Cell centre longitude with half cell width increase from West side.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float(ICE(1,L))*DLon + CNST1*Float(ICE(3,L)) + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L)) + ZLat

       END DO

!! AnglD will be undefined at poles as no local east at poles.  So polar
!! cell centres are shifted slightly off the Poles.
       IF( NPol .GT. 0 ) THEN
       DO L=NC-NPol+1, NC
         XLon(L)= Float( ICE(1,L) )*DLon + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat 
       ENDDO
       ENDIF

!! Convert standard lat/lon into rotated lat/lon if required. 
       IF( Rotated ) THEN
!!    Use two variables for rotated Pole as parameter PLat/Lon could
!!    not be modified within subroutine LLTOEQANGLE.
         DfPolat=PLAT
         DfPolon=PLon

         CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                   AnglD, DfPolat, DfPolon, NC)

       ELSE
!!    Simply copy standard lat-lon values.
         ELat = WLat
         ELon = XLon
         AnglD = 0.0

       END IF

!! Coriolis term is initialised with rotated latitude.
       DO L=1, NC
          CoriF(L) = Omega2*DT*SIN(ELat(L)*D2RAD)
       END DO

!! Initialise UC VC to be zero at first.
       UC=0.0
       VC=0.0

!! Specific cell centre velocity compenents in unit in m/s
       CNST7 = Agu36*REARTH

!!  Excluding polar cells
!        DO L=1, NC-NPol
!!  Loop over all cells including polar cells 
         DO L=1, NC

!!  Global part UC VC are at local east system
           IF( L .LT. NGLo ) THEN
!!  Standard U V components in unit m/s at cell centre local east.
         UC(L)= COS(ELat(L)*D2RAD)*COS(AnglD(L)*D2RAD)*CNST7
         VC(L)=-COS(ELat(L)*D2RAD)*SIN(AnglD(L)*D2RAD)*CNST7

!!  Polar regions use the rotated or map-east system.
           ELSE
!!  Standard U V component in unit m/s at cell centre.
         UC(L)= COS(ELat(L)*D2RAD)*CNST7
         VC(L)= 0.0
        
           ENDIF
 
!!  Avoid very small number output error
           IF( Abs( UC(L)) .LT. 1.0E-90 )  UC(L)=SIGN(1.0E-90,  UC(L))
           IF( Abs( VC(L)) .LT. 1.0E-90 )  VC(L)=SIGN(1.0E-90,  VC(L))

         END DO

       DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

       WRITE(6,*) " Cell centre wind initialised for NC=", NC


!!  Find maximum Courant number with cell centre speed
!!  while converting cell centre UC VC to Courant number
!!  in size-1 unit, not really the cell size for other sized cells.
!!  Note that Polar cell DX(NC) is used to store its area
!!  rather than the desired DX(NC), which has no definition.
!!  So UC(NC) is not properly specified here as Courant number.
!!  But this value is never used because no U-flux is associated 
!!  with the Polar cell.  VC(NC) is fine here as DY is cancelled
!!  at the cell update line to give the proper polar cell area.
!!  Note size-1 dx and dy are included in UC and VC, respectively.
!!  Note longitudinal merging factor is divided here as
!!  UC is only divided by the single siz-1 dx.  y-size is
!!  added because subtime steps is proportional to it.

       CNST1=0.0
       CNST2=0.0
       CNST3=0.0
       CNST4=DT/(DX0*REARTH)
       CNST5=DT/( DY*REARTH)
!!  Exclude polar cells for Courant number estimation.
       DO i=1, NC-NPol
         CNST1=Max( CNST1, Abs(UC(i))*CNST4/(CCLat(2*ICE(2,i)+ICE(4,i))*ICE(3,i)) )
         CNST2=Max( CNST2, Abs(VC(i))*CNST5/ICE(4,i) )
       ENDDO
       CMX=Max(CNST1, CNST2)
!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
       UMX=CMX/DT

       WRITE(6,*) ' Wind file conversion done, CMX=', CMX

!!  Initialise Hw(NC) with water height KG(NC)
       Hw(-9:0)=0.0
       Hw(1:NC)=FLOAT( KG(1:NC) )

! 999  PRINT*, ' Sub INITUCVC ended.'

       RETURN

      END SUBROUTINE INITUCVC


! Subroutine that initialise Coriolis factor for filling ocean test.
!  First created:   26 Jan 2015   Jian-Guo Li
!  Last modified:   25 Jul 2022   Jian-Guo Li

      SUBROUTINE FilOcean
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
       REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
       REAL ::  DfPolat, DfPolon
       LOGICAL:: Rotated = .false. 

!!  Face velocities are in unit of basic cell length and time step or 
!!  divided by the grid velocity BX/DT or BY/DT.
!!  Cell centre velocities are, however, in conventional unit of m/s.

!!    Half-grid increment
       CNST1=DLon*0.5
       CNST2=DLat*0.5
 
       ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )
       WRITE(6,*) " Calculating UC, VC component ..."

!!  Loop over all cells, excluding polar cells 
       DO L=1, NC-NPol

!!  Cell centre latitude equal to south side plus half cell height.
!!  Cell centre longitude with half cell width increase from West side.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float(ICE(1,L))*DLon + CNST1*Float(ICE(3,L)) + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L)) + ZLat

       END DO

!! AnglD will be undefined at poles as no local east at poles.  So polar
!! cell centres are shifted slightly off the Poles.
       IF( NPol .GT. 0 ) THEN
       DO L=NC-NPol+1, NC
         XLon(L)= Float( ICE(1,L) )*DLon + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat 
       ENDDO
       ENDIF

!! Convert standard lat/lon into rotated lat/lon if required. 
       IF( Rotated ) THEN
!!    Use two variables for rotated Pole as parameter PLat/Lon could
!!    not be modified within subroutine LLTOEQANGLE.
         DfPolat=PLAT
         DfPolon=PLon

         CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                   AnglD, DfPolat, DfPolon, NC)

       ELSE
!!    Simply copy standard lat-lon values.
         ELat = WLat
         ELon = XLon
         AnglD = 0.0

       END IF

!! Coriolis term factor use rotated grid if any. 
       DO L=1, NC
          CoriF(L) = Omega2*DT*SIN(ELat(L)*D2RAD)
       END DO
       WRITE(6,*) " Coriolis factor initialised for NC=", NC

!! Filling ocean test start with source at rest.
       UC=0.0
       VC=0.0

       DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
       CMX=0.0
       UMX=CMX/DT

!!  Initialise Hw(NC) to be zero for ocean filling experiment.  JGLi12Apr2018
       Hw=0.0
       WRITE(6,*) '  Water height Hw(NC/2) initialised to be ', Hw(NC/2)
 
!!  River source cells for filling the oceans.  JGLi11Nov2016
       IF( Source ) THEN
       OPEN(UNIT=9, FILE=TRIM(DataPath)//TRIM(GridName)//'Srce.dat',  &
            STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, TRIM(GridName)//'Srce.dat was not opened! '
       READ (9,*) NSCR
       ALLOCATE( NSCELS(NSCR) )
       READ (9,*) NSCELS
       CLOSE(9)
       PRINT*, TRIM(GridName)//'Srce.dat read done ', NSCR, NSCELS(1), NSCELS(NSCR)

!  Fill source cells upto sea level
       DO i = 1, NSCR
          n = NSCELS(i)
          Hw(n) = FLOAT( KG(n) )
       ENDDO

!! End of setting up source cells
       ENDIF

! 999  PRINT*, ' Sub FilOcean ended.'

       RETURN

      END SUBROUTINE FilOcean


!! Subroutine to initialise hw, corif, UC, VC for Williamson Case 2.
      SUBROUTINE W2HfUCVC
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7,CNST8,CNST9
        REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
        REAL ::  DfPolat, DfPolon,  GH0=2.94E4

!!  Initialise Hw(NC) to be zero. 
        Hw=0.0
 
!!    Default ocean bottom at about -3000 m
        Btm(1:NC) = -GH0/GRVTY

!!    Half-grid increment
        CNST1=DLon*0.5
        CNST2=DLat*0.5

!  Set speed constant with angular speed of 12 day per cycle
        CNST6 = Agu12d*REARTH
!! Corrected initial water height without u*u/2 term.  JGLi25May2016
        CNST7 =(Omega2*REARTH + CNST6)*CNST6*0.5

        ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )
        WRITE(6,*) " Calculating UC, VC component ..."

!!  Loop over all cells, excluding polar cells 
        DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLon
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

        END DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
        IF( NPol .GT. 0 ) THEN
        DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
        ENDDO
        ENDIF

!!  Choose rotated pole for Williamson case 2 test.
        DfPolat=PLat
        DfPolon=PLon

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
        CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
                         AnglD, DfPolat, DfPolon, NC)

!!  Cell centre U V for advective flux update.
!!  Set boundary cell velocity to be zero
        UC(-9:0)=0.0
        VC(-9:0)=0.0

!!  Loop over all cells including polar cells 
        DO L=1, NC

!!  Standard U V components in unit m/s at cell centre local east.
         UC(L)= COS(ELat(L)*D2RAD)*COS(AnglD(L)*D2RAD)*CNST6
         VC(L)=-COS(ELat(L)*D2RAD)*SIN(AnglD(L)*D2RAD)*CNST6

!!  Initial water height and Coriolis factor by rotation pole
         CNST5=SIN(ELat(L)*D2RAD)
         HW(L)=( GH0 - CNST7*CNST5*CNST5 )/GRVTY 
         CoriF(L) = Omega2*DT*CNST5

        END DO

!!  Resign polar cell UCL to be zero 
        IF(NPol .GT. 0)   UCL(NC-NPol+1:NC) = 0.0

!!  Convert local east UC VC to map-east system for polar regions
        IF( Arctic )  THEN 
!!    Note AngC is only defined for Arctic cells.
        DO i=NGLo+1,NC
          AU(i)= UC(i)*CSAnC(i) - VC(i)*SNAnC(i)
          AV(i)= VC(i)*CSAnC(i) + UC(i)*SNAnC(i)
        ENDDO
        DO i=NGLo+1,NC
          UC(i) = AU(i)
          VC(i) = AV(i)
        ENDDO
        ENDIF

        WRITE(6,*) " Cell centre wind initialised for NC=", NC

!!  Find maximum Courant number with cell centre speed
        CNST1=0.0
        CNST2=0.0
        CNST3=0.0
        CNST4=DT/(DX0*REARTH)
        CNST5=DT/( DY*REARTH)
!!  Exclude polar cells for Courant number estimation.
        DO i=1, NC-NPol
         CNST1=Max( CNST1, Abs(UC(i))*CNST4/(CCLat(2*ICE(2,i)+ICE(4,i))*ICE(3,i)) )
         CNST2=Max( CNST2, Abs(VC(i))*CNST5/ICE(4,i)  )
        ENDDO
        CMX=Max(CNST1, CNST2)
!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
        UMX=CMX/DT

        WRITE(6,*) ' Wind file conversion done, CMX=', CMX

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy*DT = (2.0*Agu12d+ Omega2)*SIN(ELat(L)*D2RAD)*DT
        L = Itrm
        Terms(1)=(2.0*Agu12d + Omega2)*SIN(ELat(L)*D2RAD)*DT
!!  H plus u^2/(2g) Gradients are given as
        CNST =SIN((90.0-PLat)*D2RAD)
        CNST0=COS((90.0-PLat)*D2RAD) 
        CNST1=SIN(XLon(L)*D2RAD)
        CNST2=COS(XLon(L)*D2RAD)
        CNST3=SIN(WLat(L)*D2RAD)
        CNST4=COS(WLat(L)*D2RAD) + ZENO
        CNST5= DT*CNST6*Agu12d
        CNST8=-CNST5 -DT*CNST6*Omega2
        CNST9=SIN(ELat(L)*D2RAD)
        WRITE(6,'(1x," Exact term sin cos values")') 
        WRITE(6,'(8F9.5)') CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST9
        Terms(2)=CNST8*CNST9*CNST1*CNST +   &
           CNST5*(CNST0+CNST2*CNST3*CNST/CNST4)*(-CNST1)*CNST3*CNST + &
           CNST5*(CNST1*CNST)*CNST2*CNST/CNST4
        Terms(3)=CNST8*CNST9*(CNST2*CNST3*CNST + CNST4*CNST0) +   &
                 CNST5*(CNST4*CNST0+CNST2*CNST3*CNST)*   &
                       (-CNST3*CNST0+CNST2*CNST4*CNST) 
        Terms(4)=Hw(L)
        Terms(5)=UC(L)
        Terms(6)=VC(L)

!! Free allocated memory.
        DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

! 999   PRINT*, ' Sub W2HfUCVC ended.'

        RETURN
      END SUBROUTINE W2HfUCVC 


!! Subroutine to initialise hw, corif, UC, VC for Indian Ocean tsunami.
      SUBROUTINE TsunamHw
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
       REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
!      REAL:: tsulon=95.854, tsulat=3.316, tsurds=1.0, tsuhit=10.0
!! New tsunami test in Medi36125 model, source off Sicily Island near Mt Etna.
       REAL:: tsulon=16.000, tsulat=37.000, tsurds=0.8, tsuhit=5.0
!      INTEGER, Dimension(2)::  NTsunm = (/ 24049, 24070 /)
       INTEGER, Dimension(2)::  NTsunm = (/ 26394, 26432 /)

!!  Half-grid increment
       CNST1=DLon*0.5
       CNST2=DLat*0.5

       ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )

!!  Loop over all cells, excluding polar cells 
       DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

       END DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
       IF( NPol .GT. 0 ) THEN
       DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
       ENDDO
       ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
!      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
!     &                 AnglD, DfPolat, DfPolon, NC)

!!  No need for rotation.
       ELon = XLon
       ELat = WLat
       AnglD = 0.0

!!  Cell centre U V for advective flux update.
!!  Set boundary cell velocity to be zero
!      UC(-9:0)=0.0
!      VC(-9:0)=0.0
       UC=0.0
       VC=0.0

!!  Initialise Hw(NC) to be equal to mean sea level. 
       Hw=0.0
       WHERE( Btm < 0.0) Hw = -Btm 
 
!!  Use selected 4 size-4 cells for tsunami disturbance
       L = NTsunm(1) 
       DO i = 0, 1
          Hw(L+i) = Hw(L+i) - tsuhit
       END DO
       L = NTsunm(2) 
       DO j = 0, 1
          Hw(L+j) = Hw(L+j) + tsuhit
       END DO
!!  W-E tsunami disturbance.   JGLi02Jan2020
!      DO j = 1, 2
!         L = NTsunm(j) 
!      DO i = 0, 1
!         Hw(L+i) = Hw(L+i) + (2*i-1)*tsuhit
!      END DO
!      END DO
       
!!  Loop over all cells to initialise tsunami disturbance.
!      DO L=1, NC

!!  Work out hill radus from ELat and ELon
!        CNST3 = ELon(L) - tsulon
!        IF( CNST3 .GT.  180.0 ) CNST3 = CNST3 - 360.0 
!        IF( CNST3 .LT. -180.0 ) CNST3 = CNST3 + 360.0 

!        CNST4 = ELat(L) - tsulat
!        CNST6 = SQRT( CNST3*CNST3 + CNST4*CNST4 )

!!  Add tsunami disturbance to initial water height.  Half up half down.
!        IF( CNST6 .LT. tsurds ) THEN
!           Hw(L) = Hw(L) + tsuhit*(1.0 - CNST6/tsurds)
!           Hw(L) = Hw(L) + tsuhit*(1.0 - CNST6/tsurds)*SIGN(1.0, CNST3)
!        ENDIF 

!      END DO

!!  Initial Coriolis factor by rotated latitude.
       DO L=1, NC
         CoriF(L) = Omega2*DT*SIN(ELat(L)*D2RAD)
       END DO

       DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

!!  Convert local east UC VC to map-east system for polar regions
      IF( Arctic )  THEN 
!!    Note AngC is only defined for Arctic cells.
        DO i=NGLo+1,NC
          AU(i)= UC(i)*CSAnC(i) - VC(i)*SNAnC(i)
          AV(i)= VC(i)*CSAnC(i) + UC(i)*SNAnC(i)
        ENDDO
        DO i=NGLo+1,NC
          UC(i) = AU(i)
          VC(i) = AV(i)
        ENDDO
      ENDIF

      WRITE(6,*) " Cell centre wind initialised for NC=", NC

!!  Find maximum Courant number with cell centre speed
      CNST1=0.0
      CNST2=0.0
      CNST3=0.0
      CNST4=DT/(DX0*REARTH)
      CNST5=DT/( DY*REARTH)
!!  Exclude polar cells for Courant number estimation.
      DO i=1, NC-NPol
         CNST1=Max( CNST1, Abs(UC(i))*CNST4/(CCLat(2*ICE(2,i)+ICE(4,i))*ICE(3,i)) )
         CNST2=Max( CNST2, Abs(VC(i))*CNST5/ICE(4,i)  )
      ENDDO
      CMX=Max(CNST1, CNST2)
!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
      UMX=CMX/DT
      WRITE(6,*) ' Wind file conversion done, CMX=', CMX

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy and gradients are skipped for case 5. 
      L = Itrm
      Terms(4)=Hw(L)
      Terms(5)=UC(L)
      Terms(6)=VC(L)

! 999  PRINT*, ' Sub TsunamHw ended.'

      RETURN
      END SUBROUTINE TsunamHw 


!! Subroutine to initialise hw, corif, UC, VC for Galewsky etal (2004) test.
      SUBROUTINE GsHfUCVC(ICase)
        USE SWEsCnstMD
        IMPLICIT NONE
        INTEGER, INTENT(IN):: ICase
        REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
        REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
        REAL ::  DfPolat, DfPolon
        REAL ::  Gsh0=10000.0, Gshd, Gsu0=80.0, Gsp0=Pie/7.0, Gsln=270.0,  &
                 Gsp1=(0.5 - 1.0/7.0)*Pie,  Gsp2=Pie/4.0,  GsPh=120.0
        REAL, DIMENSION( -NLat:NLat )::  GsU, GsH, GsC 

!!  Initialise Hw(NC) to be zero. 
      Hw=0.0

!!  Calculate Galewsky etal (2004) initial U and H
      GsU = 0.0
      GsH = Gsh0
      CNST = Gsp1 - Gsp0
      CNST5 = Gsu0*exp( 4.0/(CNST*CNST) )
      CNST6 = 0.5*REARTH/GRVTY
      DO n=-NLat, NLat
         CNST1 = YCLat(n)*D2RAD 
         IF( Gsp0 .LT. CNST1  .AND.  CNST1 .LT. Gsp1 ) THEN
           CNST2 = (CNST1 - Gsp0)*(CNST1 - Gsp1)
           GsU(n) = CNST5*exp(1.0/CNST2)
           CNST3 = Omega2*SIN(CNST1)
           GsH(n) = GsH(n-1)-CNST6*GsU(n)*(CNST3+GsU(n)*TAN(CNST1)/REARTH)*DY
         ELSE IF(n .GT. 0) THEN
           GsH(n) = GsH(n-1)
         ENDIF
      ENDDO

!!  Adjust GsH0 by integration of initial steady Hw
      DO L=1, NC
         
!!  Cell centre index for GsH(n)
         n = 2*ICE(2,L) + ICE(4,L) 
!!  Initial water height and Coriolis factor by rotation pole
         HW(L)= GsH(n) 
      END DO

!!  Integrate Hw
!     CALL Integral( Hw, CNST )
!   The sub Integral is no longer used after setting Gshd directly.

!!  Adjustment to GsH0 so that integration is equal to 4*Pie*10000
!     Gshd = Gsh0 - 0.25*CNST/Pie
      Gshd = 158.49 
      WRITE(6,*) " Gsh0 adjustment above 10km = ", Gshd

!!    Choose rotated pole for initial test field.
      DfPolat=PLat
      DfPolon=PLon

!!    Half-grid increment
      CNST1=DLon*0.5
      CNST2=DLat*0.5

!!    Default ocean bottom at minimum GsH
      Btm(1:NC) = -GsH(NLat) -Gshd

      ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )
      WRITE(6,*) " Calculating UC, VC component ..."

!!  Loop over all cells, excluding polar cells 
      DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

      END DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
      IF( NPol .GT. 0 ) THEN
      DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
      ENDDO
      ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NC)

!!  Cell centre U V for advective flux update.
!!  Set boundary cell velocity to be zero
      UC(-9:0)=0.0
      VC(-9:0)=0.0

!!  Loop over all cells including polar cells 
      DO L=1, NC
         
!!  Cell centre index for GsU(n)
         n = 2*ICE(2,L) + ICE(4,L) 

!!  Minimum longitude distance from hill centre Gsln 
         CNST3 = XLon(L) - Gsln
         CNST7 = MIN( ABS(CNST3), ABS(CNST3+360.0) )

!!  Work out hill radus from ELat and ELon
         CNST3 =  3.0*CNST7*D2RAD 
         CNST4 = 15.0*(WLAT(L)*D2RAD - Gsp2) 
         CNST6 = EXP(- CNST3*CNST3 - CNST4*CNST4 )

         IF( ICase > 0 ) THEN
!!  Initial water height with disturbing field and Coriolis factor. 
             HW(L)= Gshd + GsH(n) + GsPh*CCLat(n)*CNST6 
         ELSE
!!  Exclude disturbing field for steady flow test.  JGLi15May2025
             HW(L)= Gshd + GsH(n)
         ENDIF

!!  Initial UC VC in unit m/s and Coriolis factor at cell centre local east.
         UC(L)= GsU(n)
         VC(L)= 0.0 
         CNST5=SIN(ELat(L)*D2RAD)
         CoriF(L) = Omega2*DT*CNST5

      END DO

!!  Resign polar cell UCL to be zero 
      IF(NPol .GT. 0)   UCL(NC-NPol+1:NC) = 0.0

      DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

!!  Convert local east UC VC to map-east system for polar regions
      IF( Arctic )  THEN 
!!    Note AngC is only defined for Arctic cells.
        DO i=NGLo+1,NC
          AU(i)= UC(i)*CSAnC(i) - VC(i)*SNAnC(i)
          AV(i)= VC(i)*CSAnC(i) + UC(i)*SNAnC(i)
        ENDDO
        DO i=NGLo+1,NC
          UC(i) = AU(i)
          VC(i) = AV(i)
        ENDDO
      ENDIF

      WRITE(6,*) " Cell centre wind initialised for NC=", NC

!!  Find maximum Courant number with cell centre speed
      CNST1=0.0
      CNST2=0.0
      CNST3=0.0
      CNST4=DT/(DX0*REARTH)
      CNST5=DT/( DY*REARTH)
!!  Exclude polar cells for Courant number estimation.
      DO i=1, NC-NPol
         CNST1=MAX( CNST1, Abs(UC(i))*CNST4/(CCLat(2*ICE(2,i)+ICE(4,i))*ICE(3,i)) )
         CNST2=MAX( CNST2, Abs(VC(i))*CNST5/ICE(4,i)  )
      ENDDO
      CMX=MAX(CNST1, CNST2)
!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
      UMX=CMX/DT

      WRITE(6,*) ' Wind file conversion done, CMX=', CMX

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy and gradients are skipped for case 5. 
      L = Itrm
      Terms(4)=Hw(L)
      Terms(5)=UC(L)
      Terms(6)=VC(L)

! 999  PRINT*, ' Sub GsHfUCVC ended.'

      RETURN
      END SUBROUTINE GsHfUCVC 


!! Subroutine to initialise hw, corif, UC, VC for Williamson Case 5.
      SUBROUTINE W5HfUCVC
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
        REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
        REAL ::  DfPolat, DfPolon
        REAL ::  w5h0=5960.0,  w5u0=20.0,   w5s0=2000.0,     &
                 w5rd=20.0,    w5lmd=270.0, w5phi=30.0

!!  Initialise Hw(NC) to be zero. 
      Hw=0.0
 
!!    Choose rotated pole for Williamson case 2 test.
!!    Alpha = pie/2 case.
      DfPolat=PLat
      DfPolon=PLon

!!    Half-grid increment
      CNST1=DLon*0.5
      CNST2=DLat*0.5

!!    Default ocean bottom at -w5h0
      Btm(1:NC) = -w5h0

!! Corrected initial water height with  u*u/2 term.  JGLi06Jan2017
      CNST7 =(Omega2*REARTH + w5u0)*w5u0*0.5

      ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )
      WRITE(6,*) " Calculating UC, VC component ..."

!!  Loop over all cells, excluding polar cells 
      DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

      END DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
      IF( NPol .GT. 0 ) THEN
      DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
      ENDDO
      ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NC)

!!  Cell centre U V for advective flux update.
!!  Set boundary cell velocity to be zero
      UC(-9:0)=0.0
      VC(-9:0)=0.0

!!  Loop over all cells including polar cells 
      DO L=1, NC

!!  Work out hill radus from ELat and ELon
         CNST3 = ELon(L) - w5lmd
         CNST4 = ELat(L) - w5phi
         CNST6 = SQRT( CNST3*CNST3 + CNST4*CNST4 )

!!  Add ocean bottom hill to ocean bathymetry
         IF( CNST6 .LT. w5rd ) THEN
            Btm(L) = Btm(L) + w5s0*(1.0 - CNST6/w5rd)
         ENDIF 

!!  Standard U V components in unit m/s at cell centre local east.
         UC(L)= COS(ELat(L)*D2RAD)*COS(AnglD(L)*D2RAD)*w5u0 
         VC(L)=-COS(ELat(L)*D2RAD)*SIN(AnglD(L)*D2RAD)*w5u0 

!!  Initial water height and Coriolis factor by rotation pole
         CNST5=SIN(ELat(L)*D2RAD)
         HW(L)= -Btm(L) - CNST7*CNST5*CNST5/GRVTY 
         CoriF(L) = Omega2*DT*CNST5

      END DO

!!  Resign polar cell UCL to be zero 
      IF(NPol .GT. 0)   UCL(NC-NPol+1:NC) = 0.0

      DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

!!  Convert local east UC VC to map-east system for polar regions
      IF( Arctic )  THEN 
!!    Note AngC is only defined for Arctic cells.
        DO i=NGLo+1,NC
          AU(i)= UC(i)*CSAnC(i) - VC(i)*SNAnC(i)
          AV(i)= VC(i)*CSAnC(i) + UC(i)*SNAnC(i)
        ENDDO
        DO i=NGLo+1,NC
          UC(i) = AU(i)
          VC(i) = AV(i)
        ENDDO
      ENDIF

      WRITE(6,*) " Cell centre wind initialised for NC=", NC

!!  Find maximum Courant number with cell centre speed
      CNST1=0.0
      CNST2=0.0
      CNST3=0.0
      CNST4=DT/(DX0*REARTH)
      CNST5=DT/( DY*REARTH)
!!  Exclude polar cells for Courant number estimation.
      DO i=1, NC-NPol
         CNST1=Max( CNST1, Abs(UC(i))*CNST4/(CCLat(2*ICE(2,i)+ICE(4,i))*ICE(3,i)) )
         CNST2=Max( CNST2, Abs(VC(i))*CNST5/ICE(4,i)  )
      ENDDO
      CMX=Max(CNST1, CNST2)
!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
      UMX=CMX/DT

      WRITE(6,*) ' Wind file conversion done, CMX=', CMX

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy and gradients are skipped for case 5. 
      L = Itrm
      Terms(4)=Hw(L)
      Terms(5)=UC(L)
      Terms(6)=VC(L)

! 999  PRINT*, ' Sub W5HfUCVC ended.'

      RETURN
      END SUBROUTINE W5HfUCVC 


!! Subroutine to initialise hw, corif, UC, VC for Williamson Case 6.
      SUBROUTINE W6HfUCVC(DTNTS, Hw6t, Uw6t, Vw6t)
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL, INTENT( IN):: DTNTS 
        REAL, INTENT(OUT), Dimension(-9:NCL):: Hw6t, Uw6t, Vw6t
        REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7,CNST8,CNST9
        REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
        REAL ::  DfPolat, DfPolon
        REAL ::  w6h0=8000.0, w6omg=7.848E-6, Amue6=2.463E-6, w6u0, ru0g 

!!  Initialise Hw(NC) to be zero. 
      Hw6t=0.0
 
!!  Time shift angle in degree
      CNST = DTNTS*Amue6/D2RAD

!!    Choose rotated pole for Williamson case 2 test.
!!    Alpha = pie/2 case.
      DfPolat=PLat
      DfPolon=PLon

!!    Half-grid increment
      CNST1=DLon*0.5
      CNST2=DLat*0.5

!!    Default ocean bottom at -w5h0
      Btm(1:NC) = -w6h0

!! Corrected initial water height without u*u/2 term.  JGLi25May2016
      w6u0 = w6omg*REARTH
      ru0g = w6u0*REARTH/GRVTY

      ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )
!     WRITE(6,*) " Calculating UC, VC component ..."

!!  Loop over all cells, excluding polar cells 
      DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
!!  Shift -CNST angle in longitude to get rotated initial field.
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLON - CNST
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

      END DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
      IF( NPol .GT. 0 ) THEN
      DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON - CNST
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
      ENDDO
      ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NC)

!!  Cell centre U V for advective flux update.
!!  Set boundary cell velocity to be zero
      Uw6t(-9:0)=0.0
      Vw6t(-9:0)=0.0

!!  Loop over all cells including polar cells 
      DO L=1, NC

!!  Use standard lat/lon for W6 velocity definitions
         CNST3 = COS(WLat(L)*D2RAD) 
         CNST6 = CNST3*CNST3
         CNST9 = CNST6*CNST6
         CNST4 = 4.0*XLon(L)*D2RAD 
         CNST7 = SIN(WLat(L)*D2RAD)
         CNST8 = CNST7*CNST7

!!  Standard U V components in unit m/s at cell centre local east.
         Uw6t(L)= ( 1.0 + CNST6*(5.0*CNST8 - 1.0)*COS(CNST4) )*w6u0*CNST3 
         Vw6t(L)=-4.0*w6u0*CNST3*CNST6*CNST7*SIN(CNST4)

!!  Initial W6 water height and Coriolis factor 
         CoriF(L) = Omega2*DT*CNST7
         Hw6t(L)= w6h0 + ru0g*( (ANGUL+0.5*w6omg)*CNST6 +  &
      &         w6omg*CNST6*CNST9*(1.25*CNST9 + 6.5*CNST6 - 8.0) +  &
      &        (w6omg+ANGUL)*CNST6*(0.2+5.0*CNST8)*COS(CNST4)/3.0 - &
      &         w6omg*CNST9*CNST9*(0.25+1.25*CNST8)*COS(2.0*CNST4) )
      END DO

!!  Release allocated variable space.
      DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

!!  Convert local east UC VC to map-east system for polar regions
      IF( Arctic )  THEN 
!!    Note AngC is only defined for Arctic cells.
        DO i=NGLo+1,NC
          AU(i)= Uw6t(i)*CSAnC(i) - Vw6t(i)*SNAnC(i)
          AV(i)= Vw6t(i)*CSAnC(i) + Uw6t(i)*SNAnC(i)
        ENDDO
        DO i=NGLo+1,NC
          Uw6t(i) = AU(i)
          Vw6t(i) = AV(i)
        ENDDO
      ENDIF

      IF(DTNTS .LT. 1.0) WRITE(6,*) " Cell centre initialised for NC=", NC

!!  Find maximum Courant number with cell centre speed
      CNST1=0.0
      CNST2=0.0
      CNST3=0.0
      CNST4=DT/(DX0*REARTH)
      CNST5=DT/( DY*REARTH)
!!  Exclude polar cells for Courant number estimation.
      DO i=1, NC-NPol
         CNST1=Max( CNST1, Abs(Uw6t(i))*CNST4/(CCLat(2*ICE(2,i)+ICE(4,i))*ICE(3,i)) )
         CNST2=Max( CNST2, Abs(Vw6t(i))*CNST5/ICE(4,i)  )
      ENDDO
      CMX=Max(CNST1, CNST2)
!!  Maximum grid speed, i.e. the ratio of speed to grid length
!!  Not necessrily the maximum speed as grid length varies.
      UMX=CMX/DT

!     WRITE(6,*) ' Wind file conversion done, CMX=', CMX

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy and gradients are skipped for case 6. 
      L = Itrm
      Terms(4)=Hw(L)
      Terms(5)=UC(L)
      Terms(6)=VC(L)

! 999  PRINT*, ' Sub W6HfUCVC ended.'

      RETURN
      END SUBROUTINE W6HfUCVC 

!! Subroutine to initialise hw, corif, UC, VC for Indian Ocean tsunami.
      SUBROUTINE TsunCanr
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
       REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
!! New tsunami test near Canarias Islands in the Atlantic Ocean.
       INTEGER:: IStr=9744,IEND=9792, JStr=1136,JMid=1152,JEND=1168, SHgt=20.0
       REAL:: tsulon=-17.000, tsulat=29.000, tsurds=0.8, tsuhit=8.0

!!  Half-grid increment
       CNST1=DLon*0.5
       CNST2=DLat*0.5

       ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )

!!  Loop over all cells, excluding polar cells 
       DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

       END DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
       IF( NPol .GT. 0 ) THEN
       DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
       ENDDO
       ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
!      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
!     &                 AnglD, DfPolat, DfPolon, NC)

!!  No need for rotation.
       ELon = XLon
       ELat = WLat
       AnglD = 0.0

!!  Cell centre U V for advective flux update.
       UC=0.0
       VC=0.0

!!  Initialise Hw(NC) to be equal to mean sea level. 
       Hw=0.0
       WHERE( Btm < 0.0) Hw = -Btm 
       
!!  Loop over all cells to initialise tsunami disturbance.
       DO L=1, NC

!!  Work out hill radus from ELat and ELon
!        CNST3 = ELon(L) - tsulon
!        IF( CNST3 .GT.  180.0 ) CNST3 = CNST3 - 360.0 
!        IF( CNST3 .LT. -180.0 ) CNST3 = CNST3 + 360.0 

!        CNST4 = ELat(L) - tsulat
!        CNST6 = SQRT( CNST3*CNST3 + CNST4*CNST4 )

!!  Add tsunami disturbance to initial water height,  half up half down.
!        IF( CNST6 .LT. tsurds ) THEN
!           Hw(L) = Hw(L) + tsuhit*(1.0 - CNST6/tsurds)*SIGN(1.0, CNST3)
!        ENDIF 
!
!!  New landslide off Tenerife Island about 200 km^3.  JGLi13Dec2023
!!  Set 4 size-8 cells (about 20km x 20km) 50 m lower or to cell floor
!!  and set another 4 size-8 cells north of them 50 m higher.
         JJ = ICE(2, L)
         IF( ICE(1,L) >= IStr .AND. ICE(1,L) < IEnd ) THEN
             IF( JStr <= JJ .AND. JJ < JMid ) THEN
                 Hw(L) = MAX(0.0, Hw(L)-SHgt*0.5 )
             ELSEIF( JMID <= JJ .AND. JJ < JEND ) THEN
                 Hw(L) = Hw(L) + SHgt
             ENDIF
         ENDIF
       END DO

!!  Initial Coriolis factor by rotated latitude.
       DO L=1, NC
         CoriF(L) = Omega2*DT*SIN(ELat(L)*D2RAD)
       END DO

       DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy and gradients are skipped for case 5. 
      L = Itrm
      Terms(4)=Hw(L)
      Terms(5)=UC(L)
      Terms(6)=VC(L)

! 999  PRINT*, ' Sub TsunCanr ended.'

      RETURN
      END SUBROUTINE TsunCanr 

!! Subroutine to initialise hw, corif, UC, VC for tsunami with
!! Source.dat initial condition.
!!                              JGLi22Dec2023
      SUBROUTINE TsunamiS
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
       REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
       REAL, ALLOCATABLE, DIMENSION(:,:)::  DISTB
!! New tsunami test for 2004 Boxing day tsunami in Indian Ocean.
       INTEGER:: INmb, JNmb, IStr, IEND, JStr, JEND, MSiz

!!  Half-grid increment
       CNST1=DLon*0.5
       CNST2=DLat*0.5

       ALLOCATE( XLon(NC), WLat(NC), ELon(NC), ELat(NC), AnglD(NC) )

!!  Open and read initial source disturbance data from file.
       OPEN(UNIT=38,FILE='Source.dat',STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,'Source.dat was not opened! '
          READ(38,*)   INmb, JNmb, IStr, JStr, MSiz
         WRITE( 6,*)   INmb, JNmb, IStr, JStr, MSiz
       ALLOCATE( Distb(INmb, JNmb) )
       DO k=1, JNmb
          READ(38,*)   Distb(:,k)
       ENDDO
       CLOSE(38)
       WRITE(6,*) "Distb(1,1), Distb(INmb, JNmb)=",  &
                   Distb(1,1), Distb(INmb, JNmb)

!!  Workout disturbance i, j range.
       IEnd=IStr + INmb*MSiz
       JEnd=JStr + JNmb*MSiz
       IF( IEnd > NLon ) THEN
           WRITE(6,*) " *** Initial disturnance out of range *** ", &
                        IStr, IEnd, NLon
       ENDIF

!!  Loop over all cells, excluding polar cells 
!$OMP Parallel DO Private(L)
       DO L=1, NC-NPol

!!  Cell centre latitude equal to west side centre latitude.
!!  Note j count from -90 to 90 so j=0 corresponding to equator
         XLon(L)= Float( ICE(1,L) )*DLon + CNST1*Float( ICE(3,L) ) + ZLON
         WLat(L)= Float( ICE(2,L) )*DLat + CNST2*Float( ICE(4,L) ) + ZLat

       END DO
!$OMP END Parallel DO

!! AnglD will be undefined at poles as no local east at poles.  
!! So polar cell centres are shifted slightly off the Poles.
       IF( NPol .GT. 0 ) THEN
       DO L=NC-NPol+1, NC
         XLon(L)= Float(ICE(1,L))*DLon + ZLON
         WLat(L)= Float(ICE(2,L))*DLat + CNST2*Float(ICE(4,L))*0.9999 + ZLat
       ENDDO
       ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
!      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
!     &                 AnglD, DfPolat, DfPolon, NC)

!!  No need for rotation.
       ELon = XLon
       ELat = WLat
       AnglD = 0.0

!!  Set all cell velocity to be zero for calm start.
       UC=0.0
       VC=0.0

!!  Initialise Hw(NC) to be equal to mean sea level. 
       Hw=0.0
       WHERE( Btm < 0.0) Hw = -Btm 

!!  Initial disturbance is stored in A for output.
       A = 0.0
       
!!  Loop over all cells to initialise tsunami disturbance.
!$OMP Parallel DO Private(L, i, j, K, M, II, JJ, KK, MM, LM, CNST6)
       DO L=1, NC

       IF( Btm(L) < 0.0 ) THEN
          II = ICE(1,L)
          JJ = ICE(2,L)
          IF( IStr<=II .AND. II<IEnd .AND. JStr<=JJ .AND. JJ<JEnd ) THEN
              i = INT( (II-IStr)/MSiz ) + 1
              j = INT( (JJ-JStr)/MSiz ) + 1
              K = INT( (ICE(3,L)-1)/MSiz ) + i
              M = INT( (ICE(4,L)-1)/MSiz ) + j
              IF( K > INmb ) K=INmb
              IF( M > JNmb ) M=JNmb
              LM=0
              CNST6=0.0 
              DO MM = j, M 
              DO KK = i, K 
                 CNST6=CNST6+Distb(KK, MM)
                 LM = LM + 1
              ENDDO
              ENDDO
!!  Lowest water level drop is limited to depth.  No limit for high lift.
              A(L)  = MAX( Btm(L), CNST6/FLOAT(LM) )
              Hw(L) = Hw(L) + A(L)
!             WRITE(6,'(8i6,2F8.1)') ICE(:,L), i,j,K,M, Btm(L), A(L)
          ENDIF 
       ENDIF 
 
       END DO
!$OMP END Parallel DO

!!  Initial Coriolis factor by rotated latitude.
!$OMP Parallel DO Private(L)
       DO L=1, NC
         CoriF(L) = Omega2*DT*SIN(ELat(L)*D2RAD)
       END DO
!$OMP END Parallel DO

       DEALLOCATE( XLon, WLat, ELon, ELat, AnglD, Distb )

!!  Calcualte analytic solution terms for comparison with numerical ones.
!!  Vortiticy and gradients are skipped for case 5. 
      L = Itrm
      Terms(4)=Hw(L)
      Terms(5)=UC(L)
      Terms(6)=VC(L)

! 999  PRINT*, ' Sub TsunamiS ended.'

      RETURN
      END SUBROUTINE TsunamiS 

!! Subroutine to initialise hw, corif, UC, VC for Indian Ocean tsunami.
      SUBROUTINE TsunChil
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST7
       REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
!! New tsunami test near Canarias Islands in the Atlantic Ocean.
       REAL:: tsulon=-17.000, tsulat=29.000, tsurds=0.8, tsuhit=8.0

! 999  PRINT*, ' Sub TsunamHw ended.'

      RETURN
      END SUBROUTINE TsunChil 


!   End of module SWEsInitMD.
       END MODULE SWEsInitMD
!
