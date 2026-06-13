!
       MODULE SWEsDynaMD
!
!      This module is a collection of subroutines related to dynamical
!      model of shallow-water equations on the Spherical Multiple-Cell 
!      (SMC) grid.             JGLi15Nov2019
!
!      Subroutines included are:
!      UpdtUCVC(Ucr, Vcr) 
!      BondVictr(Uctr, Vctr)
!      BondScalr(Sclr)
!      ProUNO2(CPro, TSFr)
!      SMCxUNO2(NUA, NUB, TSF)
!      SMCyUNO2(NVA, NVB, TSF)
!      SMCxUNO3(NUA, NUB, TSF)
!      SMCyUNO3(NVA, NVB, TSF)
!      CntrAvrg(CFld)
!      TotlEngy
!      KinetcEn(Uctr, Vctr)
!      DHDXDHDY
!      UVNTerpo
!      Vorticty
!      Integral( FildC, Ftgrl )
!      Errol12m( FildC, El12m )
! 
!      ReadCell
!      ArctAngd
!      WRITEOUT( CWrt, NTSP, FD)
!      WRITEUVs( UCwt, VCwt, NTSP)
!      READUVs( UCwt, VCwt, NTSP)
!
!  Use omp_lib for OpenMP functions if switched on.   JGLi10Jan2018
!$       USE omp_lib
! 

       CONTAINS

! Subroutine that update the cell centre velocities (momentum equation)
       SUBROUTINE UpdtUCVC(Ucr, Vcr) 
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL, INTENT(OUT):: Ucr(-9:NCL), Vcr(-9:NCL)
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!! Initialise Ucr, Vcr, AU and AV
        Ucr = 0.0
        Vcr = 0.0
         AU = 0.0
         AV = 0.0

!! Some multiply factors
        CNST0= GRVTY*DT

!! Loop over all cells, including polar cells.
!$OMP Parallel DO Private(n)
        DO n=1, NC 
!! Only calculate U V at wet points
           IF( Hw(n) .GT. ZENO ) THEN
           F(n)=0.5*Vort(n)
           D(n)=F(n)*F(n)
!! Add bottom friction term by a semi-implicity scheme.  JGLi14Dec2023
           C(n)=BFrc(n)/(Hw(n) + DepMn)
 
!! Add damping term -GmDT*UC    JGLi04Mar2016
           AU(n)= ( (1.0-D(n)-GmDT)*UC(n)+Vort(n)*VC(n)-DHDX(n)*CNST0  &
      &             -F(n)*DHDY(n)*CNST0 )/(1.0+D(n)+C(n)) 
!     &             -F(n)*DHDY(n)*CNST0 )/(1.0+D(n)) 
!! Add damping term -GmDT*VC    JGLi04Mar2016
           AV(n)=(VC(n)*(1.0-GmDT)-F(n)*(UC(n)+AU(n))-DHDY(n)*CNST0)/(1.0+C(n))
!          AV(n)= VC(n)*(1.0-GmDT)-F(n)*(UC(n)+AU(n))-DHDY(n)*CNST0
           ENDIF
           IF( n .EQ. Itrm ) THEN
              Terms(1)=Vort(n)
              Terms(2)=DHDX(n)*CNST0
              Terms(3)=DHDY(n)*CNST0
              Terms(4)=Hw(n)
              Terms(5)=AU(n)
              Terms(6)=AV(n)
           ENDIF
        ENDDO
!$OMP END Parallel DO

!$OMP Parallel DO Private(m)
        DO m=1, NC 
           Ucr(m)= AU(m)
           Vcr(m)= AV(m)
        ENDDO
!$OMP END Parallel DO

!!    Update boundary cells after proper rotation if Arctic part is
!!    included. 
       IF( Arctic ) CALL BondVictr(Ucr, Vcr)

! 999   PRINT*, ' Sub UpdtUCVC ended.'
        RETURN

       END SUBROUTINE UpdtUCVC 


! Subroutine to update victor boundary conditons between global and polar parts. 
       SUBROUTINE BondVictr(Uctr, Vctr)
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL, INTENT(INOUT):: Uctr(-9:NCL), Vctr(-9:NCL)
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!!    Arctic cells for global boundary cells, rotate by AngC
!$OMP Parallel DO Private(i, ii, kk)
       DO i=1,NGLB
          ii=i+NGLA
          kk=MBGLo(i)
          Uctr(ii)= Uctr(kk)*CSAnC(kk) + Vctr(kk)*SNAnC(kk)
          Vctr(ii)= Vctr(kk)*CSAnC(kk) - Uctr(kk)*SNAnC(kk)
       ENDDO
!$OMP END Parallel DO

!!    Global cells for Arctic boundary cells.
!!    Note AngC is only defined for Arctic cells.
!$OMP Parallel DO Private(i, ii, kk)
       DO i=1,NArB
          ii=i+NArA
          kk=MBArc(i)
          Uctr(ii)= Uctr(kk)*CSAnC(ii) - Vctr(kk)*SNAnC(ii)
          Vctr(ii)= Vctr(kk)*CSAnC(ii) + Uctr(kk)*SNAnC(ii)
       ENDDO
!$OMP END Parallel DO

! 999  PRINT*, ' Sub BondVictr ended.'

      RETURN
      END SUBROUTINE BondVictr


! Subroutine to update scalar boundary conditions between global and polar parts. 
       SUBROUTINE BondScalr(Sclr)
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL, INTENT(INOUT):: Sclr(-9:NCL)
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!!    Arctic cells for global boundary cells
!$OMP Parallel DO Private(i, ii, kk)
       DO i=1,NGLB
          ii=i+NGLA
          kk=MBGLo(i)
          Sclr(ii) = Sclr(kk)
       ENDDO
!$OMP END Parallel DO

!!    Global cells for Arctic boundary cells
!$OMP Parallel DO Private(i, ii, kk)
       DO i=1,NArB
          ii=i+NArA
          kk=MBArc(i)
          Sclr(ii) = Sclr(kk)
       ENDDO
!$OMP END Parallel DO

! 999  PRINT*, ' Sub BondScalr ended.'

      RETURN
      END SUBROUTINE BondScalr


! Subroutine that calculate transportations
       SUBROUTINE ProUNO2(CPro, TSFr)
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL, INTENT(INOUT):: CPro(-9:NCL), TSFr
         REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8

!! Reset net flux arrays for this time step
         F  = 0.0
         AU = 0.0
         AV = 0.0

!! Assign transported variable to C
         C = CPro

!! Sub-stepping for different sizes of cells
        DO  NB=1, MFct

!! Loop over 3 refined levels
           DO LvR=1, MRL

!! Sub-level multiple number
              Lvm=2**(LvR-1) 
              CNST2=FLOAT(Lvm)*TSFr

!! Only calculate the level when MOD(NB, Lvm) = 0
              IF( MOD(NB, Lvm) .EQ. 0 ) THEN

!! Assign sub-time step counts
              icl=NRLCel(LvR-1)+1
              iuf=NRLUFc(LvR-1)+1
              ivf=NRLVFc(LvR-1)+1
              jcl=NRLCel(LvR)
              juf=NRLUFc(LvR)
              jvf=NRLVFc(LvR)

!! Check index ranges at first main time step
           IF( NT .EQ. NS+1 .AND. NB .EQ. MFct ) THEN
              WRITE(6, *) "NB, LvR, Lvm =", NB, LvR, Lvm
           ENDIF

!  Call subroutines to calculate advection
!  Call GMCxUNO2 to calculate MFx value
           CALL SMCxUNO2(iuf, juf, CNST2)
!          CALL SMCxUNO3(iuf, juf, CNST2)

!  Store conservative flux in F advective one in A
!  Add diffusion flux as well, note FX with an negative sign
!$OMP Parallel DO Private(i, M, N)
           DO i=iuf, juf
              M=ISD(5,i)
              N=ISD(6,i)
!  Closed boundary condition for SWE model mass conservation.
           IF( M > 0 ) THEN           
!$OMP ATOMIC 
              F(M) = F(M) - (FU(i)*U(i)*CNST2 - FX(i))
!$OMP ATOMIC 
              AU(M) = AU(M) - (FU(i)*UCL(M)*CNST2 - FX(i))
           ENDIF
           IF( N > 0 ) THEN           
!$OMP ATOMIC 
              F(N) = F(N) + (FU(i)*U(i)*CNST2 - FX(i))
!$OMP ATOMIC 
              AU(N) = AU(N) + (FU(i)*UCL(N)*CNST2 - FX(i))
           ENDIF
           ENDDO
!$OMP END Parallel DO

!  Store conservative update in D and advective update in C
!  The side length in MF value has to be cancelled with cell length
!  Also divided by another cell length as U UC is in basic unit
           mm = 0
!$OMP Parallel DO Private(n)
           DO n=icl, jcl
              D(n)=C(n) +  F(n)*RCELA(n)
              C(n)=C(n) + AU(n)*RCELA(n)
              F(n)=0.0
             AU(n)=0.0
!! Filter out negative C if any in substeps.  JGLi12Aug2022
              IF( C(n) .LT. 0.0 ) THEN
                  C(n) = 0.0
!$OMP ATOMIC 
                  mm = mm + 1
                  IF( MOD(NT, 20*NWP) == 0 .AND. NB == 8 )  &
                      WRITE(17,'(" Cu-",6i6)') ICE(:,n),KG(n)
              ENDIF
           ENDDO
!$OMP END Parallel DO

!! Note the N Polar cell does not have any U-flux input.

!  Call GMCyUNO2 to calculate MFy value
           CALL SMCyUNO2(ivf, jvf, CNST2)
!          CALL SMCyUNO3(ivf, jvf, CNST2)

!  Store conservative flux in F
!  Add diffusion flux FY, note FY with an negative sign
!$OMP Parallel DO Private(j, M, N)
           DO j=ivf, jvf
              M=JSD(5,j)
              N=JSD(6,j)
!  Closed boundary condition for SWE model mass conservation.
!  Polar region linking boundary 0 cells are allowed to open.  JGLi10Aug2022
!          IF( M > 0 .AND. N > 0 ) THEN           
           IF( M >= 0 ) THEN           
!$OMP ATOMIC 
              AV(M) = AV(M) - (FV(j)*V(j)*CNST2 - FY(j))
           ENDIF
           IF( N >= 0 ) THEN           
!$OMP ATOMIC 
              AV(N) = AV(N) + (FV(j)*V(j)*CNST2 - FY(j))
           ENDIF
           ENDDO
!$OMP END Parallel DO

!  Store conservative update of D in C 
!  The v side length in MF value has to be cancelled with cell length
!! One cosine factor is also needed to be divided for GMC grid
!$OMP Parallel DO Private(n, CNST)
           DO n=icl,jcl
!! Polar cells do not need the cosine factor.
              IF( n .GT. NC-NPol ) THEN
              CNST=RCELA(n)
              ELSE
              CNST=RCELA(n)/CCLat( 2*ICE(2,n)+ICE(4,n) )
              ENDIF
              C(n)=D(n) + AV(n)*CNST
              AV(n)=0.0
!
!! Filter out negative C if any in substeps.  JGLi12Aug2022
              IF( C(n) .LT. 0.0 ) THEN
                  C(n) = 0.0
!$OMP ATOMIC 
                  mm = mm + 1
                  IF( MOD(NT, 20*NWP) == 0 .AND. NB == 8 )  &
                      WRITE(17,'(" Cv-",6i6)') ICE(:,n),KG(n)
              ENDIF
!
           ENDDO
!$OMP END Parallel DO

!! Warning if any NaN or negative water heights appeared.
           IF( ( NT<NWP .OR. MOD(NT,NWP).eq.0 ) .AND. mm>0 ) THEN
!              WRITE(6, FMT='(" Cw mm NT NB LvR =",6i8)') mm,NT,NB,LvR
               WRITE(17,FMT='(" Cw mm NT NB LvR =",6i8)') mm,NT,NB,LvR
           ENDIF

!! End of refined level IF( MOD(NB, Lvm) .EQ. 0 ) block
              ENDIF
!! End of refined level loop LvR 
           ENDDO

!! End of sub-step loops NB
        ENDDO

!!    Update boundary cells after proper rotation if Arctic part is
!!    included. 
       IF( Arctic ) CALL BondScalr(C)

!!   Assign transported value back to CPro
       CPro = C

! 999  PRINT*, ' Sub ProUNO2 ended.'

      RETURN
      END SUBROUTINE ProUNO2


! Subroutine that calculate mid-flux values for x dimension 
       SUBROUTINE SMCxUNO2(NUA, NUB, TSF)
         USE SWEsCnstMD
         IMPLICIT NONE
         INTEGER, INTENT(IN):: NUA, NUB
         REAL,    INTENT(IN):: TSF
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, &
                      CNST7, CNST8, CNST9

!    Two layer of boundary cells are added to each boundary cell face
!    with all boundary cells refer to C(-2:0)=0.0.

!    Diffusivity k*dt*2, where dt is the grid scaled sub-timestep.
         CNST7 = AKHDT2*TSF
         FX = 0.0 

!$OMP  Parallel Default(Shared), Private(i, jk, K, L, M, N),  &
!$OMP& Private(CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8,CNST9)

!    Notice an extra side length L is multiplied to mid-flux to give correct
!    proportion of flux into the cells.  This length will be removed by the
!    cell length when the tracer concentration is updated.

!$OMP DO
      DO i=NUA, NUB

!    Diffusion k*dt*2/dx multiplied by TSF for multiple steps
!    Add sine square polar biased factor  BS2Lat.  JGLi05Jun2017
         jk = 2*ISD(2,i)+ISD(3,i)
         CNST9= DX0*CCLat(jk)
         CNST0= CNST7*BS2Lat(jk)/( CNST9*CNST9 )

!    Multi-resolution SMC grid requires flux multiplied by face factor.
         CNST8 = FLOAT( ISD(3,i) )

!    Select Upstream, Central and Downstream cells
         K=ISD(4,i)
         L=ISD(5,i)
         M=ISD(6,i)
         N=ISD(7,i)

!    Face bounding cell lengths and central gradient
         CNST2=REAL( ICE(3,L) )
         CNST3=Real( ICE(3,M) )
         CNST5=(C(M)-C(L))/(CNST3+CNST2)

!!   Diffusion only between wet cells, otherwise zero.  JGLi01Sep2022
         IF( C(L)>ZENO .AND. C(M)>ZENO ) THEN
!!   Diffusion flux is proportional to total height H+b gradient and 
!    is multiplied by Fourier Number and face_width.
           FX(i)=CNST0*CNST8*(C(M)+Btm(M)-C(L)-Btm(L))/(CNST3+CNST2)
         ENDIF

!    Face normal velocity and courant number in local size-1 cell unit
         CNST6=U(i)*TSF

!    For positive velocity case
         IF(CNST6 >= 0.0)  THEN

!    Upstream cell length and gradient, depending on UFLX sign.
           CNST1=REAL( ICE(3,K) )
           CNST4=(C(L)-C(K))/(CNST1+CNST2)

!    Use minimum gradient all region
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value inside central cell
           FU(i)=(C(L) + CNST*(CNST2-CNST6))*CNST8

!    For negative velocity case
         ELSE

!    Upstream cell length and gradient, depending on UFLX sign.
           CNST1=REAL( ICE(3,N) )
           CNST4=(C(N)-C(M))/(CNST3+CNST1)

!    Use minimum gradient outside monotonic region
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value inside central cell M
           FU(i)=(C(M) - CNST*(CNST3+CNST6))*CNST8

!    End of advection mid-flux evaluation.
         ENDIF

      END DO
!$OMP END DO

!$OMP END Parallel 

! 999  PRINT*, ' Sub SMCxUNO2 ended.'

      RETURN
      END SUBROUTINE SMCxUNO2


! Subroutine that calculate mid-flux values for x dimension 
       SUBROUTINE SMCyUNO2(NVA, NVB, TSF)
         USE SWEsCnstMD
         IMPLICIT NONE
         INTEGER, INTENT(IN):: NVA, NVB
         REAL,    INTENT(IN):: TSF

         REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6, &
                     CNST7,CNST8,CNST9 

!    Two layer of boundary cells are added to each boundary cell face
!    with all boundary cells refer to C(-2:0)=0.0.

!    Diffusion k*dt*2/(DY*DY) multiplied by TSF for multiple steps
         CNST7=AKHDT2*TSF*DYR*DYR
         FY = 0.0

!$OMP  Parallel Default(Shared), Private(j, K, L, M, N),  &
!$OMP& Private(CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8)

!    Notice an extra side length L is multiplied to mid-flux to give correct
!    proportion of flux into the cells.  This length will be removed by the
!    cell length when the tracer concentration is updated.

!$OMP DO
      DO j=NVA, NVB

!!   Polar biased diffusivity.
         CNST0=CNST7*BS2Lat( 2*JSD(2,j) )

!    Face size integer and cosine factor
         CNST8=CSLat( JSD(2,j) )*Real( JSD(3,j) )

!    Select Upstream, Central and Downstream cells
         K=JSD(4,j)
         L=JSD(5,j)
         M=JSD(6,j)
         N=JSD(7,j)

!    Face bounding cell lengths and gradient
         CNST2=Real( ICE(4,L) )
         CNST3=Real( ICE(4,M) )
         CNST5=(C(M)-C(L))/(CNST3+CNST2)

!!   Diffusion only between wet cells, otherwise zero. JGLi01Sep2022
         IF( C(L)>ZENO .AND. C(M)>ZENO ) THEN
!!   Diffusion flux is proportional to total height H+b gradient and 
!    is multiplied by Fourier Number and face_width.
           FY(j)=CNST0*CNST8*(C(M)+Btm(M)-C(L)-Btm(L))/(CNST3+CNST2)
         ENDIF

!    Courant number in basic cell unit
         CNST6=V(j)*TSF

!    For positive velocity case
         IF(CNST6 >= 0.0)  THEN

!    Upstream cell size and irregular grid gradient, depending on VFLY.
           CNST1=Real( ICE(4,K) )
           CNST4=(C(L)-C(K))/(CNST1+CNST2)

!    Use minimum gradient outside monotonic region
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value multiplied by face width and cosine factor
           FV(j)=( C(L) + CNST*(CNST2-CNST6) )*CNST8

!    For negative velocity case
         ELSE

!    Upstream cell size and irregular grid gradient, depending on VFLY.
           CNST1=REAL( ICE(4,N) )
           CNST4=(C(N)-C(M))/(CNST3+CNST1)

!    Use minimum gradient outside monotonic region
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value multiplied by face width and cosine factor
           FV(j)=( C(M) - CNST*(CNST3+CNST6) )*CNST8 

         ENDIF

      END DO
!$OMP END DO

!$OMP END Parallel 

! 999  PRINT*, ' Sub SMCyUNO2 ended.'

      RETURN
      END SUBROUTINE SMCyUNO2


! Subroutine that calculate mid-flux values for x dimension 
       SUBROUTINE SMCxUNO3(NUA, NUB, TSF)
         USE SWEsCnstMD
         IMPLICIT NONE
         INTEGER, INTENT(IN):: NUA, NUB
         REAL,    INTENT(IN):: TSF
         REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6, &
                     CNST7,CNST8,CNST9

!    Two layer of boundary cells are added to each boundary cell face
!    with all boundary cells refer to C(-2:0)=0.0.

!    Diffusivity k*dt*2 is converted for grid scaled sub-timestep.
         CNST0 = AKHDT2*TSF
         FX = 0.0

!$OMP  Parallel Default(Shared), Private(i, jk, K, L, M, N),  &
!$OMP& Private(CNST,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7,CNST8,CNST9)

!    Notice an extra side length L is multiplied to mid-flux to give correct
!    proportion of flux into the cells.  This length will be removed by the
!    cell length when the tracer concentration is updated.

!$OMP DO
      DO i=NUA, NUB

!    Diffusion k*dt*2/dx multiplied by TSF for multiple steps
!    Add sine square polar biased factor  BS2Lat.  JGLi05Jun2017
         jk = 2*ISD(2,i)+ISD(3,i)
         CNST9= DX0*CCLat(jk)
         CNST7= CNST0*BS2Lat(jk)/( CNST9*CNST9 )

!    Select Upstream, Central and Downstream cells
         K=ISD(4,i)
         L=ISD(5,i)
         M=ISD(6,i)
         N=ISD(7,i)

!    Face bounding cell lengths and central gradient
         CNST2=REAL( ICE(3,L) )
         CNST3=Real( ICE(3,M) )
         CNST5=(C(M)-C(L))/(CNST3+CNST2)

!!   Diffusion only between wet cells, otherwise zero. JGLi01Sep2022
         IF( C(L)>ZENO .AND. C(M)>ZENO ) THEN
!!   Diffusion flux is proportional to total height H+b gradient and 
!    is multiplied by Fourier Number and face_width.
           FX(i)=CNST7*CNST8*(C(M)+Btm(M)-C(L)-Btm(L))/(CNST3+CNST2)
         ENDIF

!    Face normal velocity and courant number in local size-1 cell unit
         CNST6=U(i)*TSF

!    Multi-resolution SMC grid requires flux multiplied by face factor.
         CNST8 = FLOAT( ISD(3,i) )

!    For positive velocity case
         IF(CNST6 >= 0.0)  THEN

!    Upstream cell length and gradient, depending on UFLX sign.
           CNST1=REAL( ICE(3,K) )
           CNST4=(C(L)-C(K))/(CNST1+CNST2)

!    Second order gradient
           CNST7 = CNST5 - CNST4
           CNST9 = 2.0/( CNST3+CNST2+CNST2+CNST1 )

!    Use 3rd order scheme
           IF( Abs(CNST7) .LT. 0.6*CNST9*Abs(C(M)-C(K)) ) THEN
               CNST= CNST5 - ( CNST3+CNST6 )*CNST7*CNST9/1.5

!    Use doubled UNO2 scheme
           ELSE IF( CNST4*CNST5 .GT. 0.0 ) THEN
               CNST=Sign(2.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

                ELSE
!    Use minimum gradient UNO2 scheme
               CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

           ENDIF

!    Mid-flux value inside central cell
           FU(i)=(C(L) + CNST*(CNST2-CNST6))*CNST8
           
!    For negative velocity case
         ELSE

!    Upstream cell length and gradient, depending on UFLX sign.
           CNST1=REAL( ICE(3,N) )
           CNST4=(C(N)-C(M))/(CNST3+CNST1)

!    Second order gradient
           CNST7 = CNST4 - CNST5
           CNST9 = 2.0/( CNST2+CNST3+CNST3+CNST1 )

!    Use 3rd order scheme
           IF( Abs(CNST7) .LT. 0.6*CNST9*Abs(C(N)-C(L)) ) THEN
               CNST= CNST5 + ( CNST2-CNST6 )*CNST7*CNST9/1.5

!    Use doubled UNO2 scheme
           ELSE IF( CNST4*CNST5 .GT. 0.0 ) THEN
               CNST=Sign(2.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

                ELSE
!    Use minimum gradient UNO2 scheme. 
               CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

           ENDIF

!    Mid-flux value inside central cell M
           FU(i)=(C(M) - CNST*(CNST3+CNST6))*CNST8

         ENDIF

      END DO
!$OMP END DO

!$OMP END Parallel

! 999  PRINT*, ' Sub SMCxUNO3 ended.'

      RETURN
      END SUBROUTINE SMCxUNO3


! Subroutine that calculate mid-flux values for x dimension 
       SUBROUTINE SMCyUNO3(NVA, NVB, TSF)
         USE SWEsCnstMD
         IMPLICIT NONE
         INTEGER, INTENT(IN):: NVA, NVB
         REAL,    INTENT(IN):: TSF

         REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7,CNST8,CNST9

!    Two layer of boundary cells are added to each boundary cell face
!    with all boundary cells refer to C(-2:0)=0.0.

!    Diffusion k*dt*2/(DY*DY) multiplied by TSF for multiple steps
         CNST0=AKHDT2*TSF*DYR*DYR
         FY = 0.0 

!$OMP  Parallel Default(Shared), Private(j, K, L, M, N),  &
!$OMP& Private(CNST,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7,CNST8,CNST9)

!    Notice an extra side length L is multiplied to mid-flux to give correct
!    proportion of flux into the cells.  This length will be removed by the
!    cell length when the tracer concentration is updated.

!$OMP DO
      DO j=NVA, NVB

!!   Polar biased diffusivity.
         CNST7=CNST0*BS2Lat( 2*JSD(2,j) )

!    Face size integer and cosine factor
         CNST8=CSLat( JSD(2,j) )*Real( JSD(3,j) )

!    Select Upstream, Central and Downstream cells
         K=JSD(4,j)
         L=JSD(5,j)
         M=JSD(6,j)
         N=JSD(7,j)

!    Face bounding cell lengths and gradient
         CNST2=Real( ICE(4,L) )
         CNST3=Real( ICE(4,M) )
         CNST5=(C(M)-C(L))/(CNST3+CNST2)

!!   Diffusion only between wet cells, otherwise zero.  JGLi01Sep2022
         IF( C(L)>ZENO .AND. C(M)>ZENO ) THEN
!!   Diffusion flux is proportional to total height H+b gradient and 
!    is multiplied by Fourier Number and face_width.
           FY(j)=CNST7*CNST8*(C(M)+Btm(M)-C(L)-Btm(L))/(CNST3+CNST2)
         ENDIF

!    Courant number in basic cell unit
         CNST6=V(j)*TSF

!    For positive velocity case
         IF(CNST6 >= 0.0)  THEN

!    Upstream cell size and irregular grid gradient, depending on VFLY.
           CNST1=Real( ICE(4,K) )
           CNST4=(C(L)-C(K))/(CNST1+CNST2)

!    Second order gradient
           CNST7 = CNST5 - CNST4
           CNST9 = 2.0/( CNST3+CNST2+CNST2+CNST1 )

!    Use 3rd order scheme
           IF( Abs(CNST7) .LT. 0.6*CNST9*Abs(C(M)-C(K)) ) THEN
               CNST= CNST5 - ( CNST3+CNST6 )*CNST7*CNST9/1.5

!    Use doubled UNO2 scheme
           ELSE IF( CNST4*CNST5 .GT. 0.0 ) THEN
               CNST=Sign(2.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

                ELSE

!    Use minimum gradient outside monotonic region
               CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

           ENDIF

!    Mid-flux value multiplied by face width and cosine factor
           FV(j)=( C(L) + CNST*(CNST2-CNST6) )*CNST8

!    For negative velocity case
         ELSE

!    Upstream cell size and irregular grid gradient, depending on VFLY.
           CNST1=REAL( ICE(4,N) )
           CNST4=(C(N)-C(M))/(CNST3+CNST1)

!    Second order gradient
           CNST7 = CNST4 - CNST5
           CNST9 = 2.0/( CNST2+CNST3+CNST3+CNST1 )

!    Use 3rd order scheme
           IF( Abs(CNST7) .LT. 0.6*CNST9*Abs(C(N)-C(L)) ) THEN
               CNST= CNST5 + ( CNST2-CNST6 )*CNST7*CNST9/1.5

!    Use doubled UNO2 scheme
           ELSE IF( CNST4*CNST5 .GT. 0.0 ) THEN
               CNST=Sign(2.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

                ELSE

!    Use minimum gradient outside monotonic region
               CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

           ENDIF

!    Mid-flux value multiplied by face width and cosine factor
           FV(j)=( C(M) - CNST*(CNST3+CNST6) )*CNST8 

         ENDIF

      END DO
!$OMP END DO

!$OMP END Parallel

! 999  PRINT*, ' Sub SMCyUNO3 ended.'

      RETURN
      END SUBROUTINE SMCyUNO3


! Subroutine that average the cell centre fields
!!  Modified to balance x-y ratio for merged cells.  JGLi19Mar2015
!!  Modified to exclude average with dry cells.   JGLi22Nov2019
!!  Use exact 1-2-1 average for wet cells only.   JGLi02Sep2022
!
       SUBROUTINE CntrAvrg(CFld)
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL, INTENT(INOUT):: CFld(-9:NCL)
         REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8
         REAL, DIMENSION(-9:NC):: SLX, SLY

!! Reset net flux arrays for this time step
         AU  = 0.0
         AV  = 0.0
         SLX = 0.0 
         SLY = 0.0 

!! Assign to be averaged variable to C
         C = CFld
         C(-9:0) = 0.0

!$OMP  Parallel Default(Shared), Private(i, j, k, M, N),  &
!$OMP& Private(CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8)

!! Average over two cells bounding each U-face except for boundary cells. 
!$OMP DO
         DO i=1, NU
            M=ISD(5,i)
            N=ISD(6,i)

!! Use Hw to exclude average with dry and boundary cells.  JGLi28Aug2022
         IF( (M .GT. 0) .AND. (N .GT. 0) .AND.  &
             Hw(M)>ZENO .AND. Hw(N)>ZENO ) THEN 
            CNST8 = FLOAT( ISD(3,i) )
            CNST0 = CNST8*( C(M) + C(N) )
!$OMP ATOMIC
            AU(M) = AU(M) + CNST0
!$OMP ATOMIC
            AU(N) = AU(N) + CNST0
!$OMP ATOMIC
            SLX(M) = SLX(M) + CNST8
!$OMP ATOMIC
            SLX(N) = SLX(N) + CNST8
         ENDIF
         ENDDO
!$OMP END DO

!  Average over two cells bounding each V-face 
!$OMP DO
         DO j=1, NV
            M=JSD(5,j)
            N=JSD(6,j)
!! Use Hw to exclude average with dry and boundary cells.  JGLi28Aug2022
         IF( (M .GT. 0) .AND. (N .GT. 0) .AND.  &
             Hw(M)>ZENO .AND. Hw(N)>ZENO ) THEN 
            CNST6 = FLOAT( JSD(3,j) )
            CNST1 = CNST6*( C(M) + C(N) )
!$OMP ATOMIC
            AV(M) = AV(M) + CNST1
!$OMP ATOMIC
            AV(N) = AV(N) + CNST1
!$OMP ATOMIC
            SLY(M) = SLY(M) + CNST6
!$OMP ATOMIC
            SLY(N) = SLY(N) + CNST6
         ENDIF
         ENDDO
!$OMP END DO

!  Store averaged values back to C, excluding polar cells if any. 
!$OMP DO
         DO k=1, NC-NPol
!! Average only for wet cells whos Abs(J) index is above JAvrg.  JGLi19Jan2017
           IF( ABS(ICE(2,k)-JEqut) >= JAvrg .AND. Hw(k)>ZENO ) THEN

!! The SLX(n)/ICE(4,n) or SLY(n)/ICE(3,n) should be less or equal to 2, each.
!! They represent how many pairs of values are add for average, counting the 
!! sum of sub-faces as one. If one sub-face is missing, it becomes a fraction. 
!! The average is biased towards central cell value with a weight ratio of 6:4.
!! Check SLX/Y to be positive before dividing.  JGLi03Aug2022
!! 
!! Polar cell has only nonzero SLY, and SLY(n)/ICE(3,n) should be equal to the 
!! number of sub-faces surrounding it, because polar cell ICE(3,n) is equal to 
!! one sub-face length, not the whole round circumference.  The central cell
!! extra weight is removed so 1-2-1 average is used except for polar cells,
!! which use the SLY weight of all cells surrounding them.  JGLi08Aug2022
              CNST2 = 0.0
              CNST3 = 0.0
              CNST4 = ( SLX(k)/ICE(4,k) + SLY(k)/ICE(3,k) )

              IF( SLY(k) > ZENO ) THEN
                 CNST2 = 1.0
                 CNST3 = 0.5*AV(k)/SLY(k) 
              ENDIF
              IF( SLX(k) > ZENO ) THEN
                 CNST2 = 1.0 + CNST2 
                 CNST3 = 0.5*AU(k)/SLX(k) + CNST3  
              ENDIF

              IF( CNST2 > ZENO ) THEN
                 CNST5 = CNST3/CNST2
                 IF( k > NC-NPol ) THEN
                    C(k) = CNST5
                 ELSE
!!  Use central biased average for partially surrounded cells.  JGLi05Sep2022
                    C(k) = 0.25*( CNST5*CNST4 + (4.0-CNST4)*C(k) )
                 ENDIF   !! Polar cell difference.
              ENDIF      !! Non-zero CNST2 for average.
           ENDIF         !! JAvrg check.

         ENDDO
!$OMP END DO

!$OMP END Parallel

!!   Assign averaged value back to CFld
         CFld = C

! 999  PRINT*, ' Sub CntrAvrg ended.'

       RETURN
       END SUBROUTINE CntrAvrg

! Subroutine to calculate potential energy from Hw and Btm fields.
! Also caculate column integrated kinetic enegy Enkn*Hw.
!  First created:    9 Jan 2017   Jian-Guo Li
!  Last modified:   25 Jul 2024   Jian-Guo Li
      SUBROUTINE TotlEngy
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!!  Initialise potential and kinetic eneryg to be zero
         EnkH=0.0
         Enpt=0.0

!!  Loop over all cells, including polar cells
!$OMP Parallel DO Private(n)
         DO n=1, NC

!!  Keep dry point potential energy to be zero. 
            IF (Hw(n) .GT. ZENO ) THEN
!!  Standard potential energy forumlation except for the 
!!  gravity constant as kinetic energy has divided by it.
            Enpt(n)= Hw(n)*( Hw(n)*0.5 + Btm(n) )
!!  Column integrated kinetic energy is separated from potential energy. 
            EnkH(n)= Hw(n)*Enkn(n) 
            ENDIF

         END DO
!$OMP END Parallel DO

! 999  PRINT*, ' Sub TotlEngy ended.'

       RETURN
       END SUBROUTINE TotlEngy


! Subroutine to calculate kinetic energy from given velocities
!  First created:   12 Feb 2015   Jian-Guo Li
!  Last modified:    8 Mar 2016   Jian-Guo Li
!  Add bottom friction terms.  JGLi14Dec2023

      SUBROUTINE KinetcEn(Uctr, Vctr)
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL, INTENT(IN):: Uctr(-9:NCL), Vctr(-9:NCL)
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!!  Cell centre kinetic energy divided by gravity constant GRVTY.
!!  Set initial cell kinetic energy and friction force to be zero.
         Enkn=0.0
         BFrc=0.0
         CNST=0.5/GRVTY
         CNST1=CBFr*DT

!!  Loop over all cells, including polar cells
!$OMP Parallel DO Private(n, CNST2)
         DO n=1, NC

!!  Keep dry point kinetic energy to be zero.  JGLi03Feb2016
            IF (Hw(n) .GT. ZENO ) THEN
!!  Standard kinetic energy forumlation as UC and VC 
!!  do not need conversion for correct velocity unit.
               CNST2 = ( Uctr(n)*Uctr(n) + Vctr(n)*Vctr(n) )
               Enkn(n)= CNST*CNST2

!!  Bottom friction force velocity magnitude related part.
               BFrc(n)= CNST1*SQRT( CNST2 )

            ENDIF

         END DO
!$OMP END Parallel DO

! 999  PRINT*, ' Sub KinetcEn ended.'

       RETURN
       END SUBROUTINE KinetcEn


! Subroutine to calculate hw and kinetic energy gradients. 
!  First created:    3 Feb 2015   Jian-Guo Li
!  Last modified:   28 Aug 2022   Jian-Guo Li

       SUBROUTINE DHDXDHDY
         USE SWEsCnstMD
         IMPLICIT NONE
         REAL:: CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7
         REAL, DIMENSION(-9:NC):: AUN, AUT, AVN, AVT, SLX, SLY

!!   Assign water depth to HCel from KG integer values.
!!   set all depth zero for negative cells.
         DHDX=0.0
         DHDY=0.0
         HCel(-9:0)=0.0
         HCel(1:NC)= Btm(1:NC) + Hw(1:NC) + Enkn(1:NC)
         A = Hw + Btm

!!   Calculate DH/DX using ISD flux array to find neighbouring cells.
!!   0.5 divided by the basic cell x-length at Equator in meter
!        CNST0=0.5/(DX0*REARTH)
!!   The two cell length is 2 times of the required distance so
!!   a factor of 2.0 is needed on the flux instead of 0.5!  JGLi20Oct2016
!!   2.0 divided by the basic cell x-length at Equator in meter
         CNST0=2.0/(DX0*REARTH)

         AUN=0.0
         AUT=0.0
         AVN=0.0
         AVT=0.0
         SLX=ZENO
         SLY=ZENO

!!   Use the face arrays to calculate the bathymetry x-gradients.
!$OMP  Parallel DO Default(Shared), Private(i,M,N),  &
!$OMP& Private(CNST,CNST1,CNST3,CNST4,CNST5,CNST7)
       DO i=1, NU

!    Select Central and Downstream cells
           M=ISD(5,i)
           N=ISD(6,i)
           CNST1=Real( ISD(3,i) )

!    Simply skip boundary faces for zero gradient boundary condition. 
         IF( (M .GT. 0) .AND. (N .GT. 0) ) THEN

!!   Only calculate gradient when the cell is wet and its neighbour cell floor 
!!   is lower than its water level no matter the cell is dry or wet. This will
!!   automatically exclude higher dry cells for gradient.  JGLi01Sep2022
           IF(( Hw(M)>ZENO .AND. A(M)>Btm(N) ) .OR. &
              ( Hw(N)>ZENO .AND. A(N)>Btm(M) )) THEN

              CNST= HCel(N) - HCel(M)
            
!    Cell length of UCD cells
              CNST3=Real(ICE(3,M)+ICE(3,N))*CCLat(2*ISD(2,i)+ISD(3,i))

!    Side gradients over basic cell length for central cells include face length factor
              CNST7=CNST0*CNST1*CNST/CNST3

!    Project gradient to map-east direction system in polar regions
!    before store side gradient in two neighbouring cells.
              IF(i .GT. NUGL) THEN
                 CNST4 =CNST7*CSAnU(i)
                 CNST5 =CNST7*SNAnU(i)
!$OMP ATOMIC
                 AUN(M) = AUN(M) + CNST4
!$OMP ATOMIC
                 AUN(N) = AUN(N) + CNST4
!$OMP ATOMIC
                 AUT(M) = AUT(M) + CNST5
!$OMP ATOMIC
                 AUT(N) = AUT(N) + CNST5
              ELSE
!$OMP ATOMIC
                 AUN(M) = AUN(M) + CNST7
!$OMP ATOMIC
                 AUN(N) = AUN(N) + CNST7
              ENDIF

!!   End of skipping higher dry cell faces.
           ENDIF
!!   End of skipping boundary faces M N > 0
         ENDIF

!!   Face length is always added even for boundary face.  JGLi03Jun2016
!$OMP ATOMIC
         SLX(M) = SLX(M) + CNST1
!$OMP ATOMIC
         SLX(N) = SLX(N) + CNST1

       END DO
!$OMP END Parallel DO

!!   Calculate DH/DY using JSD flux array to find neighbouring cells.
!!   2.0 divided by the basic cell y-length at Equator in meter.  JGLi20Oct2016
         CNST6=2.0/(DY*REARTH)

!!   Use the face arrays to calculate the bathymetry y-gradients.
!$OMP  Parallel DO Default(Shared), Private(j,M,N),  &
!$OMP& Private(CNST,CNST2,CNST3,CNST4,CNST5,CNST7)
       DO j=1, NV

!    Select Central and Downstream cells
           M=JSD(5,j)
           N=JSD(6,j)
!!   Use numerical average not true face length one.  JGLi02Apr2015
!          CNST2=Real( JSD(3,j) )*CSLat( JSD(2,j) )
           CNST2=Real( JSD(3,j) )

!    Simply skip boundary faces for zero gradient boundary condition. 
         IF( (M .GT. 0) .AND. (N .GT. 0) ) THEN

!!   Replace with zero-gradient at higher dry cell side but allow
!!   water flow into lower dry cell.  JGLi01May2018
           IF(( Hw(M)>ZENO .AND. A(M)>Btm(N) ) .OR. &
              ( Hw(N)>ZENO .AND. A(N)>Btm(M) )) THEN

              CNST= HCel(N) - HCel(M)

!    Cell length of UCD cells
              CNST3=Real( ICE(4,M) + ICE(4,N) )

!    Side gradients over basic cell length for central cells include face length factor
              CNST7=CNST6*CNST2*CNST/CNST3

!    Project gradient to map-east direction system in polar regions
!    before store side gradient in two neighbouring cells.
              IF(j .GT. NVGL) THEN
                 CNST4 =  CNST7*CSAnV(j)
                 CNST5 = -CNST7*SNAnV(j)
!$OMP ATOMIC
                 AVN(M) = AVN(M) + CNST4
!$OMP ATOMIC
                 AVN(N) = AVN(N) + CNST4
!$OMP ATOMIC
                 AVT(M) = AVT(M) + CNST5
!$OMP ATOMIC
                 AVT(N) = AVT(N) + CNST5
              ELSE
!$OMP ATOMIC
                 AVN(M) = AVN(M) + CNST7
!$OMP ATOMIC
                 AVN(N) = AVN(N) + CNST7
              ENDIF

!!   End of skipping higher dry cell faces.
           ENDIF
!!   End of skipping boundary faces M N > 0
         ENDIF

!!   Face length is always added even for boundary face.  JGLi03Jun2016
!$OMP ATOMIC
         SLY(M) = SLY(M) + CNST2
!$OMP ATOMIC
         SLY(N) = SLY(N) + CNST2

       END DO
!$OMP END Parallel DO
 
!  Assign averaged side-gradient to DHDX and DHDY, including polar cells. 
!  Because SLX/Y add each face length twice, it already contains a factor 2.
!$OMP  Parallel DO Default(Shared), Private(n)
       DO n = 1, NC
          DHDX(n)= AUN(n)/SLX(n) + AVT(n)/SLY(n)
          DHDY(n)= AUT(n)/SLX(n) + AVN(n)/SLY(n)
       ENDDO
!$OMP END Parallel DO

! 999  PRINT*, ' Sub DHDXDHDY ended.'

       RETURN
       END SUBROUTINE DHDXDHDY


!! Subroutine that interpolate UC VC on to cell face components.
!  First created:    3 Feb 2015   Jian-Guo Li
!  Last modified:    8 Aug 2022   Jian-Guo Li

       SUBROUTINE UVNTerpo
       USE SWEsCnstMD
       IMPLICIT NONE
       REAL:: CNST, CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST7
       REAL:: AUN(NU), AUT(NU), AVN(NV), AVT(NV)  

!      PRINT*, ' Sub UVNTerpo started.'

!!  Cell centre velocities are in conventional unit of m s-1 
!!  but face normal velocities are in unit of basic cell grid speed or 
!!  divided by the grid velocity BX/DT or BY/DT.
!!  Tangential face velocities are only used for loop integration
!!  so they are multiplied by unit face size (in unit of radian).
       CNST6=DT/(DX0*REARTH) 
       CNST7=DT/(DY*REARTH) 

!!  For variable bathymetry, the simple average is replaced with volume 
!!  or mass weighted average.  Assuming face size is shared by the two
!!  neighbouring cells (equal horizontal quarter areas), the volume is 
!!  then represented by the cell-size*depth.  The cell face depth is 
!!  simply given by the numerically average of the two cell depths. 
!!                      JGLi28Jan2016

!!  Full water surface height above sea level or dry cell altitude.
       A = Hw + Btm 

!!  Initial all U V UT VT to be zero.
       U  = 0.0
       UT = 0.0
       V  = 0.0
       VT = 0.0

!!  Introduce dry cell boundary condition when the dry cell is above 
!!  neighbouring wet cell.  Simply use wet cell tangent velocity and 
!!  zero normal velocity for such dry cell face.  JGLi21Nov2019

!!   Use the face arrays to calculate centre to U-face interpolation.
!$OMP Parallel DO Private(i,M,N,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5)
       DO i=1, NU

!    Select Central and Downstream cells
           M=ISD(5,i)
           N=ISD(6,i)
           CNST1= CNST6/CCLat( 2*ISD(2,i)+ISD(3,i) )

!!   For face bounded with M wet and N higher dry or boundary cell.
         IF(      Hw(M)>ZENO .AND. ( N < 0 .OR.    &
                 (Hw(N)<ZENO .AND. A(M)<=Btm(N)) ) ) THEN
             IF(i .GT. NUGL) THEN
                UT(i) = ( VC(M)*CSAnU(i) - UC(M)*SNAnU(i) )*CNST6
             ELSE
                UT(i) = VC(M)*CNST6
             ENDIF

!!   For face bounded with N wet and M higher dry or boundary cell.
         ELSE IF( Hw(N)>ZENO .AND. ( M < 0 .OR.    &
                 (Hw(M)<ZENO .AND. A(N)<=Btm(M)) ) )THEN
             IF(i .GT. NUGL) THEN
                UT(i) = ( VC(N)*CSAnU(i) - UC(N)*SNAnU(i) )*CNST6
             ELSE
                UT(i) = VC(N)*CNST6
             ENDIF

!    Full interpolation when both cell are wet or one dry cell is lower.
         ELSE IF( Hw(M) > ZENO .OR. Hw(N) > ZENO ) THEN
 
!    Cell length of UCD cells
           CNST2= Real( ICE(3,M) )
           CNST3= Real( ICE(3,N) )
!    Volume weight introduced.  JGLi28Jan2016
!    Add minimum number ZENO=1.0E-32 to avoid zero-dividing 
!    in case a dry point or Hw=0.0     JGLi03Feb2016
           CNST0= 2.0/((Hw(M)+Hw(N)+ZENO)*(CNST3+CNST2))
           CNST4= Hw(M)*CNST0*CNST3 
           CNST5= Hw(N)*CNST0*CNST2 

!    Interpolation to face in proportion of neighbouring cell sizes.
           AUN(i)= CNST4*UC(M) + CNST5*UC(N)
           AUT(i)= CNST4*VC(M) + CNST5*VC(N)

!    Project map-east velocity to local east in polar regions
!    and add normalisation factor for face velocities.
           IF(i .GT. NUGL) THEN
               U(i)= ( AUN(i)*CSAnU(i) + AUT(i)*SNAnU(i) )*CNST1
!!   Tangential velocity is used for vorticity circular integration so
!!   the cosine factor is not required.   JGLi25May2016
              UT(i)= ( AUT(i)*CSAnU(i) - AUN(i)*SNAnU(i) )*CNST6
           ELSE
               U(i)= AUN(i)*CNST1
              UT(i)= AUT(i)*CNST6
           ENDIF

!!   End of wet-dry cell checking if-block.
         ENDIF

       END DO
!$OMP END Parallel DO

!      PRINT*, ' Sub UVNTerpo U-loop done.'

!!   Use the face arrays to calculate centre to V-face interpolation.
!$OMP Parallel DO Private(j,M,N,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5)
       DO j=1, NV

!    Select Central and Downstream cells
           M=JSD(5,j)
           N=JSD(6,j)

!!   For face bounded with M wet and N higher dry cell.
         IF(      Hw(M)>ZENO .AND. ( N < 0 .OR.    &
                 (Hw(N)<ZENO .AND. A(M)<=Btm(N)) ) ) THEN
             IF(j .GT. NVGL) THEN
                VT(j) = ( UC(M)*CSAnV(j) + VC(M)*SNAnV(j) )*CNST7
             ELSE
                VT(j) = UC(M)*CNST7
             ENDIF

!!   For face bounded with N wet and M higher dry cell.
         ELSE IF( Hw(N)>ZENO .AND. ( M < 0 .OR.    &
                 (Hw(M)<ZENO .AND. A(N)<=Btm(M)) ) ) THEN
             IF(j .GT. NVGL) THEN
                VT(j) = ( UC(N)*CSAnV(j) + VC(N)*SNAnV(j) )*CNST7
             ELSE
                VT(j) = UC(N)*CNST7
             ENDIF

!    Full interpolation when both cell are wet or one dry cell is lower.
         ELSE IF( Hw(M) > ZENO .OR. Hw(N) > ZENO ) THEN

!    Cell length of UCD cells
           CNST2= Real( ICE(4,M) )
           CNST3= Real( ICE(4,N) )
!    Volume weight introduced.  JGLi28Jan2016
!    Add minimum number ZENO=1.0E-32 to avoid zero-dividing 
!    in case a dry point or Hw=0.0     JGLi03Feb2016
           CNST0= 2.0/((Hw(M)+Hw(N)+ZENO)*(CNST3+CNST2))
           CNST4= Hw(M)*CNST0*CNST3 
           CNST5= Hw(N)*CNST0*CNST2 

!    Interpolation to face in proportion of neighbouring cell sizes.
           AVT(j)= CNST4*UC(M) + CNST5*UC(N)
           AVN(j)= CNST4*VC(M) + CNST5*VC(N)

!    Project map-east velocity to local east in polar regions
           IF(j .GT. NVGL) THEN
               V(j)= ( AVN(j)*CSAnV(j) - AVT(j)*SNAnV(j) )*CNST7
              VT(j)= ( AVT(j)*CSAnV(j) + AVN(j)*SNAnV(j) )*CNST7
           ELSE
               V(j)= AVN(j)*CNST7
              VT(j)= AVT(j)*CNST7
           ENDIF

!!   End of wet-dry cell checking if-block.
         ENDIF
  
       END DO
!$OMP END Parallel DO

!!  Cell centre velocity at local east direction UCL for advective flux.
!!  Advective U-flux (and hence UCL) at polar cells are not required.
!$OMP Parallel DO Private(j,M,N,CNST0)
       DO k=1, NC-NPol

           CNST0= CNST6/CCLat( 2*ICE(2,k)+ICE(4,k) )
           IF(k .GT. NGLo) THEN
               UCL(k)= ( UC(k)*CSAnC(k) + VC(k)*SNAnC(k) )*CNST0
           ELSE
               UCL(k)= UC(k)*CNST0
           ENDIF

       END DO
!$OMP END Parallel DO

! 999  PRINT*, ' Sub UVNTerpo ended.'

       RETURN

      END SUBROUTINE UVNTerpo


! Subroutine that calculate vorticity for shallow water equation model.
!  First created:    2 Feb 2015   Jian-Guo Li
!  Last modified:    6 Feb 2015   Jian-Guo Li

      SUBROUTINE Vorticty
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        REAL, ALLOCATABLE, DIMENSION(:)::  UTDY, VTDX

!!  Tangential velocities are in Courant number form as the nornam velocities, 
!!  divided by unit face length DX or DY and muliplied by time step DT. 

!!  Allocate a few temporary variables
       ALLOCATE( UTDY(-9:NC), VTDX(-9:NC) )
       UTDY = 0.0
       VTDX = 0.0

!!  Loop over U face to calculate UT.dy of the curl operation
!$OMP Parallel DO Private(i, M, N)
       DO i=1, NU

!    Select Central and Downstream cells
           M=ISD(5,i)
           N=ISD(6,i)

!    U-face length (in unit DY) is given by ISD(3,i)
           FU(i)=UT(i)*ISD(3,i)

!    Store sub-section UT*dy in two neighbouring cells
!$OMP ATOMIC
           UTDY(M) = UTDY(M) + FU(i)
!$OMP ATOMIC
           UTDY(N) = UTDY(N) - FU(i)

       ENDDO
!$OMP END Parallel DO

!!  Loop over V face to calculate VT.dx of the curl operation
!$OMP Parallel DO Private(j, M, N)
       DO j=1, NV

!    Select Central and Downstream cells
           M=JSD(5,j)
           N=JSD(6,j)

!    Unit V-face length (in unit radian) is already included in VT 
           FV(j)=VT(j)*JSD(3,j)*CSLat( JSD(2,j) )

!    Store sub-section VT*dx in two neighbouring cells
!$OMP ATOMIC
           VTDX(M) = VTDX(M) - FV(j)
!$OMP ATOMIC
           VTDX(N) = VTDX(N) + FV(j)

       ENDDO
!$OMP END Parallel DO

!    Initialise all vorticity to be zero
       Vort=0.0

!!   Loop over cell to calculate absolute vorticity, 
!$OMP Parallel DO Private(n)
       DO n=1, NC-NPol

!    Keep vorticity to be zero if Hw = 0.   JGLi03Feb2016
         IF( Hw(n) .GT. ZENO ) THEN
!    Vorticity including DT factor.  RCELA is the area factor without CCLAT.
         Vort(n)= ( UTDY(n) + VTDX(n) )*RCELA(n)/CCLAT(2*ICE(2,n)+ICE(4,n)) + CoriF(n)
         ENDIF

       END DO
!$OMP END Parallel DO
      
!!   Polar cells are linkec by V-faces only. It is DY in radius
!!   Addd condition Hw > 0.  JGLi03Feb2016
       IF(NPol .GT. 0 .AND. Hw(NNor) .GT. ZENO) THEN
         Vort(NNor)= VTDX(NNor)*RCELA(NNor) + CoriF(NNor)
       ENDIF 
       IF(NPol .GT. 1 .AND. Hw(NSou) .GT. ZENO) THEN
         Vort(NSou)= VTDX(NSou)*RCELA(NSou) + CoriF(NSou)
       ENDIF 


       DEALLOCATE( UTDY, VTDX )

!      WRITE(6,*) " Cell centre vorticity updated for NC=", NC

! 999  PRINT*, ' Sub Vorticty ended.'

      RETURN

      END SUBROUTINE Vorticty


!!  Integral given field over whole domain, excluding boundary cells
!!  if any.  Field is assumed at cell centre.
!!
!  First created:    9 Jan 2017   Jian-Guo Li
!  Last modified:    9 Jan 2017   Jian-Guo Li

      SUBROUTINE Integral( FildC, Ftgrl )
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        REAL, INTENT( IN):: FildC(-9:NCL )
        REAL, INTENT(OUT):: Ftgrl 

        REAL, ALLOCATABLE, DIMENSION(:)::  Fild

!!  Tangential velocities are in Courant number form as the nornam velocities, 
!!  divided by unit face length DX or DY and muliplied by time step DT. 

!!  Allocate a few temporary variables
       ALLOCATE( Fild(NC) )
       Fild = FildC(1:NC)

!!  Set Arctic boundary cell values to be zero so that they are 
!!  effectively excluded in final integration.
       IF( Arctic ) THEN
          m=NGLo - NGlB + 1
          n=NGLo + NArB 
          Fild(m:n) = 0.0
       ENDIF

       CNST0 = DX0*DY
       CNST1 = 0.0

!!  Loop over all cells except for Polar cells for integration.
!$OMP Parallel DO Private(i, CNST3, CNST4)
       DO i=1, NC-NPol

!    Cell sizes and area in radian square
          CNST3=CNST0*Real( ICE(3,i)*ICE(4,i) )
          CNST4=CNST3*CCLat( 2*ICE(2,i)+ICE(4,i) )

!    Integral field over each cell
!$OMP ATOMIC
          CNST1 = CNST1 + Fild(i)*CNST4

       ENDDO
!$OMP END Parallel DO

!!  Polar cells requires a round patch area.
       IF( NPol .GT. 0 ) THEN
          CNST5=PCRDY*DY*Real( ICE(4,NNor) )
          CNST6=Pie*CNST5*CNST5
       DO i=NC-NPol+1, NC
          CNST1 = CNST1 + Fild(i)*CNST6
       ENDDO
       ENDIF

!  Pass final integration to Ftgrl
       Ftgrl = CNST1

!  Free allocated variables
       DEALLOCATE( Fild )

! 999  PRINT*, ' Sub Integral ended.'

      RETURN

      END SUBROUTINE Integral


! Subroutine that calculate error norms l1 l2 and lmax for input field.
! The sub only calculate the integration for each field.  Net l1 l2 and 
! lmax values will be this integration divided by the initial field 
! integration, which is also calculated with this sub.
!
!  First created:    2 Dec 2016   Jian-Guo Li
!  Last modified:    9 Jan 2017   Jian-Guo Li

      SUBROUTINE Errol12m( FildC, El12m )
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        REAL, INTENT( IN):: FildC(-9:NCL )
        REAL, INTENT(OUT):: El12m( 3 )

        REAL, ALLOCATABLE, DIMENSION(:)::  FAbs, FSqr

!!  Tangential velocities are in Courant number form as the nornam velocities, 
!!  divided by unit face length DX or DY and muliplied by time step DT. 

!!  Allocate a few temporary variables
       ALLOCATE( FAbs(NC), FSqr(NC) )
       FAbs = ABS( FildC(1:NC) )
       El12m(3) = MAXVAL( FAbs )

!!  Exclude boundary cells if Arctic part is present.
       IF( Arctic ) THEN
          m=NGLo - NGlB + 1
          n=NGLo + NArB
          FAbs(m:n) = 0.0
       ENDIF

       CNST1 = 0.0
       CNST2 = 0.0

       CNST0 = DX0*DY

!!  Loop over U face to calculate UT.dy of the curl operation
!$OMP Parallel DO Private(i, M, CNST3, CNST4)
       DO i=1, NC-NPol

          FSqr(i) = FAbs(i)*FAbs(i)

!    Cell sizes and area in radian square
          M=ICE(3,i)
          CNST3=CNST0*Real( ICE(3,i)*ICE(4,i) )
          CNST4=CNST3*CCLat( 2*ICE(2,i)+ICE(4,i) )

!    Error l1 and l2 top integration term 
!$OMP ATOMIC
          CNST1 = CNST1 + FAbs(i)*CNST4
!$OMP ATOMIC
          CNST2 = CNST2 + FSqr(i)*CNST4

       ENDDO
!$OMP END Parallel DO

       IF( NPol .GT. 0 ) THEN
          CNST5=PCRDY*DY*Real( ICE(4,NNor) )
          CNST6=Pie*CNST5*CNST5
       DO i=NC-NPol+1, NC
          CNST1 = CNST1 + FAbs(i)*CNST6
          CNST2 = CNST2 + FSqr(i)*CNST6
       ENDDO
       ENDIF

!  Pass final l1 and l2 top integration to El12m
       El12m(1) = CNST1
       El12m(2) = CNST2

!  Free allocated variables
       DEALLOCATE( FAbs, FSqr )

! 999  PRINT*, ' Sub Errol12m ended.'

      RETURN

      END SUBROUTINE Errol12m


! Subroutine to read cell and face arrays and to define grid variables.
!  First created:    1 Apr 2015   Jian-Guo Li
!  Last modified:   20 Jul 2022   Jian-Guo Li

      SUBROUTINE ReadCell
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        CHARACTER(Len=136):: PathName

!  Path and grid name are shared by all cell and face array files.
       PathName=TRIM(DataPath)//TRIM(GridName)

!  Read Global and Arctic part Multiple-Cell info
       OPEN(UNIT=8, FILE=TRIM(PathName)//'Cels.dat', STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, TRIM(PathName)//'Cels.dat was not opened! '
          READ (8,*) NGLo, NRLCel(1:MRL) 
       DO J=1,NGLo
          READ (8,*) (ICE(N,J), N=1,4), KG(J)
       END DO
       CLOSE(8)
       PRINT*, TRIM(PathName)//'Cels.dat read done ', NGLo, NRLCel(1:MRL) 

!!  Arctic part becomes optional.  JGLi12Dec2011
       IF( Arctic ) THEN
       OPEN(UNIT=8, FILE=TRIM(PathName)//'BArc.dat', STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*, TRIM(GridName)//'BArc.dat was not opened! '
          READ (8,*) NArc, NArB, NGLB
       DO J=NGLo+1, NGLo+NArc
          READ (8,*) (ICE(N,J), N=1,4), KG(J) 
       END DO
       CLOSE(8)
       PRINT*, TRIM(GridName)//'BArc.dat read done  NArc=', NArc

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
          WRITE(6,'(i8,2i6,2i4,i6)') J, (ICE(N,J), N=1,4), KG(J)
       END DO

!    Boundary -9 to -1 cells for cell size 2**n and 0 cell for Arctic link.
!    Note the position indice for bounary cell are not used.
       ICE(1,-9:0)=0
       ICE(2,-9:0)=0
!!  Polar linking boundary cell 0 use the same sizes as the last global cell.
       ICE(3,   0)=ICE(3, NGLo)
       ICE(4,   0)=ICE(4, NGLo)
       ICE(3,  -1)=1
       ICE(4,  -1)=1
!!   Restrict boundary cell y-size no more than base cell size
!!          2**(MRL-1).
       mm = 2**(MRL-1)
       DO i=2,9
          ICE(3,-i)=ICE(3,-i+1)*2
          ICE(4,-i)=MIN(mm, ICE(3,-i))
       ENDDO

!!  Read sorted ISD JSD variables for global part.
       OPEN(UNIT=10, FILE=TRIM(PathName)//'ISid.dat', STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,TRIM(PathName)//'ISid.dat was not opened! '
       READ(10,*) NUGL, NRLUFc(1:MRL)      
       WRITE(6,*) " Read u face numbers NUGL, NRLUFc(1:MRL)"     
       WRITE(6,*)                       NUGL, NRLUFc(1:MRL)      
       DO I=1,NUGL
          READ(10,*)  (ISD(N,I), N=1,7)
       END DO
       CLOSE(10)

       OPEN(UNIT=11, FILE=TRIM(PathName)//'JSid.dat', STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,TRIM(PathName)//'JSid.dat was not opened! '
       READ(11,*) NVGL, NRLVFc(1:MRL)     
       WRITE(6,*) " Read v face numbers NVGL, NRLVFc(1:MRL) "
       WRITE(6,*)                       NVGL, NRLVFc(1:MRL)  
       DO J=1,NVGL
!!     Dropping the last y-size parameter, which is used for sorting resolution levels.
!         READ(11,*)  (JSD(N,J), N=1,8)
          READ(11,*)  (JSD(N,J), N=1,7), kk
       END DO
       CLOSE(11)

!!  Read sorted ISD JSD variables for Arctic part.
       IF( Arctic ) THEN

       OPEN(UNIT=10, FILE=TRIM(PathName)//'AISd.dat', STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,TRIM(PathName)//'AISd.dat was not opened! '
       READ(10,*) NUAr
       WRITE(6,*) " Read u face numbers NUAr =", NUAr
       DO I=1,NUAr
          READ(10,*)  (ISD(N,I+NUGL), N=1,7)
       END DO
       CLOSE(10)

       OPEN(UNIT=11, FILE=TRIM(PathName)//'AJSd.dat', STATUS='OLD',IOSTAT=nn,ACTION='READ')
       IF(nn /= 0) PRINT*,TRIM(PathName)//'AJSd.dat was not opened! '
       READ(11,*) NVAr
       WRITE(6,*) " Read v face numbers NVAr =", NVAr
       DO J=1,NVAr
!         READ(11,*)  (JSD(N,J+NVGL), N=1,8)
          READ(11,*)  (JSD(N,J+NVGL), N=1,7), kk 
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

! 999  PRINT*, ' Sub READCELL ended.'

       RETURN

      END SUBROUTINE READCELL


!! Subroutine to separate the polar link and lateral boundary cells.
!! All lateral boundary cells will start from -1, -2, ... while the 0
!! boundary cell will be assigned to polar link boundary faces.
!  First created:   10 Aug 2022   Jian-Guo Li
!  Last modified:   11 Aug 2022   Jian-Guo Li

      SUBROUTINE ArctLink
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        INTEGER, ALLOCATABLE, DIMENSION(:):: JPolars, JPositv, JNegatv
        INTEGER :: JNMx, JNMn, JSMx, JSMn, JSiz 

!  Polar linking cells should be base resolution cells.
        JSiz = 2**(MRL - 1)

!! Work out South and North Polar region boundary j values.
!! The overlapping rows are assumed to be at NGLo-NB+1:NGLo. 
        IF( Arctic ) THEN
           ALLOCATE( JPolars(NB) )
           JPolars = ICE(2,NGLo-NB+1:NGLo)
           JPositv = PACK( JPolars, JPolars > 0 )
           JNMx = MAXVAL( JPositv ) + JSiz
           JNMn = MINVAL( JPositv )
           IF( NPol .EQ. 2 ) THEN
              JNegatv = PACK( JPolars, JPolars < 0 )
              JSMx = MAXVAL( JNegatv ) + JSiz 
              JSMn = MINVAL( JNegatv )
              WRITE(6, *) " JSMn JSMx JNMn JNMx =",JSMn,JSMx,JNMn,JNMx
           ELSE
              WRITE(6, *) "JNMn JNMx =",JNMn,JNMx
           END IF
        END IF
!$OMP Parallel
!! !$    CALL OMP_SET_NUM_THREADS(2)
!$    WRITE(6,*) "Num_Threads =",  omp_get_num_threads()

!$OMP Sections  Private(I, J, M, N)

!!  Deduct all face array boundary cell index by -1. 
        DO N=1,NU
        DO I=4,7
           IF( ISD(I,N) <= 0 ) ISD(I,N) = ISD(I,N) - 1 
        END DO
        END DO

!$OMP  Section

        DO M=1, NV
        DO J=4,7
           IF( JSD(J,M) <= 0 ) JSD(J,M) = JSD(J,M) - 1 
        END DO
        END DO

!$OMP End Sections
!$OMP Barrier

!! Assign north polar link boundary cells to be 0
        IJK = 0
        IF( Arctic ) THEN
!$OMP Parallel DO Private(M)
           DO M=1, NV
              IF( JSD(2,M) .EQ. JNMx .AND. JSD(6,M) < 0 ) THEN
                  JSD(6,M) = 0 
                  JSD(7,M) = 0 
!$OMP ATOMIC
                  IJK = IJK + 1
              ELSE IF( JSD(2,M) .EQ. JNMn .AND. JSD(5,M) < 0 ) THEN
                  JSD(5,M) = 0 
                  JSD(4,M) = 0 
!$OMP ATOMIC
                  IJK = IJK + 1
              ENDIF 
           END DO
!$OMP END Parallel DO

!! Assign south polar linking boundary cells as well
           IF( NPol .EQ. 2 ) THEN
!$OMP Parallel DO Private(M)
              DO M=1, NV
              IF( JSD(2,M) .EQ. JSMx .AND. JSD(6,M) < 0 ) THEN
                  JSD(6,M) = 0 
                  JSD(7,M) = 0 
!$OMP ATOMIC
                  IJK = IJK + 1
              ELSE IF( JSD(2,M) .EQ. JSMn .AND. JSD(5,M) < 0 ) THEN
                  JSD(5,M) = 0 
                  JSD(4,M) = 0 
!$OMP ATOMIC
                  IJK = IJK + 1
              ENDIF 
              END DO
!$OMP END Parallel DO
           ENDIF 
           WRITE(6,*) " Number of polar boundary cells adjusted =", IJK
        ENDIF 

!!    End of parallel sessions.   JGLi02Feb2024
!$OMP End Parallel

! 999  PRINT*, ' Sub ArctLink ended.'

       RETURN

      END SUBROUTINE ArctLink

! Subroutine that generates the Arctic reference direction angle
      SUBROUTINE ArctAngd
        USE SWEsCnstMD
        IMPLICIT NONE
        REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        REAL, ALLOCATABLE, DIMENSION(:)::  XLon, WLat, ELon, ELat, AnglD
        REAL ::  DfPolat, DfPolon, Omega, DfSpeed

!!    Note only the Arctic part needs the rotation angles.
!     Work out u-face central position XLon, WLat in standard grid
      CNST1=DLon*0.5
      CNST2=DLat*0.5
      DfPolat=PoLAT
      DfPolon=PoLON

      ALLOCATE( XLon(NUAr), WLat(NUAr), ELon(NUAr), ELat(NUAr), AnglD(NUAr) )
      WRITE(6,*) " Calculating U component ..."

!$OMP Parallel DO Private(i, L)
      DO L=1, NUAr
         i=L+NUGL 
!!  U-face latitude with half dlat increase from SW corner
!!  Note j is from -NLat2 to NLat2 and j=0 corresponds to v-face on the Equator
!!  Longitude is measured half-grid from ZLon and first cell i=0 coicides with XLon=0.
         XLon(L)= Float( ISD(1,i) )*DLon + ZLon
         WLat(L)= Float( ISD(2,i) )*DLat + Float( ISD(3,i) )*CNST2 + ZLat

      END DO
!$OMP END Parallel DO

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NUAr)

!$OMP Parallel DO Private(i, L)
      DO L=1, NUAr
         i=L+NUGL 
!!  Convert the AnglD into rad and store SIN/COS. 
         CSAnU(i)=COS( AnglD(L)*D2RAD ) 
         SNAnU(i)=SIN( AnglD(L)*D2RAD ) 
      END DO
!$OMP END Parallel DO

      DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )

        ALLOCATE( XLon(NVAr), WLat(NVAr), ELon(NVAr), ELat(NVAr), AnglD(NVAr) )

!     Work out v-face central position XLon, WLat in standard grid
!$OMP Parallel DO Private(j, L)
      DO L=1, NVAr
         j=L+NVGL
!!  V-face latitude is the same as its SW corner point.
         XLon(L)= Float( JSD(1,j) )*DLon + CNST1*Float( JSD(3,j) ) + ZLon
         WLat(L)= Float( JSD(2,j) )*DLat + ZLat
      END DO
!$OMP END Parallel DO

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NVAr)

!$OMP Parallel DO Private(j, L)
      DO L=1, NVAr
         j=L+NVGL
!!  Convert the AnglD into rad and store SIN/COS 
         CSAnV(j)=COS( AnglD(L)*D2RAD ) 
         SNAnV(j)=SIN( AnglD(L)*D2RAD ) 
      END DO
!$OMP END Parallel DO

      DEALLOCATE( XLon, WLat, ELon, ELat, AnglD )


!! Specific cell centre velocity compenents
      ALLOCATE( XLon(NArc), WLat(NArc), ELon(NArc), ELat(NArc), AnglD(NArc) )
      WRITE(6,*) " Calculating UC, VC component ..."

      CNST1=DLon*0.5
      CNST2=DLat*0.5
!! All cells include the polar cells (NPol).
!! Note the wlat is not at 90N for the polar cell as direction will be undefined.
!! Here Wlat is half dlat from the polar cell edge and half dlat from the NP.
!$OMP Parallel DO Private(i, L)
      DO L=1, NArc-NPol
         i=L+NGLo

!!  Cell centre longitude with half cell width increase from West side centre
!!  Although the polar cell is of angular radius dlat (not dlat/2) the 
!!  transformation location is still used dlat/2 from its SW corner. The error
!!  will be negeligible as only the AnglD is used.
         XLon(L)= Float( ICE(1,i) )*DLon + CNST1*Float( ICE(3,i) ) + ZLon
         WLat(L)= Float( ICE(2,i) )*DLat + CNST2*Float( ICE(4,i) ) + ZLat

      END DO
!$OMP END Parallel DO

!! AnglD will be undefined at poles as no local east at poles.  So polar
!! cell centres are shifted half-grid length off the Poles.
      IF( NPol .GT. 0 ) THEN
      DO L=NArc-NPol+1, NArc
         i=L+NGLo
         XLon(L)= Float( ICE(1,i) )*DLon + ZLON
         WLat(L)= Float( ICE(2,i) )*DLat + CNST2*Float(ICE(4,L))*0.5 + ZLat
      ENDDO
      ENDIF

!!  Convert standard lat/lon into rotated lat/lon for deformation wind
      CALL LLTOEQANGLE( WLat, XLon, ELat, ELon,     &
     &                 AnglD, DfPolat, DfPolon, NArc )

!$OMP Parallel DO Private(i, L)
      DO L=1, NArc
         i=L+NGLo
!!  Keep the AnglD in Deg and store in AngCD(L).  Spectral rotation for
!!  boundary cell update will use this angle later.
         AngCD(i)=  AnglD(L) 
         CSAnC(i)=COS( AnglD(L)*D2RAD ) 
         SNAnC(i)=SIN( AnglD(L)*D2RAD ) 
      END DO
!$OMP END Parallel DO

!!  Output AngCD for checking
!     WRITE(6,        *)  "(AngCD(L+NGLo), L=1, NArc)"
!     WRITE(6,'(8ES12.3)') (AngCD(L+NGLo), L=1, NArc)

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


! 999  PRINT*, ' Sub ArctAngd ended.'

      RETURN

      END SUBROUTINE ArctAngd


!! Subroutine that writeout a full cell list variable to a file.
       SUBROUTINE WRITEOUT( CWrt, NTSP, FD)
        USE SWEsCnstMD
        IMPLICIT NONE
        CHARACTER(LEN=2), INTENT(IN):: FD
        INTEGER,   INTENT(IN):: NTSP
        REAL,      INTENT(IN):: CWrt(-9:NCL)
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        CHARACTER(LEN=12):: FL9NM='FD10000000.d'

!!   File name with time step mark
        WRITE(FL9NM(1:2), FMT='(A2)' )  FD
        WRITE(FL9NM(3:10), FMT='(i8)' )  10000000+NTSP
        OPEN(UNIT=26, FILE=FL9NM, STATUS='UNKNOWN',IOSTAT=nn)
        IF(nn /= 0) PRINT*,' File FL9NM was not opened! '
        WRITE(UNIT=6,FMT='(2x,"NT= ",i8,3x,A)') NTSP, FL9NM

!$OMP Parallel DO Private(i)
        DO i=1, NC
           D(i) = CWrt(i)
!!   Filter very small CWrt value so it is greater than E-90
           IF( Abs(D(i)) .LT. 1.0E-90 ) THEN
               D(i)=SIGN(1.0E-90, CWrt(i))
           ENDIF
!!   Filter very large CWrt value so it is less than 9.99E90
           IF( Abs(D(i)) .GT. 9.99E90 ) THEN
               D(i)=SIGN(9.99E90, CWrt(i))
           ENDIF

        ENDDO
!$OMP END Parallel DO


!    All cells are saved 
        WRITE(UNIT=26, FMT='(2x,2i8)' )  NTSP, NC
        WRITE(UNIT=26, FMT=7113)  (D(n),  n=1, NC)

        CLOSE(26)

 7113   FORMAT( 1x, 7ES11.3 )

! 999   PRINT*, ' Sub WRITEOUT ended.'
        RETURN

       END SUBROUTINE WRITEOUT 


! Subroutine that writeout a full cell list vector variables to a file.
       SUBROUTINE WRITEUVs( UCwt, VCwt, NTSP)
        USE SWEsCnstMD
        IMPLICIT NONE
        INTEGER, INTENT(IN):: NTSP
        REAL,    INTENT(IN):: UCwt(-9:NCL), VCwt(-9:NCL)
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        CHARACTER(LEN=12):: FL10NM='UV10000000.d'

!!   File name with time step mark
        WRITE(FL10NM(3:10), FMT='(i8)' )  10000000+NTSP
        OPEN(UNIT=26, FILE=FL10NM, STATUS='UNKNOWN',IOSTAT=nn)
        IF(nn /= 0) PRINT*,' File FL9NM was not opened! '
        WRITE(UNIT=6,FMT='(2x,"NT= ",i8,3x,A)') NTSP, FL10NM

!$OMP Parallel DO Private(i)
        DO i=1, NC
           A(i) = UCwt(i)
           D(i) = VCwt(i)
!!   Filter very small CWrt value so it is greater than E-90
           IF( Abs(A(i)) .LT. 1.0E-90 ) THEN
               A(i)=SIGN(1.0E-90, UCwt(i))
           ENDIF
           IF( Abs(D(i)) .LT. 1.0E-90 ) THEN
               D(i)=SIGN(1.0E-90, VCwt(i))
           ENDIF
!!   Filter very large CWrt value so it is less than 9.99E90
           IF( Abs(A(i)) .GT. 9.99E90 ) THEN
               A(i)=SIGN(9.99E90, UCwt(i))
           ENDIF
           IF( Abs(D(i)) .GT. 9.99E90 ) THEN
               D(i)=SIGN(9.99E90, VCwt(i))
           ENDIF
        ENDDO
!$OMP END Parallel DO

!    All cells are saved 
        WRITE(UNIT=26, FMT='(2x,3i8)' )  NTSP, NC, 2
!       WRITE(UNIT=26, FMT=7123)  (A(n),  n=1, NC)
!       WRITE(UNIT=26, FMT=7123)  (D(n),  n=1, NC)
        WRITE(UNIT=26, FMT=6123)  (A(n), D(n),  n=1, NC)

        CLOSE(26)

 7123   FORMAT( 1x, 7ES12.3 )
 6123   FORMAT( (6ES12.3) )

! 999   PRINT*, ' Sub WRITEUVs ended.'
        RETURN

       END SUBROUTINE WRITEUVs 

! Subroutine that reads a full cell list velocity and water height variables 
! from a restart file, which could be created by merging a UV and Hw output.
       SUBROUTINE READUVHs( UCwt, VCwt, Hwst, NTSP)
        USE SWEsCnstMD
        IMPLICIT NONE
        INTEGER, INTENT(OUT):: NTSP
        REAL,    INTENT(OUT):: UCwt(-9:NCL), VCwt(-9:NCL), Hwst(-9:NCL)
        REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
        CHARACTER(LEN=10):: FL10NM='Restarts.d'

!!   File name with time step mark
!       WRITE(FL10NM(3:8), FMT='(i6)' )  100000+NTSP
        OPEN(UNIT=26, FILE=FL10NM, STATUS='Old',IOSTAT=nn)
        IF(nn /= 0) PRINT*,' File FL10NM was not opened! '
!       WRITE(UNIT=6,FMT='(2x,"Restart NS= ",i6,3x,A10)') NTSP, FL10NM

!!   Initial all UC and VC to be zero
        UCwt = 0.0
        VCwt = 0.0
        Hwst = 0.0

!    All cell values are resigned. 
        READ(26, *)  NTSP, MM
        WRITE(UNIT=6,FMT='(2x,"UCVC at NS= ",i6,3x,A10)') NTSP, FL10NM

        READ(26, *)  (UCwt(n), VCwt(n),  n=1, MM)
!       READ(26, *)  (VCwt(n),  n=1, MM)

!    Read appended Hw+Btm from the same file
        READ(26, *)  NTSP, MM
        WRITE(UNIT=6,FMT='(2x,"Hw+Btm  NS= ",i6,3x,A10)') NTSP, FL10NM

        READ(26, *)  (Hwst(n),  n=1, MM)

        CLOSE(26)
        IF( MM .NE. NC ) PRINT*, ' *** Warning ***, unmatching NC', MM, NC

! 999   PRINT*, ' Sub READUVHs ended.'
        RETURN

       END SUBROUTINE READUVHs 

!/ End of module SWEsDynaMD. ------------------------------------------/
!/
       END MODULE SWEsDynaMD
! 
