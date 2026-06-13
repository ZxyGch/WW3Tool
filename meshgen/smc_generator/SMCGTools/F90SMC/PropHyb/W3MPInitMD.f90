!/ ------------------------------------------------------------------- /
      MODULE W3MPInitMD
!/
!/    Adapted from WW3 model w3initmd.ftn for SMC grid propagation test. 
!/                           JGLi02Jul2019
!/    Modified to rectify MPI_SEND/RECV_INIT bugs.  JGLi23Oct2019
!/
!  2. Subroutines and functions :
!
!      Name      Type  Scope    Description
!     ----------------------------------------------------------------
!      W3INIT    Subr. Public   Wave model initialization.
!      W3MPII    Subr. Public   Initialize MPI data transpose.
!      W3MPIO    Subr. Public   Initialize MPI output gathering.
!      W3MPIP    Subr. Public   Initialize MPI point output gathering.
!     ----------------------------------------------------------------
!
!  3. Remarks :
!
!/ ------------------------------------------------------------------- /
      PUBLIC
!/
      REAL, PARAMETER                :: CRITOS = 15.
      CHARACTER(LEN=10), PARAMETER   :: WWVER  = '6.06  '
!/
      CONTAINS
!/ ------------------------------------------------------------------- /
      SUBROUTINE W3INIT 
!/
!/                  +-----------------------------------+
!/                  | WAVEWATCH III           NOAA/NCEP |
!/                  |           H. L. Tolman            |
!/                  |                        FORTRAN 90 |
!/                  | Last update :         03-Sep-2012 |
!/                  +-----------------------------------+
!/
!!Li  Modified for SMC grid propagation test.  JGLi26Jul2019 
!
!  8. Structure :
!
!     ----------------------------------------------------
!      1.  Set-up of idata structures and I/O.
!        a Point to proper data structures.
!        b Number of processors and processor number.
!        c Open files.
!        d Dataset unit numbers
!        e Subroutine tracing
!        f Initial and test outputs
!      2.  Model definition.
!        a Read model definition file         ( W3IOGR )
!        b Save MAPSTA.
!        c MPP preparation
!      3.  Model initialization.
!        a Read restart file.                 ( W3IORS )
!        b Compare grid and restart MAPSTA.
!        c Initialize with winds if requested (set flag).
!        d Initialize calm conditions if requested.
!        e Preparations for prop. scheme.
!      4.  Set-up output times.
!        a Unpack ODAT.
!        b Check if output available.
!        c Get first time per output and overall.
!        d Prepare point output               ( W3IOPP )
!      5.  Define wavenumber grid.
!        a Calculate depth.
!        b Fill wavenumber and group velocity arrays.
!      6.  Initialize arrays.
!      7.  Write info to log file.
!      8.  Final MPI set up  ( W3MPII , W3MPIO , W3MPIP )
!     ----------------------------------------------------
!
! 10. Source code :
!
!/ ------------------------------------------------------------------- /
      USE CONSTANTS
!/
      IMPLICIT NONE
!
!     INCLUDE "mpif.h"
!/
!/ ------------------------------------------------------------------- /
!
! 1.b Number of processors and processor number.
!     Overwrite some initializations from W3ODATMD.
!
!     *******************************************************
!     *** NOTE : OUTPUT PROCESSOR ASSIGNMENT NEEDS TO BE  ***
!     ***        CONSISTENT WITH ASSIGNMENT IN WMINIT.    ***
!     *******************************************************
!
!     MPI_COMM_WAVE = MPI_COMM_WORLD
!     CALL MPI_COMM_SIZE ( MPI_COMM_WAVE, NAPROC, IERR_MPI )
!     CALL MPI_COMM_RANK ( MPI_COMM_WAVE, IAPROC, IERR_MPI )
!     IAPROC = IAPROC + 1
!
! 2.c MPP preparation
! 2.c.1 Set simple counters and variables
!
      NSEAL  = 1 + (NSEA-IAPROC)/NAPROC
      NSEALM = 1 + (NSEA-1)/NAPROC
!
! 2.c.2 Allocate VA array and initialise to be zero
!
      NSPEC = NSpc
      IF ( IAPROC .LE. NAPROC ) THEN
         ALLOCATE ( VA(NSPEC,0:NSEALM), STAT=ISTAT ) 
         VA(:,:) = 0.
      ENDIF
!
! 2.c.3 Calculated expected number of prop. calls per processor
!!  Assign spectral components to MPI ranks for balanced load.
      CALL Spctinit
!
! 8.  Final MPI set up ----------------------------------------------- /
!
      CALL W3MPII

!!Li  SWH output is now done by MPI_GATHER on last rank (not WW3 method). 
!!    This function requires the root PE to be defined or use default 0.
!!    Local and gather variables are declared here.  JGLi22Aug2019 
      NAPFLD = NAPROC
      ALLOCATE ( HS(NSEALM) )
      IF ( IAPROC .EQ. NAPFLD ) ALLOCATE ( XHS(NSEALM*NAPROC) )
!
      CALL W3MPIO
!
! 999  WRITE(6, *) " Sub W3INIT ended on rank ", IAPROC 

      RETURN
!
!/ End of W3INIT ----------------------------------------------------- /
!/
      END SUBROUTINE W3INIT
!/
!/ ------------------------------------------------------------------- /
!/
      SUBROUTINE W3MPII 
!/
!/                  +-----------------------------------+
!/                  | WAVEWATCH III           NOAA/NCEP |
!/                  |           H. L. Tolman            |
!/                  |                        FORTRAN 90 |
!/                  | Last update :         11-May-2007 |
!/                  +-----------------------------------+
!/
!!Li  Modified for SMC grid propagation test.  JGLi26Jul2019 
!!Li  Updated to rectify MPI_SEND/RECV_INIT.   JGLi23Oct2019 
!/
!  1. Purpose :
!
!     Perform initializations for MPI version of model.
!     Data transpose only.
!
!  2. Method :
!
!     Some derived data types are defined.  All communiction in
!     W3GATH, W3SCAT and W3WAVE are initialized so that all
!     communication can be performed with single MPI_STARTALL,
!     MPI_TESTALL and MPI_WAITALL calls.
!
!  3. Parameters :
!
!  4. Subroutines used :
!
!      Name      Type  Module   Description
!     ----------------------------------------------------------------
!
!      MPI_TYPE_VECTOR, MPI_TYPE_COMMIT
!                Subr. mpif.h   MPI derived data type routines.
!
!      MPI_SEND_INIT, MPI_RECV_INIT
!                Subr. mpif.h   MPI persistent communication calls.
!     ----------------------------------------------------------------
!
!  5. Called by :
!
!      Name      Type  Module   Description
!     ----------------------------------------------------------------
!      W3INIT    Subr. W3INITMD Wave model initialization routine.
!     ----------------------------------------------------------------
!
!  6. Remarks :
!
!     - Basic MPP set up partially performed in W3INIT.
!     - Each processor has to be able to send out individual error
!       messages in this routine !
!     - In version 3.09 STORE was split into a send and receive 
!       buffer, to avoid/reduce possible conflicts between the FORTRAN
!       and MPI standards when a gather is posted in a given buffer
!       right after a send is completed.
!
!/ ------------------------------------------------------------------- /
!
      USE CONSTANTS
      IMPLICIT NONE
!
!     INCLUDE "mpif.h"
!/
!/ ------------------------------------------------------------------- /
!/ Local parameters
!/
      INTEGER  :: NXXXX
      INTEGER  :: ISP, IH, IP, ITARG, IERR1, IERR2
!/
!/ ------------------------------------------------------------------- /
!/
!
! 1.  Set up derived data types -------------------------------------- /
!
      NXXXX  = NSEALM * NAPROC
!
      CALL MPI_TYPE_VECTOR ( NSEALM, 1, NAPROC, MPI_REAL,        &
                             WW3_FIELD_VEC, IERR_MPI )
      CALL MPI_TYPE_VECTOR ( NSEALM, 1, NSPEC, MPI_REAL,         &
                             WW3_SPEC_VEC,  IERR_MPI )
      CALL MPI_TYPE_COMMIT ( WW3_FIELD_VEC, IERR_MPI )
      CALL MPI_TYPE_COMMIT ( WW3_SPEC_VEC,  IERR_MPI )
!
      IF( IAPROC .GT. NAPROC ) THEN
          NSPLOC = 0
          NRQSG1 = 0
          NRQSG2 = 0
          RETURN
      ENDIF
!
! 2.  Set up scatters and gathers for W3WAVE ------------------------- /
!     ( persistent communication calls )
!
      NSPLOC = 0
      DO ISP=1, NSPEC
        IF ( IAPPRO(ISP) .EQ. IAPROC ) NSPLOC = NSPLOC + 1
      ENDDO
!
      NRQSG1 = NSPEC - NSPLOC
      ALLOCATE ( IRQSG1(MAX(1,NRQSG1),2) )
!
      IH = 0
      DO ISP=1, NSPEC
         IF ( IAPPRO(ISP) .NE. IAPROC ) THEN
            ITARG  = IAPPRO(ISP) - 1
            IH     = IH + 1
            CALL MPI_SEND_INIT ( VA(ISP,1), 1, WW3_SPEC_VEC,     &
                 ITARG, ISP, MPI_COMM_WAVE, IRQSG1(IH,1), IERR1 )
            CALL MPI_RECV_INIT ( VA(ISP,1), 1, WW3_SPEC_VEC,     &
                 ITARG, ISP, MPI_COMM_WAVE, IRQSG1(IH,2), IERR2 )
         ENDIF
      END DO
!
! 3.  Set up scatters and gathers for W3SCAT and W3GATH -------------- /
!     Also set up buffering of data.
!
      NRQSG2 = MAX( 1 , NAPROC-1 )
      ALLOCATE ( IRQSG2(NRQSG2*NSPLOC,2),           &
                 GSTORE(NAPROC*NSEALM,MPIBUF),      &
                 SSTORE(NAPROC*NSEALM,MPIBUF) )
      NRQSG2 = NAPROC - 1
!
      IH     = 0
      IBFLOC = 0
      GSTORE = 0.
      SSTORE = 0.
!
! 3.a Loop over local spectral components
!
      DO ISP=1, NSPEC
         IF ( IAPPRO(ISP) .EQ. IAPROC ) THEN
!
            IBFLOC = IBFLOC + 1
            IF ( IBFLOC .GT. MPIBUF ) IBFLOC = 1
!
! 3.b Loop over non-local processes
!
            DO IP=1, NAPROC
               IF ( IP .NE. IAPROC ) THEN
!
                  ITARG  = IP - 1
                  IH     = IH + 1
!
                  CALL MPI_RECV_INIT( GSTORE(IP,IBFLOC), 1,      &
                       WW3_FIELD_VEC, ITARG, ISP, MPI_COMM_WAVE, &
                       IRQSG2(IH,1), IERR2 )
                  CALL MPI_SEND_INIT( SSTORE(IP,IBFLOC), 1,      &
                       WW3_FIELD_VEC, ITARG, ISP, MPI_COMM_WAVE, &
                       IRQSG2(IH,2), IERR2 )
!
               ENDIF
            ENDDO
!
         ENDIF
      ENDDO
!
! 4.  Initialize buffer management ----------------------------------- /
!
      BSTAT  = 0
      BISPL  = 0
      ISPLOC = 0
      IBFLOC = 0
!
!     WRITE(6, *) "Rank and NRQSG1/2 = ", IAPROC, NRQSG1, NRQSG2
!     WRITE(6, *) " Sub W3MPII ended on rank ", IAPROC 
!
      RETURN
!
!/ End of W3MPII ----------------------------------------------------- /
!/
      END SUBROUTINE W3MPII
!/ ------------------------------------------------------------------- /
!/
      SUBROUTINE W3MPIO 
!/
!/                  +-----------------------------------+
!/                  | WAVEWATCH III           NOAA/NCEP |
!/                  |           H. L. Tolman            |
!/                  |                        FORTRAN 90 |
!/                  | Last update :         11-Nov-2015 |
!/                  +-----------------------------------+
!/
!!Li  Modified for SMC grid propagation test.  JGLi26Jul2019 
!
!  1. Purpose :
!
!     Prepare MPI persistent communication needed for WAVEWATCH I/O
!     routines.
!
!  2. Method :
!
!     Create handles as needed.
!
!  4. Subroutines used :
!
!      Name      Type  Module   Description
!     ----------------------------------------------------------------
!      W3XDMA    Subr. W3ADATMD Dimension expanded output arrays.
!      W3SETA    Subr.    "     Set pointers for output arrays
!      STRACE    Subr. W3SERVMD Subroutine tracing.
!
!      MPI_SEND_INIT, MPI_RECV_INIT
!                Subr. mpif.h   MPI persistent communication calls.
!     ----------------------------------------------------------------
!
!  5. Called by :
!
!      Name      Type  Module   Description
!     ----------------------------------------------------------------
!      W3INIT    Subr. W3INITMD Wave model initialization routine.
!     ----------------------------------------------------------------
!
!  6. Remarks :
!
!     - The communication as set up in W3MPII uses tags with number
!       ranging from 1 through NSPEC. New and unique tags for IO
!       related communication are assigned here dynamically.
!
!/ ------------------------------------------------------------------- /
!
      USE CONSTANTS 
!
      IMPLICIT NONE
!
!/
!/ ------------------------------------------------------------------- /
!/ Local parameters
!/
      INTEGER  :: IROOT, IT, IT0, IP, IFROM, ITARG 
!/
!/ ------------------------------------------------------------------- /
!/
! 1   Set field output rank to be last one
      NAPFLD = NAPROC
      IROOT  = NAPROC - 1

      NRQGO2 = NAPROC - 1
      IT0    = NSPEC
!
!!Li  Use SWH only for propagation test or NRQMAX = 1.  JGLi30Jul2019 
!
      ALLOCATE ( IRQGO2(NRQGO2) )
!
! 1.a Sends of fields to last rank NAPROC-1
!
      IF ( IAPROC .NE. NAPROC ) THEN
              IT = IT0 + IAPROC
          CALL MPI_SEND_INIT (HS(1), NSEALM, MPI_REAL, IROOT,    &
                              IT, MPI_COMM_WAVE, IRQGO, IERR)
!         WRITE(6, *) " Done HS send/recv for rank ", IAPROC
      END IF
!
! 1.b Collect at rank NAPFLD (last rank).
!
      IF ( IAPROC .EQ. NAPFLD ) THEN
              DO IP=1, NAPROC-1

                IFROM  = IP - 1
                IT     = IP + IT0
           CALL MPI_RECV_INIT (XHS(IP), 1, WW3_FIELD_VEC, IFROM, IT,  &
                               MPI_COMM_WAVE, IRQGO2(IP), IERR )
                END DO
!
      END IF
!
!     WRITE(6, *) " Sub W3MPIO ended on rank ", IAPROC 

      RETURN
!
!/ End of W3MPIO ----------------------------------------------------- /
!/
      END SUBROUTINE W3MPIO
!/
!
! Subroutine that assigns spectral components to MPI ranks for spatial propagation.
!    Adapted from WW3 model subroutine w3init in module w3initmd.ftn.
!    Wave speed is used to balance the computing load.    JGLi26Jun2019 
       SUBROUTINE Spctinit
         USE Constants
         IMPLICIT NONE

         INTEGER :: i, j, k, ISP, ISTEP, MnRank, NTTMIN
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
         INTEGER:: NTTOT, NTLOC(NFrq), NTTARG, NTTMAX, NTTSpc(NSpc)
!
! 2.c.3 Calculated expected number of prop. calls per processor
!
         NTTOT = 0
         DO K=1, NFrq
            NTLOC(K) = 1 + INT(DTG/(DTCFL*SIG(K)/SIG(1))-0.001)
            NTTOT = NTTOT + NTLOC(K)*NDir
         END DO
         NTTARG = 1 + (NTTOT-1)/nprocs
         NTTARG = NTTARG + NTLOC(NFrq)
!        NTTMAX = NTTARG + 5
         NTTMAX = NTTARG + NTLOC(NFrq)
!
! 2.c.4 Initialize IAPPRO and NTTSpc
!
         IAPPRO = 1
         NTTSpc = NTTOT
!
! 2.c.5 First sweep filling IAPPRO
!
        DO i = 1, nprocs
           ISTEP  = i
           ISP    = 0
           NTTSpc(i) = 0
           DO j=1, 1+NSpc/nprocs
             ISP    = ISP + ISTEP
             IF ( MOD(j,2) .EQ. 1 ) THEN
                ISTEP  = 2*(nprocs-i) + 1
             ELSE
                ISTEP  = 2*i - 1
             END IF
             IF ( ISP .LE. NSpc ) THEN
                K = 1 + (ISP-1)/NDir
                IF ( NTTSpc(i)+NTLOC(K) .LE. NTTARG ) THEN
                    IAPPRO(ISP) = i
                    NTTSpc(i)   = NTTSpc(i) + NTLOC(K)
                ELSE
                    IAPPRO(ISP) = -1
                END IF
             END IF
           END DO 
        END DO
!
! 2.c.6 Second sweep filling IAPPRO
!
        DO i=1, nprocs
           IF( NTTSpc(i) .LT. NTTARG ) THEN
              DO ISP=1, NSpc
                 IF( IAPPRO(ISP) .EQ. -1 ) THEN
                    K = 1 + (ISP-1)/NDir
                    IF ( NTTSpc(i)+NTLOC(K) .LE. NTTARG ) THEN
                        IAPPRO(ISP) = i
                        NTTSpc(i)   = NTTSpc(i) + NTLOC(K)
                    END IF
                 END IF
              END DO
           END IF
        END DO
!
! Final check all spectral components are assigned properly. 
! If not, assign it to the least loaded rank.  JGLi15Oct2019
!
        DO ISP=1, NSpc
           IF( IAPPRO(ISP) .EQ. -1 ) THEN
               K = 1 + (ISP-1)/NDir
               NTTMIN=NTTMAX               
               DO i=nprocs, 1, -1
                  IF ( NTTSpc(i) .LT. NTTMIN ) THEN
                     NTTMIN = NTTSpc(i)
                     MnRank = i
                  END IF
               END DO
               IAPPRO(ISP) = MnRank 
               NTTSpc(MnRank)   = NTTSpc(MnRank) + NTLOC(K)
           END IF    
        END DO

! Final check all spectral components are assigned properly. 
        IF( myrank .eq. nprocs - 1 ) THEN
           DO ISP=1, NSpc
              IF( IAPPRO(ISP) < 0 ) WRITE(6,*)  &
        " *** Warning, component ", ISP, " wrong rank", IAPPRO(ISP)
           ENDDO
        ENDIF


! 999  PRINT*, ' Sub Spctinit ended on ', IAPROC

       RETURN
       END SUBROUTINE Spctinit

!/
!/ End of module W3INITMD -------------------------------------------- /
!/
      END MODULE W3MPInitMD

