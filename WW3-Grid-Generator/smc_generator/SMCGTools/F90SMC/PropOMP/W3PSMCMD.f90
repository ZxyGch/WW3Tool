!/ ------------------------------------------------------------------- /
      MODULE W3PSMCMD
!/
!/                  +------------------------------------+
!/                  | Spherical Multiple-Cell (SMC) grid |
!/                  | Adv, GCT, Rfr, Dif subroutines.    |
!/                  |           Jian-Guo Li              |
!/                  | First created:     8 Nov 2010      |
!/                  | Last modified:    18 Oct 2021      |
!/                  +------------------------------------+
!/
!/    Simplified version for propagation test.  JGLi10Jul2019
!/
!  1. Purpose :
!
!     Bundles routines for SMC advection (UNO2) and diffusion schemes in 
!     single module, including GCT and refraction rotation schemes.
!
!  3. Subroutines and functions :
!
!      Name      Type  Scope    Description
!     ----------------------------------------------------------------
!      W3PSMC    Subr. Public   Spatial propagation on SMC grid.
!      W3KSMC    Subr. Public   Spectral modification by GCT and refraction.
!      SMCxUNO2  Subr. Public   Irregular grid mid-flux on U-faces by UNO2.
!      SMCyUNO2  Subr. Public   Irregular grid mid-flux on V-faces by UNO2.
!      SMCkUNO2  Subr. Public   Shift in k-space due to refraction by UNO2.
!      SMCGtCrfr Subr. Public   Refraction and GCT rotation in theta.
!      SMCDHXY   Subr. Public   Evaluate depth gradient and refraction limiter.
!      SMCDCXY   Subr. Public   Evaluate current velocity gradient.
!      SMCGradn  Subr. Public   Evaluate local gradient for sea points.
!      SMCAverg  Subr. Public   Numerical 1-2-1 average of sea point field.
!      W3GATHSMC W3SCATSMC      Gather and scatter spectral components.
!     ----------------------------------------------------------------
!/
!/ Use omp_lib for OpenMP functions if switched on.   JGLi10Jan2018
!$       USE omp_lib
!/

      CONTAINS

!/ ------------------------------------------------------------------- /
!/
      SUBROUTINE W3PSMC ( ITH, IK, MT, VQ )
!/
!/                  +------------------------------------+
!/                  | Spherical Multiple-Cell (SMC) grid |
!/                  | Advection and diffusion sub.       |
!/                  | First created:   JG Li  8 Nov 2010 |
!/                  | Last modified:   JG Li 26 Apr 2017 |
!/                  +------------------------------------+
!/
!/    08-Nov-2010 : Origination.                JGLi    ( version 1.00 )
!/    16-Dec-2010 : Check U/V CFL values.       JGLi    ( version 1.10 )
!/    18-Mar-2011 : Check MPI communication.    JGLi    ( version 1.20 )
!/    16-May-2011 : Tidy up diagnosis lines.    JGLi    ( version 1.30 )
!/     4 Nov-2011 : Separate x and y obstruc.   JGLi    ( version 1.40 )
!/     5 Jan-2012 : Multi-resolution SMC grid.  JGLi    ( version 1.50 )
!/     2 Feb-2012 : Separate single multi adv.  JGLi    ( version 1.60 )
!/     6 Mar-2012 : Minor adjustments of CLATF. JGLi    ( version 1.70 )
!/    12 Feb-2012 : Remove net flux bug.        JGLi    ( version 1.80 )
!/    16 Sep-2013 : Add Arctic part.            JGLi    ( version 2.00 )
!/     3 Sep-2015 : Gradient, UNO3 and Average. JGLi    ( version 2.10 )
!/    26 Feb-2016 : Update boundary spectra.    JGLi    ( version 2.20 )
!/    23 Mar-2016 : Add current option.         JGLi    ( version 2.30 )
!/    26 Apr-2017 : Adapted for local refraction program.  JGLi26Apr2017
!/
!  1. Purpose :
!
!     Propagation in phyiscal space for a given spectral component.
!
!  2. Method :
!
!     Unstructured SMC grid, point-oriented face and cell loops.
!     UNO2 advection scheme and isotropic FTCS diffusion scheme. 
!
!/ ------------------------------------------------------------------- /
      USE CONSTANTS
      IMPLICIT NONE
!/
!/ ------------------------------------------------------------------- /
!/ Parameter list
!/
      INTEGER, INTENT(IN)     :: ITH, IK, MT
      REAL,    INTENT(INOUT)  :: VQ(NSEA)
!/
!/ ------------------------------------------------------------------- /
!/ Local parameters
!/
      INTEGER                 :: NTLOC, ITLOC, ISEA, IXY,    &
                                 IY, IY0, IP, IBI 
      REAL                    :: CG0, CGA, CGN, CGX, CGY, FMR, RD1,   &
                                 RD2, CXMIN, CXMAX, CYMIN, CYMAX,     &
                                 CXC, CYC, DTLDX, DTLDY 
      REAL                    :: DTLOC, CGCOS, CGSIN, FUTRN, FVTRN,   &
                                 DFRR, DX0I, DY0I, CGD, DSSD,ARCTH,   &
                                 DNND, DCELL, XWIND, TFAC, DSS, DNN
!/
!/ Automatic work arrays
!
      REAL, Dimension(-9:NCL) ::  FCNt, AFCN, BCNt, UCFL, VCFL, CQ,  &
                                   CQA, CXTOT, CYTOT
      REAL, Dimension(   NFC) ::  FUMD, FUDIFX, ULCFLX
      REAL, Dimension(   NFC) ::  FVMD, FVDIFY, VLCFLY

      LOGICAL ::  YFIRST

! 1.  Preparations --------------------------------------------------- *

!!Li  Maximum group speed for 1st and the transported frequency bin
!!Li  A factor of 1.2 is added to account for the shallow water peak.
      CG0    = 0.6 * GRAV / SIG(1)
      CGA    = 0.6 * GRAV / SIG(IK)

!!Li  Maximum group speed for given spectral bin. First bin speed is 
!!Li  used to avoid zero speed component.
      CGX    =  CGA * ECOS(ITH) 
      CGY    =  CGA * ESIN(ITH) 

!!Li  Add maximum current components to maximum group components.
      IF ( FLCUR ) THEN
          CXMIN  = MINVAL ( CX(1:NC) )
          CXMAX  = MAXVAL ( CX(1:NC) )
          CYMIN  = MINVAL ( CY(1:NC) )
          CYMAX  = MAXVAL ( CY(1:NC) )
          IF ( ABS(CGX+CXMIN) .GT. ABS(CGX+CXMAX) ) THEN
              CGX    = CGX + CXMIN
            ELSE
              CGX    = CGX + CXMAX
            END IF
          IF ( ABS(CGY+CYMIN) .GT. ABS(CGY+CYMAX) ) THEN
              CGY    = CGY + CYMIN
            ELSE
              CGY    = CGY + CYMAX
            END IF
          CXC    = MAX ( ABS(CXMIN), ABS(CXMAX) )
          CYC    = MAX ( ABS(CYMIN), ABS(CYMAX) )
        ELSE
          CXC    = 0.
          CYC    = 0.
        END IF

!!Li  Base-cell grid lenth at Equator (size-4 on SMC625 grid).
      DX0I  = 1.0/(SX * D2RAD * REARTH)
      DY0I  = 1.0/(SY * D2RAD * REARTH)

!!Li  Miminum time step determined by Courant number < 0.8
!!Li  Note, minimum x grid length is half the Equator value.
!!Li  Minimum time step should not be less than sub w3init requirement,
!!Li  where IAPPRO array is initialised for propagation parallization.
      CGN   = 0.9999 * MAX( ABS(CGX), ABS(CGY), CXC, CYC, 0.001*CG0 )
      DTLOC = DTCFL*CG0/CGN 
      NTLOC  = 1 + INT(DTG/DTLOC - 0.001)
      DTLOC  = DTG / REAL(NTLOC)

!!Li  Group speed component common factors, FACX=DTG*DX0I 
!!Li  FACX and FACY are evaluated here directly.  JGLi16Jan2013
!     CGCOS   = FACX * ECOS(ITH) / REAL(NTLOC)
!     CGSIN   = FACY * ESIN(ITH) / REAL(NTLOC)
      CGCOS   = ECOS(ITH)
      CGSIN   = ESIN(ITH)
      DTLDX   = DTLOC * DX0I 
      DTLDY   = DTLOC * DY0I 
!
      YFIRST = MOD(MT,2) .EQ. 0
!
!Li   Homogenous diffusion Fourier number DNND and DSSD will be used.
!Li   They have to be divided by base-cell size for size-1 stability.
!Li   So they are equivalent to the Fourier number in size-1 cell at
!Li   the sub-time step DTLOC/MRFct.
      IF ( DTME .GT. 0. ) THEN
          DFRR   = XFR - 1.
          CGD    = 0.5 * GRAV / SIG(IK)
          DNN    = ((DThta*CGD)**2)*DTME / 12.
          DNND   = DNN*DTLOC*(DX0I*DX0I)
          DSSD   = DNN*DTLOC*(DY0I*DY0I)
      ELSE
          DSSD = 0.0
          DNND = 0.0
      END IF
!
! 1.b Initialize arrays
!
!/T      WRITE (NDST,9010)
!
      UCFL   = 0.
      VCFL   = 0.
      ULCFLX = 0.
      VLCFLY = 0.
      CXTOT  = 0. 
      CYTOT  = 0. 
      CQ     = 0.
!$OMP Parallel DO
!Li    Pass spectral element to CQ and filter out NaN value if any.
      DO ISEA=1, NSEA
!Li  Transported variable is divided by CG as in WW3 (???)
!        CQ(ISEA) = WSpc(ITH, IK, ISEA)/CGrp(IK,ISEA)
         CQ(ISEA) = VQ(ISEA)/CGrp(IK,ISEA)
!Li  Resetting NaNQ VQ to zero if any.   JGLi18Mar2013
         IF( .NOT. (CQ(ISEA) .EQ. CQ(ISEA)) )  CQ(ISEA) = 0.0
      END DO
!$OMP END Parallel DO

!Li  Add current components if any to wave velocity.
      IF ( FLCUR ) THEN
!$OMP Parallel DO
         DO ISEA=1, NSEA
            CXTOT(ISEA) = (CGCOS * CGrp(IK,ISEA) + CX(ISEA))
            CYTOT(ISEA) = (CGSIN * CGrp(IK,ISEA) + CY(ISEA))
         END DO 
!$OMP END Parallel DO
      ELSE
!Li   No current case use group speed only.
!$OMP Parallel DO
         DO ISEA=1, NSEA
            CXTOT(ISEA) =  CGCOS * CGrp(IK,ISEA) 
            CYTOT(ISEA) =  CGSIN * CGrp(IK,ISEA)
         END DO 
!$OMP END Parallel DO
!Li   End of IF( FLCUR ) block.
      ENDIF

!Li   Arctic cell velocity components need to be rotated 
!Li   back to local east referenence system for propagation.
      IF( Arctic ) THEN
         DO ISEA=NGLO+1, NSEA
            ARCTH = AngArc(ISEA-NGLo)*D2RAD 
            CXC = CXTOT(ISEA)*COS(ARCTH) + CYTOT(ISEA)*SIN(ARCTH)
            CYC = CYTOT(ISEA)*COS(ARCTH) - CXTOT(ISEA)*SIN(ARCTH)
            CXTOT(ISEA) = CXC 
            CYTOT(ISEA) = CYC 
         END DO

!Li   V-component is reset to zero for Polar cell as direction
!Li   is undefined there.  
         IF(NPol .GT. 0) CYTOT(NSEA-NPol+1:NSEA) = 0.0
      ENDIF 

!$OMP Parallel DO
!Li     Convert velocity components into CFL factors.
         DO ISEA=1, NSEA
            UCFL(ISEA) = DTLDX*CXTOT(ISEA)/CLATS(ISEA)
            VCFL(ISEA) = DTLDY*CYTOT(ISEA) 
         ENDDO 
!$OMP END Parallel DO

!Li  Initialise boundary cell CQ and Velocity values.
           CQ(-9:0)=0.0
         UCFL(-9:0)=0.0
         VCFL(-9:0)=0.0
!
! 3.  Loop over frequency-dependent sub-steps -------------------------*
!
       DO ITLOC=1, NTLOC
!
!     Initialise net flux arrays.
          FCNt(-9:NCL) = 0.0
          AFCN(-9:NCL) = 0.0
          BCNt(-9:NCL) = 0.0
!
!     Multi-resolution SMC grid uses irregular grid advection scheme
!     without partial blocking when MRL > 1
!
! 3.a    Multiresolution sub-steps depend on refined levels MRFct
         DO LMN = 1, MRFct
!
! 3.b    Loop over all levels, starting from the finest level.
           DO LL= 1, MRL

!        Cell size of this level
              LvR=2**(LL - 1)
              FMR=REAL( LvR )
!
! 3.c    Calculate this level only if size is factor of LMN 
           IF( MOD(LMN, LvR) .EQ. 0 ) THEN
!
! 3.d    Select cell and face ranges 
           icl=NRLCel(LL-1)+1
           iuf=NRLUFc(LL-1)+1
           ivf=NRLVFc(LL-1)+1
           jcl=NRLCel(LL)
           juf=NRLUFc(LL)
           jvf=NRLVFc(LL)
!
!  Use 3rd order UNO3 scheme.  JGLi03Sep2015
!          IF( FUNO3 ) THEN
!          CALL SMCxUNO3(iuf, juf, CQ, UCFL, ULCFLX, DNND, FUMD, FUDIFX, FMR)
!          ELSE
!  Call SMCxUNO2 to calculate finest level (size-1) MFx value
           CALL SMCxUNO2(iuf, juf, CQ, UCFL, ULCFLX, DNND, FUMD, FUDIFX, FMR)
!          ENDIF

!  Store fineset level conservative flux in FCNt advective one in AFCN
!! No partial blocking for multi-resolution SMC grid.  JGLi02Feb2012

!$OMP Parallel DO Default(Shared), Private(i,L,M,FUTRN)
           DO i=iuf, juf 
              L=ISD(5,i)
              M=ISD(6,i)
              FUTRN = FUMD(i)*ULCFLX(i) - FUDIFX(i)
!! Remove boundary cell flux update or L M > 0.  JGLi28Mar2019
           IF( L > 0 ) THEN
!$OMP ATOMIC 
              FCNt(L) = FCNt(L) - FUTRN 
!$OMP ATOMIC 
              AFCN(L) = AFCN(L) - (FUMD(i)*UCFL(L)*FMR - FUDIFX(i))
           ENDIF
           IF( M > 0 ) THEN
!$OMP ATOMIC 
              FCNt(M) = FCNt(M) + FUTRN 
!$OMP ATOMIC 
              AFCN(M) = AFCN(M) + (FUMD(i)*UCFL(M)*FMR - FUDIFX(i))
           ENDIF
           ENDDO
!$OMP END Parallel DO

!  Store conservative update in D and advective update in C
!  The side length in MF value has to be cancelled with cell y-length.
!  Also divided by another cell x-size as UCFL is in size-1 unit.
!$OMP Parallel DO
           DO n=icl, jcl 
              CQA(n)=CQ(n) + FCNt(n)*RCELA(n)
              CQ (n)=CQ(n) + AFCN(n)*RCELA(n) 
              FCNt(n)=0.0
              AFCN(n)=0.0
           ENDDO
!$OMP END Parallel DO
!
!  Use 3rd order UNO3 scheme.  JGLi03Sep2015
!          IF( FUNO3 ) THEN
!          CALL SMCyUNO3(ivf, jvf, CQ, VCFL, VLCFLY, DSSD, FVMD, FVDIFY, FMR)
!          ELSE
!  Call SMCyUNO2 to calculate MFy value
           CALL SMCyUNO2(ivf, jvf, CQ, VCFL, VLCFLY, DSSD, FVMD, FVDIFY, FMR)
!          ENDIF
!
!  Store conservative flux in F
!! No partial blocking for multi-resolution SMC grid.  JGLi02Feb2012

!$OMP Parallel DO Default(Shared), Private(j,L,M,FVTRN)
           DO j=ivf, jvf 
              L=JSD(5,j)
              M=JSD(6,j)
              FVTRN = FVMD(j)*VLCFLY(j) - FVDIFY(j)
           IF( L > 0 ) THEN
!$OMP ATOMIC 
              BCNt(L) = BCNt(L) - FVTRN 
           ENDIF
           IF( M > 0 ) THEN
!$OMP ATOMIC 
              BCNt(M) = BCNt(M) + FVTRN 
           ENDIF
           ENDDO
!$OMP END Parallel DO

!  Store conservative update of D in C
!  The v side length in MF value has to be cancelled with x-size. 
!  Also divided by cell y-size as VCFL is in size-1 unit.
!! One cosine factor is also needed to be divided for SMC grid
!$OMP Parallel DO
           DO n=icl, jcl
              CQ(n)=CQA(n) + BCNt(n)*RCELA(n)/CLATS(n) 
              BCNt(n)=0.0
           ENDDO
!$OMP END Parallel DO
!
!  End of refine level if block  MOD(LMN, LvR) .EQ. 0 
           ENDIF

!  End of refine level loop LL=1, MRL
           ENDDO
!!
!!    END of multi-resolution sub-step loop LMN = 1, MRFct
         ENDDO

!!    End of ITLOC DO
       ENDDO
 
!  Average with 1-2-1 scheme.  JGLi20Aug2015
       IF(FVERG) CALL SMCAverg(CQ)

!
! 4.  Store results in VQ in proper format --------------------------- *
!
         NN = 0
!$OMP Parallel DO
      DO ISEA=1, NSEA
!Li  Resetting NaNQ VQ to zero if any.   JGLi14Nov2017
         IF( .NOT. (CQ(ISEA) .EQ. CQ(ISEA)) ) THEN
             CQ(ISEA) = 0.0
             NN = NN + 1
         ENDIF
!!Li  Assign spectral component to full sea point array
!        WSpc(ITH, IK, ISEA) = MAX(0.0, CQ(ISEA)*CGrp(IK,ISEA) )
         VQ(ISEA) = MAX(0.0, CQ(ISEA)*CGrp(IK,ISEA) )
        END DO
!$OMP END Parallel DO
        IF( NN > 0 ) WRITE(6,*) NN," NaN found PSMC end at ITH IK NT=", ITH, IK, MT
!
      RETURN
!
!/ End of W3PSMC ----------------------------------------------------- /
!/
      END SUBROUTINE W3PSMC
!/
!/ ------------------------------------------------------------------- /
!/
!     SUBROUTINE W3KRTN ( ISEA, MT ) 
      SUBROUTINE W3KRTN ( MT ) 
!     SUBROUTINE W3KRTN ( ISEA, FACTH, FACK, CTHG0, CG, WN, DEPTH,    &
!                         DDDX, DDDY, ALFLMT, CX, CY, DCXDX, DCXDY,   &
!                         DCYDX, DCYDY, DCDX, DCDY, VA )
!/
!/                  +------------------------------------+
!/                  | Spherical Multiple-Cell (SMC) grid |
!/                  | Refraction and great-cirle turning |
!/                  |           Jian-Guo Li              |
!/                  | First created:     8 Nov 2010      |
!/                  | Last modified:    18 Oct 2021      |
!/                  +------------------------------------+
!/
!/    08-Nov-2010 : Origination.                        ( version 1.00 )
!/    10-Jun-2011 : New refraction formulation.         ( version 1.10 )
!/    16-Jun-2011 : Add refraction limiter to gradient. ( version 1.20 )
!/    21-Jul-2011 : Old refraction formula + limiter.   ( version 1.30 )
!/    26-Jul-2011 : Tidy up refraction schemes.         ( version 1.40 )
!/    28-Jul-2011 : Finalise with old refraction.       ( version 1.50 )
!/    23-Mar-2016 : Add current option in refraction.   ( version 2.30 )
!/    28-Apr-2017 : Adapted for independent refraction program.   JGLi
!/    18-Oct-2021 : Merge with PropHyb module for consistency.    JGLi
!/
!/
!  1. Purpose :
!
!     Refraction and great-circle turning by spectral rotation.
!
!  2. Method :
!
!     Linear interpolation equivalent to 1st order upstream scheme 
!     but without restriction on rotation angle.  However, refraction 
!     is limited towards the depth gradient direction (< 90 degree).
!     Refraction induced spectral shift in the k-space will remain 
!     to be advected using the UNO2 scheme.
!
!  4. Subroutines used :
!
!       SMCGtCrfr Refraction and GCT rotation in theta.
!       SMCkUNO2  Refraction shift in k-space by UNO2.
!
!/ ------------------------------------------------------------------- /
      USE CONSTANTS
      IMPLICIT NONE
!/
!/ ------------------------------------------------------------------- /
!/ Parameter list
!/
      INTEGER, INTENT(IN) :: MT
!     INTEGER, INTENT(IN) :: ISEA, MT
!     REAL, INTENT(IN)    :: FACTH, FACK, CTHG0, CG(0:NK+1),      &
!                            WN(0:NK+1), DEPTH, DDDX, DDDY,       &
!                            ALFLMT(NTH), CX, CY, DCXDX, DCXDY,   & 
!                            DCYDX, DCYDY, DCDX(0:NK+1), DCDY(0:NK+1) 
!     REAL, INTENT(INOUT) :: VA(NSPEC)
!/
!/ ------------------------------------------------------------------- /
!/ Local parameters
!/
      INTEGER    :: ITH, IK, ISP, ISEA 
      REAL       :: FGC, FKD, FKS, DEPTH30, CFLK(NDir,0:NFrq)
      REAL, Dimension(NFrq):: FRK, FRG
      REAL, Dimension(NDir):: DDNorm, FKC
      REAL, Dimension(NDir, NFrq):: VQ, VCFLT 
      REAL       :: DM(-1:NFrq+1), DB(0:NFrq+1), SIGSNH(0:NFrq+1)

!Li  Local sea point loop is moved inside the sub.  JGLi18Oct2021
!$OMP Parallel DO Default(Shared),                                  &
!$OMP             Private(FRK,FRG,FKC,VQ,VCFLT,DM,DB,SIGSNH,CFLK),  &
!$OMP             Private(ITH,IK,ISP,ISEA,FGC,FKD,FKS,DEPTH30,DDNorm)

      DO ISEA=1, NC-NPol 

! 1.  Preparation for point ------------------------------------------ *
!     Array with partial derivative of sigma versus depth
!Li   Use of minimum depth 30 m for refraction factor.  JGLi12Feb2014
      DEPTH30=MAX(30.0, HCel(ISea))

      DO IK=0, NFrq+1
!Li   Refraction factor uses minimum depth of 30 m.  JGLi12Feb2014
!Li   Maximum of phase 50.0 radian is imposed by Arun Chawla.  JGLi16Feb2017
          SIGSNH(IK) = SIG(IK)/SINH(MIN(2.0*Wnmk(IK,ISea)*DEPTH30,50.0))
        END DO
!
! 2.  Extract spectrum without mapping
!
         VQ = WSpc(:,:,ISEA)

!Li  Resetting NaNQ VQ to zero if any.   JGLi14Nov2017
!     WHERE( .NOT. (VQ .EQ. VQ) )
!        VQ = 0.0
!     ENDWHERE 

! 3.  Refraction velocities ------------------------------------------ *
!
!
      IF ( FLCTH ) THEN
!
! 3.a Set slope filter for depth refraction
!
!Li   Lift theta-refraction limit and use new formulation.   25 Nov 2010
          FGC    = DTG*CTHG0S(ISEA)/DThta
!
          DO IK=1, NFrq
            FRK(IK) = DTG * SIGSNH(IK)
            FRG(IK) = FGC * CGrp(IK,ISEA)
          END DO
!
!Li   Current induced refraction stored in FKC.    JGLi30Mar2016
!Li   Put a CTMAX limit on current theta rotation.  JGLi02Mar2017
          IF ( FLCUR ) THEN
             DO ITH=1, NDir
                FGC = DTG*( DCYDX(ISEA)*ES2(ITH) - DCXDY(ISEA)*EC2(ITH) +  & 
                                  (DCXDX(ISEA) - DCYDY(ISEA))*ESC(ITH) )
                FKC(ITH) = SIGN( MIN(ABS(FGC), CTMAX), FGC )
             END DO
          ELSE
                FKC(:)=0.0
          END IF
!
! 3.b Depth refraction and great-circle turning.
!
          DO ITH=1, NDir
             DDNorm(ITH)=ESIN(ITH)*DHDX(ISEA)-ECOS(ITH)*DHDY(ISEA)
             DO IK=1, NFrq
!Li   Apply depth gradient limited refraction, current and GCT term
                VCFLT(ITH,IK)=FRG(IK)*ECOS(ITH) + FKC(ITH) +          & 
                SIGN( MIN(ABS(FRK(IK)*DDNorm(ITH)), DHLMT(ITH,ISEA)), &
                                      DDNorm(ITH) )
             END DO
          END DO

      END IF
!
! 4.  Wavenumber shift velocities due to current refraction ---------- *
!
      IF ( FLCK ) THEN
!
! 4.a Directionally dependent part
!
          DO ITH=1, NDir
!Li   Depth induced refraction is suspended as it is absorbed in
!Li   the fixed frequency bin used for wave spectrum.  JGLi30Mar2016
!           FKC(ITH) = ( ECOS(ITH)*DDDX + ESIN(ITH)*DDDY )
            FKC(ITH) = -DCXDX(ISEA)*EC2(ITH) -DCYDY(ISEA)*ES2(ITH)     &
                       -(DCXDY(ISEA) + DCYDX(ISEA))*ESC(ITH)
            END DO
!Li   Reset any NaN values in current 2nd order gradients. JGLi14Nov2017
!         WHERE( .NOT. (FKC .EQ. FKC) )
!           FKC = 0.0
!         ENDWHERE
!
! 4.b Band widths
!
!Li  Cell and side indices for k-dimension are arranged as
!    Cell:    | -1 | 0 | 1 | 2 | ... | NK | NK+1 | NK+2 |
!    Side:        -1   0   1   2 ...     NK     NK+1
!Li  DSIP = SIG(K+1) - SIG(K), radian frequency increment
!
          DO IK=0, NFrq
            DB(IK) = DSIP(IK) / CGrp(IK,ISEA)
            DM(IK) = WNmk(IK+1,ISEA) - WNmk(IK,ISEA)
            END DO
          DB(NFrq+1) = DSIP(NFrq+1) / CGrp(NFrq+1,ISEA)
          DM(NFrq+1) = DM(NFrq)
          DM(  -1) = DM( 0)
         
! 4.c Courant number of k-velocity without dividing by dk
!
!Li   Current-bathy gradient product term.
          FKD = CX(ISEA)*DHDX(ISEA) + CY(ISEA)*DHDY(ISEA)
!Li   Reset any NaN values in current-bathy gradient. JGLi14Nov2017
          IF ( .NOT. (FKD .EQ. FKD) )  FKD = 0.0

          DO IK=0, NFrq
!Li   For new refraction scheme using Cg.  JGLi3Jun2011
!           FKS   = - FACK*WN(IK)*SIG(IK)/SNH2K(IK)
!Li   Old refraction formulation using phase speed.  JGLi8Jun2011
!           FKS   = - FACK*WN(IK)*SIGSNH(IK)
!Li   Current induced k-shift.   JGLi30Mar2016
            FKS = MAX( 0.0, CGrp(IK,ISEA)*WNmk(IK,ISEA)-0.5*SIG(IK) )*FKD /    &
                     ( DEPTH30*CGrp(IK,ISEA) )
            DO ITH=1, NDir
              CFLK(ITH,IK) = DTG*( FKS + FKC(ITH)*WNmk(IK,ISEA) )
            END DO
          END DO
!!Li   No CFL limiter is required here as it is applied in SMCkUNO2.

        END IF
!
! 5.  Propagate ------------------------------------------------------ *
!
      IF ( MOD(MT,2) .EQ. 0 ) THEN
          IF ( FLCK ) THEN
!!Li  Refraction caused k-space shift.
              CALL SMCkUNO2(CFLK, VQ, DB, DM)
            END IF
          IF ( FLCTH ) THEN
!!Li  GCT and refraction by rotation in theta direction.
              CALL SMCGtCrfr(VCFLT, VQ)
            END IF
        ELSE
          IF ( FLCTH ) THEN
!!Li  GCT and refraction by rotation in theta direction.
              CALL SMCGtCrfr(VCFLT, VQ)
            END IF
          IF ( FLCK )  THEN
!!Li  Refraction caused k-space shift.
              CALL SMCkUNO2(CFLK, VQ, DB, DM)
            END IF
        END IF
 
!Li  Resetting NaNQ VQ to zero if any.   JGLi14Nov2017
!     NN = 0
!     DO IK=0, NFrq
!        DO ITH=1, NDir
!          IF( .NOT. (VQ(ITH,IK) .EQ. VQ(ITH,IK)) ) THEN
!            NN = NN + 1
!            VQ(ITH, IK) = 0.0
!          ENDIF
!        ENDDO
!     ENDDO
!     IF (NN .GT. 0)  WRITE(6,*) NN, " NaN in KTRN9 at ISEA =", ISEA
!
! 6.  Store reults --------------------------------------------------- *
!   
        WSpc(:,:,ISEA) = VQ 
!

!!    End of refraction cell loop ISEA.
      END DO  
!$OMP END Parallel DO

      RETURN
!
!/ End of W3KRTN ----------------------------------------------------- /
!/
      END SUBROUTINE W3KRTN
!/
!
! Subroutine that calculate mid-flux values for x dimension 
       SUBROUTINE SMCxUNO2(NUA, NUB, CF, UC, UFLX, AKDif, FU, FX, FTS)
!!Li         CALL SMCxUNO2(iuf, juf, CQ, UCFL, ULCFLX, DNND, FUMD, FUDIFX, FMR)
         USE CONSTANTS
         IMPLICIT NONE

         INTEGER, INTENT( IN):: NUA, NUB
         REAL,    INTENT( IN):: CF(-9:NC), UC(-9:NC), AKDif, FTS
         REAL,    INTENT(Out):: UFLX(NU), FU(NU), FX(NU)
!
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST8, CNST9

!    Two layer of boundary cells are added to each boundary cell face
!    with all boundary cell values CF(-9:0)=0.0.

!    Diffusion Fourier no. at sub-time-step, proportional to face size,
!    which is also equal to the sub-time-step factor FTS.
         CNST0=AKDif*FTS*FTS
!    Uniform diffusion coefficient for all sizes.  JGLi24Feb2012
!        CNST0=AKDif*MRFct*FTS

!$OMP Parallel Default(Shared), Private(i, ij, K, L, M, N),  &
!$OMP          Private(CNST,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8,CNST9) 

!$ !  IF( NT .EQ. 0 ) THEN
!$ !  WRITE(6,*) "Num_Threads in SMCxUNO2 =",  omp_get_num_threads()
!$ !  ENDIF

!$OMP DO

!    Notice an extra side length L is multiplied to mid-flux to give correct
!    proportion of flux into the cells.  This length will be removed by the
!    cell length when the tracer concentration is updated.

      DO i=NUA, NUB

!    Select Upstream, Central and Downstream cells
           K=ISD(4,i)
           L=ISD(5,i)
           M=ISD(6,i)
           N=ISD(7,i)

!    Face bounding cell lengths and central gradient
           CNST2=REAL( ICE3(L) )
           CNST3=REAL( ICE3(M) )
           CNST5=(CF(M)-CF(L))/( CNST2 + CNST3 )

!    Courant number in local size-1 cell, arithmetic average.
           CNST6=0.5*( UC(L)+UC(M) )*FTS
           UFLX(i) = CNST6

!    Multi-resolution SMC grid requires flux multiplied by face factor.
           CNST8 = REAL( ISD(3,i) )

!    Diffusion factor in local size-1 cell, plus the cosine factors.
!    2.0 factor to cancel that in gradient CNST5.  JGLi08Mar2012
!    The maximum cell number is used to avoid the boundary cell number
!    in selection of the cosine factor.
           ij= MAX(L, M)
           CNST9 = 2.0/( CLATS( ij )*CLATS( ij ) )

!    For positive velocity case
         IF(CNST6 >= 0.0)  THEN

!    Use central cell velocity for boundary flux.  JGLi06Apr2011
           IF( M .LE. 0) UFLX(i) = UC(L)*FTS

!    Upstream cell length and gradient, depending on UFLX sign.
           CNST1=REAL( ICE3(K) )
           CNST4=(CF(L)-CF(K))/( CNST2 + CNST1 )

!    Use minimum gradient all region.
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value inside central cell
           FU(i)=(CF(L) + CNST*(CNST2 - UFLX(i)))*CNST8

!    For negative velocity case
         ELSE

!    Use central cell velocity for boundary flux.  JGLi06Apr2011
           IF( L .LE. 0) UFLX(i) = UC(M)*FTS

!    Upstream cell length and gradient, depending on UFLX sign.
           CNST1=REAL( ICE3(N) )
           CNST4=(CF(N)-CF(M))/( CNST1 + CNST3 )

!    Use minimum gradient outside monotonic region. 
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value inside central cell M
           FU(i)=(CF(M) - CNST*(CNST3+UFLX(i)))*CNST8

         ENDIF

!    Diffusion flux by face gradient x DT 
         FX(i)=CNST0*CNST5*CNST8*CNST9

      END DO

!$OMP END DO

!$OMP END Parallel 

! 999  PRINT*, ' Sub SMCxUNO2 ended.'

      RETURN
      END SUBROUTINE SMCxUNO2


! Subroutine that calculate mid-flux values for x dimension 
      SUBROUTINE SMCyUNO2(NVA, NVB, CF, VC, VFLY, AKDif, FV, FY, FTS)
!!Li        CALL SMCyUNO2(ivf, jvf, CQ, VCFL, VLCFLY, DNND, FVMD, FVDIFY, FMR)
         USE CONSTANTS
         IMPLICIT NONE

         INTEGER, INTENT( IN):: NVA, NVB
         REAL,    INTENT( IN):: CF(-9:NC), VC(-9:NC), AKDif, FTS
         REAL,    INTENT(Out):: VFLY(NV), FV(NV), FY(NV)
!
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6, CNST8

!    Notice an extra side length L is multiplied to mid-flux to give correct
!    proportion of flux into the cells.  This length will be removed by the
!    cell length when the tracer concentration is updated.

!    Diffusion Fourier no. at sub-time-step, proportional to face size,
!    which is also equal to the sub-time-step factor FTS.
!        CNST0=AKDif*FTS*FTS
!    2.0 factor to cancel that in gradient CNST5.  JGLi08Mar2012
         CNST0=AKDif*FTS*FTS*2.0
!    Uniform diffusion coefficient for all sizes.  JGLi24Feb2012
!        CNST0=AKDif*MRFct*FTS

!$OMP Parallel Default(Shared), Private(j, K, L, M, N),  &
!$OMP          Private(CNST,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6,CNST8) 

!$ !  IF( NT .EQ. 0 ) THEN
!$ !  WRITE(6,*) "Num_Threads in SMCyUNO2 =",  omp_get_num_threads()
!$ !  ENDIF

!$OMP DO

      DO j=NVA, NVB

!    Select Upstream, Central and Downstream cells
           K=JSD(4,j)
           L=JSD(5,j)
           M=JSD(6,j)
           N=JSD(7,j)

!    Face bounding cell lengths and gradient
           CNST2=REAL( ICE4(L) )
           CNST3=REAL( ICE4(M) )
           CNST5=(CF(M)-CF(L))/( CNST2 + CNST3 )

!    Courant number in local size-1 cell unit 
!    Multiply by multi-resolution time step factor  FTS
           CNST6=0.5*( VC(L)+VC(M) )*FTS
           VFLY(j) = CNST6

!    Face size integer and cosine factor.  
!    CLATF is defined on V-face for SMC grid.  JGLi28Feb2012
         CNST8=CLATF(j)*REAL( JSD(3,j) )

!    For positive velocity case
         IF(CNST6 >= 0.0)  THEN

!    Boundary cell y-size is set equal to central cell y-size 
!    as y-boundary cell sizes are not proportional to refined 
!    inner cells but constant of the base cell y-size, and  
!    Use central cell speed for face speed.  JGLi06Apr2011
           IF( M .LE. 0 ) THEN
              VFLY(j) = VC(L)*FTS
              CNST3   = CNST2
           ENDIF

!    Upstream cell size and irregular grid gradient, depending on VFLY.
           CNST1=REAL( ICE4(K) )
           CNST4=(CF(L)-CF(K))/( CNST2 + CNST1 )

!    Use minimum gradient outside monotonic region
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value multiplied by face width and cosine factor
           FV(j)=( CF(L) + CNST*(CNST2 - VFLY(j)) )*CNST8

!    For negative velocity case
         ELSE

!    Set boundary cell y-size equal to central cell y-size and 
!    Use central cell speed for flux face speed.  JGLi06Apr2011
           IF( L .LE. 0 ) THEN
               VFLY(j) = VC(M)*FTS
               CNST2   = CNST3
           ENDIF

!    Upstream cell size and gradient, depending on VFLY sign.
!    Side gradients for central cell includs 0.5 factor.
           CNST1=REAL( ICE4(N) )
           CNST4=(CF(N)-CF(M))/( CNST1 + CNST3 )

!    Use minimum gradient outside monotonic region
           CNST=Sign(1.0, CNST5)*min( Abs(CNST4), Abs(CNST5) )

!    Mid-flux value multiplied by face width and cosine factor
           FV(j)=( CF(M) - CNST*(CNST3 + VFLY(j)) )*CNST8 

         ENDIF

!    Diffusion flux by face gradient x DT x face_width x cos(lat)
!    Multiply by multi-resolution time step factor FTS
         FY(j)=CNST0*CNST5*CNST8

      END DO

!$OMP END DO

!$OMP END Parallel 

! 999  PRINT*, ' Sub SMCyUNO2 ended.'

      RETURN
      END SUBROUTINE SMCyUNO2


!
! Subroutine that calculate cell centre gradient for any input variable.
! Nemerical average is applied to size-changing faces and the gradients 
! are along the lat-lon local east-north directions.    JGLi18Aug2015
!
       SUBROUTINE SMCGradn(CVQ, GrdX, GrdY, L0r1) 

         USE CONSTANTS, Only:  NSEA, NU,  NV,  NPol, DX0, DY,  &
                               ICE,  ISD, JSD, CLATS, REARTH
         IMPLICIT NONE

         REAL,    INTENT( IN)::  CVQ(NSEA)
         REAL,    INTENT(Out):: GrdX(NSEA), GrdY(NSEA)
         INTEGER, INTENT( IN):: L0r1
!
         INTEGER :: i, j, k, L, M, N
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6 
         REAL :: DX0I, DY0I

!    Use a few working arrays
         REAL,  Dimension(-9:NSEA):: CVF, AUN, AVN  

!    Pass a copy to working variable.
         CVF(-9:0)  = 0.0
         CVF(1:NSEA)=CVQ(1:NSEA) 

!!   Initialize arrays
         AUN = 0.
         AVN = 0.
        GrdX = 0.
        GrdY = 0.

!!   Multi-resolution base-cell size defined by refined levels.
!!   So the MRFct converts the base cell SX, SY into size-1 cell lenth.
!!   Constant size-1 dy=DY0 and dx on Equator DX0, inverted.
        DX0I   = 1.0/( DX0*REARTH )
        DY0I   = 1.0/(  DY*REARTH )

!$OMP Parallel Default(Shared), Private(i, j, K, L, M, N),  &
!$OMP          Private(CNST,CNST0,CNST1,CNST2,CNST3,CNST4,CNST5,CNST6)

!$OMP DO

!!   Calculate x-gradient by averaging U-face gradients. 
        DO i=1, NU

!    Select Upstream, Central and Downstream cells
           L=ISD(5,i)
           M=ISD(6,i)

!!   For zero-gradient boundary conditions, simply skip boundary faces.
        IF( L0r1 .EQ. 0 .OR. (L > 0 .AND. M > 0) ) THEN

!    Multi-resolution SMC grid requires flux multiplied by face factor.
           CNST1=REAL( ISD(3,i) ) 

!    Face bounding cell lengths and central gradient
           CNST2=REAL( ICE(3,L) ) 
           CNST3=REAL( ICE(3,M) ) 

           CNST5=CNST1*(CVF(M)-CVF(L))/(CNST2+CNST3)

!    Store side gradient in two neighbouring cells
!    Store side gradient in two neighbouring cells
!! Remove boundary cell flux update or L M > 0.  JGLi28Mar2019
           IF( L > 0 ) THEN
!$OMP ATOMIC 
           AUN(L) = AUN(L) + CNST5 
           ENDIF
           IF( M > 0 ) THEN
!$OMP ATOMIC 
           AUN(M) = AUN(M) + CNST5 
           ENDIF

        ENDIF
        END DO

!$OMP END DO

!  Assign averaged side-gradient to GrdX, plus latitude factor
!  Note averaging over 2 times of cell y-width factor but AUN
!  has already been divied by two cell lengths. 

!$OMP DO

        DO n=1, NSEA

!  Cell y-size IJKCel(4,i) is used to cancel the face size-factor in AUN. 
!  Plus the actual physical length scale for size-1 cell. 
!  Note polar cell (if any) AUN = 0.0 as it has no U-face.
           GrdX(n)=DX0I*AUN(n)/( CLats(n)*ICE(4,n) )

        ENDDO

!$OMP END DO

!$OMP DO

!!   Calculate y-gradient by averaging V-face gradients. 
        DO j=1, NV

!    Select Central and Downstream cells
           L=JSD(5,j)
           M=JSD(6,j)

!!   For zero-gradient boundary conditions, simply skip boundary faces.
        IF( L0r1 .EQ. 0 .OR. (L > 0 .AND. M > 0) ) THEN

!    Face size is required for multi-resolution grid.
           CNST1=Real( JSD(3,j) )

!    Cell y-length of UCD cells
           CNST2=Real( ICE(4,L) )
           CNST3=Real( ICE(4,M) )

!    Side gradients over 2 cell lengths for central cell.
!    Face size factor is also included for average.
!    Side gradients over 2 cell lengths for central cell.
!    Face size factor is also included for average.
           CNST6=CNST1*(CVF(M)-CVF(L))/(CNST2+CNST3)

!! Remove boundary cell flux update or L M > 0.  JGLi28Mar2019
           IF( L > 0 ) THEN
!    Store side gradient in two neighbouring cells
!$OMP ATOMIC 
           AVN(L) = AVN(L) + CNST6 
           ENDIF
           IF( M > 0 ) THEN
!$OMP ATOMIC 
           AVN(M) = AVN(M) + CNST6 
           ENDIF

        ENDIF
        END DO

!$OMP END DO

!$OMP DO

!  Assign averaged side-gradient to GrdY.
        DO n=1, NSEA 

!  AV is divided by the cell x-size IJKCel(3,i) to cancel face
!  size-factor, and physical y-distance of size-1 cell.
           GrdY(n)=DY0I*AVN(n)/Real( ICE(3,n) )

        END DO

!$OMP END DO

!$OMP END Parallel 

!!Li  Polar cell (if any) y-gradient is set to zero.
        IF( NPol .GT. 0 )  GrdY(NSEA-NPol+1:NSEA) = 0.0

! 999  PRINT*, ' Sub SMCGradn ended.'

        RETURN
        END SUBROUTINE SMCGradn

!
! Subroutine that average sea point values with a 1-2-1 scheme. 
!
       SUBROUTINE SMCAverg(CVQ) 

         USE CONSTANTS
         IMPLICIT NONE

         REAL,    INTENT(INOUT)::  CVQ(-9:NC)

         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!    Use a few working arrays
         REAL,  Dimension(-9:NC):: CVF, AUN, AVN  

!    Pass a copy to working variable. 
         CVF=CVQ 

!!   Initialize arrays
         AUN = 0.
         AVN = 0.

!!Li  Save polar cell value if any.
         CNST0 = CVQ(NSEA)

!$OMP Parallel Default(Shared), Private(i, j, L, M, n),  &
!$OMP          Private(CNST3,CNST4,CNST5,CNST6)

!!   Calculate x-gradient by averaging U-face gradients. 
!$OMP DO
        DO i=1, NU

!    Select Upstream, Central and Downstream cells
           L=ISD(5,i)
           M=ISD(6,i)

!    Multi-resolution SMC grid requires flux multiplied by face factor.
           CNST5=Real( ISD(3,i) )*(CVF(M)+CVF(L))

!    Store side gradient in two neighbouring cells
           IF( L > 0 ) THEN
!$OMP ATOMIC
              AUN(L) = AUN(L) + CNST5 
           ENDIF
           IF( M > 0 ) THEN
!$OMP ATOMIC
              AUN(M) = AUN(M) + CNST5 
           ENDIF

        END DO
!$OMP END DO

!!   Calculate y-gradient by averaging V-face gradients. 
!$OMP DO
        DO j=1, NV

!    Select Central and Downstream cells
           L=JSD(5,j)
           M=JSD(6,j)

!    Face size is required for multi-resolution grid.
           CNST6=Real( JSD(3,j) )*(CVF(M)+CVF(L))

!    Store side gradient in two neighbouring cells
!! Remove boundary cell flux update or L M > 0.  JGLi28Mar2019
           IF( L > 0 ) THEN
!$OMP ATOMIC 
              AVN(L) = AVN(L) + CNST6 
           ENDIF
           IF( M > 0 ) THEN
!$OMP ATOMIC 
              AVN(M) = AVN(M) + CNST6 
           ENDIF

       END DO
!$OMP END DO

!  Assign averaged value back to CVQ.
!      DO n=1, NSEA 
!!Li  Keep polar cell values unchanged.  
!$OMP DO
       DO n=1, NC - NPol

            CNST3=0.125/Real( ICE3(n) )
            CNST4=0.125/Real( ICE4(n) )
!  AUN is divided by the cell y-size IJKCel(4,n) and AVN by 
!  the cell x-size IJKCel(3,n) to cancel face size factors. 
            CVQ(n)= AUN(n)*CNST4 + AVN(n)*CNST3 

       END DO
!$OMP END DO

!$OMP END Parallel 

!!Li  Polar cell (if any) keep original value. 
       IF( NPol > 0 ) CVQ(NSEA) = CNST0

! 999  PRINT*, ' Sub SMCAverg ended.'

      RETURN
      END SUBROUTINE SMCAverg


!Li
! Subroutine that calculate great circle turning (GCT) and refraction.
! The refraction and GCT terms are equivalent to a simgle rotation by each 
! element and does not need to be calculated as advection.  A simple rotation
! scheme similar to the 1st order upstream scheme but without any restriction 
! on the rotation angle or the CFL limit by an Eulerian advection scheme. 
!                 Jian-Guo Li  12 Nov 2010
!Li

       SUBROUTINE SMCGtCrfr(CoRfr, SpeTHK)
         USE CONSTANTS
         IMPLICIT NONE

         REAL, INTENT(IN)   ::  CoRfr(NDIR, NFrq)
         REAL, INTENT(INOUT):: SpeTHK(NDIR, NFrq)
         INTEGER ::  NRefr
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!    Loop through NFrq spectral bins.
       DO n=1, NFrq

!!   Asign cell spectrum to temporary variable Spcetr
         Spectr=SpeTHK(1:NDIR,n)
         SpeGCT=0.0 

!!   Loop through NDIR directional bins for each cell spectrum
         DO j=1, NDIR

!    GCT + refraction Courant number for this dirctional bin
           CNST6=CoRfr(j,n)

!    Work out integer number of bins to be skipped.
!    If K is great than NDIR, full circle turning is removed.
           CNST5=ABS( CNST6 )
           K= MOD( INT(CNST5), NDIR ) 

!    Partitioning faraction of the spectral component
           CNST1=CNST5 - REAL( INT(CNST5) )
           CNST2=1.0 - CNST1

!    For positive turning case
         IF(CNST6 > 0.0)  THEN
 
!    Select the upstream and downstream bins to rotate in, wrap at end
           L=j+K
           M=j+K+1
           IF( L .GT. NDIR ) L = L - NDIR
           IF( M .GT. NDIR ) M = M - NDIR

!!   Divid the j bin energy by fraction of CNST6 and store in SpeGCT
           SpeGCT(L)=SpeGCT(L)+Spectr(j)*CNST2
           SpeGCT(M)=SpeGCT(M)+Spectr(j)*CNST1

!    For negative or no turning case
         ELSE 

!    Select the upstream and downstream bins to rotate in, wrap at end
           L=j-K
           M=j-K-1
           IF( L .LT. 1 ) L = L + NDIR
           IF( M .LT. 1 ) M = M + NDIR

!!   Divid the bin energy by fraction of CNST6 and store in SpeGCT
           SpeGCT(L)=SpeGCT(L)+Spectr(j)*CNST2
           SpeGCT(M)=SpeGCT(M)+Spectr(j)*CNST1

         ENDIF

!!   End of directional loop j
         END DO

!!   Store GCT spectrum
         SpeTHK(1:NDIR,n) = SpeGCT

!!   End of frequency loop n
       END DO

! 999  PRINT*, ' Sub SMCGtCrfr ended.'

      RETURN
      END SUBROUTINE SMCGtCrfr


!Li
! Subroutine that calculates refraction induced shift in k-space. 
! The term is equivalent to advection on an irregular k-space grid.
! The UNO2 scheme on irregular grid is used for this term. 
!                 Jian-Guo Li  15 Nov 2010
!Li

       SUBROUTINE SMCkUNO2(CoRfr, SpeTHK, DKC, DKS)
         USE CONSTANTS

         IMPLICIT NONE
         REAL, INTENT(IN)   ::  CoRfr(NDIR, 0:NFrq), DKC(0:NFrq+1), DKS(-1:NFrq+1)
         REAL, INTENT(INOUT):: SpeTHK(NDIR, NFrq)
         REAL, Dimension(-1:NFrq+2):: SpeRfr, Spectf, SpeFlx
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!Li  Cell and side indices for k-dimension are arranged as 
!    Cell:    | -1 | 0 | 1 | 2 | ... | NK | NK+1 | NK+2 |
!    Side:        -1   0   1   2 ...     NK     NK+1
!    The wave action in k-space is extended at the high-wavenumber (frequency) end 
!    by the (m+2)th negative power of frequency for boundary conditions.  Outside 
!    low-wavenumber (frequncy) end, wave action is assumed to be zero.
      CNST=XFR**(-7)

      DO n=1, NDIR

!!   Asign cell spectrum to temporary variable Spcetr
         Spectf(-1)  =0.0
         Spectf( 0)  =0.0
         Spectf(1:NFrq)=SpeTHK(n,1:NFrq)
         Spectf(NFrq+1)=Spectf(NFrq  )*CNST
         Spectf(NFrq+2)=Spectf(NFrq+1)*CNST

!!   Calculate k-space gradient for NFrq+2 faces by UNO2 scheme 
            SpeRfr(-1)= 0.0
         DO j=-1, NFrq+1
            SpeRfr(j)=(Spectf(j+1)-Spectf(j))/DKS(j)
         ENDDO

!!   Calculate k-space fluxes for NFrq+1 faces by UNO2 scheme 
         DO j=0, NFrq

!!   Final refraction Courant number for this k-space face 
!!   Note CoRfr is CFL for k but without dividing dk.
         CNST6=CoRfr(n,j)
!!   Resetting NaNQ CFL to zero if any.   JGLi14Nov2017
         IF( .NOT. (CNST6 .EQ. CNST6) ) CNST6 = 0.0 

!    For positive case
         IF(CNST6 > 0.0)  THEN
            CNST0 = MIN( CTMAX*DKC(j), CNST6 )
         SpeFlx(j) = CNST0*(Spectf(j) + SIGN(0.5, SpeRfr(j))*(DKC(j)-CNST0)  &
                      *MIN( ABS(SpeRfr(j-1)), ABS(SpeRfr(j)) ))
 
!    For negative or no turning case
         ELSE 

            CNST0 = MIN( CTMAX*DKC(j+1), -CNST6 )
         SpeFlx(j) = -CNST0*(Spectf(j+1) - SIGN(0.5, SpeRfr(j))*(DKC(j+1)-CNST0) &
                      *MIN( ABS(SpeRfr(j+1)), ABS(SpeRfr(j)) ) )

         ENDIF

!!   End of flux loop j
         END DO

!!   Update spectrum for the given direction
         DO j=1, NFrq
!    Final refraction Courant number for this k-space face 
!           SpeTHK(n, j) = Spectf(j) + (SpeFlx(j-1) - SpeFlx(j))/DKC(j)
!    Add positive filter in case negative values.  JGLi27Jun2017
            SpeTHK(n, j) = MAX( 0.0, Spectf(j)+(SpeFlx(j-1)-SpeFlx(j))/DKC(j) )
         END DO

!!   End of directional loop n
      END DO

! 999  PRINT*, ' Sub SMCkUNO2 ended.'

      RETURN
      END SUBROUTINE SMCkUNO2


! Subroutine that calculates water-depth gradient for refraction.
! For consistency with the lat-lon grid, full grid DDDX, DDDY are
! also assigned here.  DHDX, DHDY are used for refraction at present.
! It has to be rotated to map-east system in the Arctic part.
       SUBROUTINE SMCDHXY
         USE CONSTANTS
         IMPLICIT NONE
         REAL :: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
         REAL, Dimension(NC) :: GrHx, GrHy
         REAL, Dimension(-9:NC) :: Dpth

!!   Assign water depth to Dpth from HCel values.
       Dpth = HCel(-9:NC)

!!   Calculate sea point water depth gradient
       CALL SMCGradn(Dpth, GrHx, GrHy, 1)

!!   Pass gradient values to DHDX, DHDY
       DHDX(1:NC) = GrHx
       DHDY(1:NC) = GrHy

!!   Apply limiter to depth-gradient and rotate Arctic part.
       DO n=1,NC

!  A limiter of gradient <= 0.1 is applied.
           IF( ABS( DHDX(n) ) .GT.  0.1) DHDX(n)=SIGN( 0.1, DHDX(n) )
           IF( ABS( DHDY(n) ) .GT.  0.1) DHDY(n)=SIGN( 0.1, DHDY(n) )

!Li  Depth gradient in the Arctic part has to be rotated into 
!Li  the map-east system for calculation of refraction. 
       IF( Arctic .AND. n .GT. NGLO ) THEN
          CNST0 = AngArc(n-NGLo)*D2RAD
          CNST1 = DHDX(n)*COS(CNST0) - DHDY(n)*SIN(CNST0)
          CNST2 = DHDX(n)*SIN(CNST0) + DHDY(n)*COS(CNST0)
          DHDX(n) = CNST1
          DHDY(n) = CNST2
       ENDIF

       END DO

!! Calculate the depth gradient limiter for refraction.  
       L = 0
       DO n=1,NC
!Li   Work out magnitude of depth gradient
             CNST4 = 1.0001*SQRT(DHDX(n)*DHDX(n) + DHDY(n)*DHDY(n))
!
!Li   Directional depedent depth gradient limiter.  JGLi16Jun2011
          IF ( CNST4 .GT. 1.0E-5 ) THEN
             L = L + 1
             DO i=1, NDir
!Li   Refraction is done only when depth gradient is non-zero.
!Li   Note ACOS returns value between [0, Pi), always positive.
               CNST6 = ACOS(-(DHDX(n)*ECOS(i)+DHDY(n)*ESIN(i))/CNST4 )
!Li   User-defined refraction limiter added.   JGLi09Jan2012 
               DHLMT(i,n)=MIN(Refran, 0.75*MIN(CNST6,ABS(Pie-CNST6)))/DTH
             END DO

          ELSE
               DHLMT(:,n) = 0.0
          ENDIF

       ENDDO

! 999  PRINT*, ' Sub SMCDHXY ended.'

       RETURN
       END SUBROUTINE SMCDHXY 


! Subroutine that calculates current velocity gradient for refraction.
! For consistency with the lat-lon grid, full grid DCXDXY, DCYDXY are
! assigned here.  They are rotated to map-east system in the Arctic part.
!                 JGLi23Mar2016
!
       SUBROUTINE SMCDCXY
         USE CONSTANTS
         IMPLICIT NONE

         REAL :: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
         REAL, Dimension(NC) :: GrHx, GrHy
         REAL, Dimension(-9:NC) :: CXCY

!!   Assign current CX speed to CXCY and set negative cells.
       CXCY(-9:0) = 0.0
       CXCY(1:NC)= CX(1:NC) 

!!   Initialize gradient arrays
       GrHx = 0.0
       GrHy = 0.0

!!   Calculate sea point water depth gradient
       CALL SMCGradn(CXCY, GrHx, GrHy, 1)

!!   Apply limiter to CX-gradient and copy to full grid.
       DO n=1,NC

!  A limiter of gradient <= 0.1 is applied.
          IF( ABS( GrHx(n) ) .GT.  0.1) GrHx(n)=SIGN( 0.1, GrHx(n) )
          IF( ABS( GrHy(n) ) .GT.  0.1) GrHy(n)=SIGN( 0.1, GrHy(n) )

!Li  Current gradient in the Arctic part has to be rotated into 
!Li  the map-east system for calculation of refraction. 
          IF( Arctic .AND. n .GT. NGLO ) THEN
             CNST0 = AngArc(n-NGLo)*D2RAD 
             CNST1 = GrHx(n)*COS(CNST0) - GrHy(n)*SIN(CNST0)
             CNST2 = GrHx(n)*SIN(CNST0) + GrHy(n)*COS(CNST0)
             GrHx(n) = CNST1
             GrHy(n) = CNST2
          ENDIF

       END DO

!!   Store CX gradient in DCXDX, DCXDY
       DCXDX(1:NC) = GrHx
       DCXDY(1:NC) = GrHy

!!   Assign current CY speed to CXCY and set negative cells.
       CXCY(-9:0) = 0.0
       CXCY(1:NC)= CY(1:NC) 

!!   ReInitialize gradient arrays
       GrHx = 0.0
       GrHy = 0.0

!!   Calculate sea point water depth gradient
       CALL SMCGradn(CXCY, GrHx, GrHy, 1)

!!   Apply limiter to CX-gradient and copy to full grid.
       DO n=1,NC

!  A limiter of gradient <= 0.1 is applied.
          IF( ABS( GrHx(n) ) .GT.  0.1) GrHx(n)=SIGN( 0.1, GrHx(n) )
          IF( ABS( GrHy(n) ) .GT.  0.1) GrHy(n)=SIGN( 0.1, GrHy(n) )

!Li  Current gradient in the Arctic part has to be rotated into 
!Li  the map-east system for calculation of refraction. 
          IF( Arctic .AND. n .GT. NGLO ) THEN
             CNST0 = AngArc(n-NGLo)*D2RAD 
             CNST1 = GrHx(n)*COS(CNST0) - GrHy(n)*SIN(CNST0)
             CNST2 = GrHx(n)*SIN(CNST0) + GrHy(n)*COS(CNST0)
             GrHx(n) = CNST1
             GrHy(n) = CNST2
          ENDIF

       END DO

!!   Store CY gradient in DCYDX, DCYDY
       DCYDX(1:NC) = GrHx
       DCYDY(1:NC) = GrHy

! 999  PRINT*, ' Sub SMCDCXY ended.'

       RETURN
       END SUBROUTINE SMCDCXY 

!/
!/ End of module W3PSMCMD -------------------------------------------- /
!/
      END MODULE W3PSMCMD

