!!
!!  FORTRAN 90 program to generate face arrays for a given SMC grid. 
!!
!!  First created:        JGLi12Nov2007
!!  Last modified:        JGLi28Aug2025
!!

MODULE Constants
   IMPLICIT NONE

!! Parameters to be read from InpFile:
   CHARACTER(LEN=16):: SMCGrid='SMC61250' 
   INTEGER:: NCL,  NFC,  MRL 
   INTEGER:: NLon, NLat, NPol
   CHARACTER(LEN=80):: InpFile 
   LOGICAL:: Arctic = .FALSE. 

!! Variables for grid cells.
   INTEGER:: NU, NV, NC, N1, N2, N4, N8, N9, N16, N32
   INTEGER:: NGLo, NArc, NArB, NGLB, NCP, NNorth, NSouth

!! Allocatable arrays, depending on InpFile parameters.
   INTEGER, ALLOCATABLE:: ICE(:,:), ISD(:,:), JSD(:,:), NRLCel(:)

   INTEGER, ALLOCATABLE:: IWest(:), IEast(:), JSoth(:), JNoth(:)

   INTEGER:: I,II,IJ,IJK,J,JJ,JK,JKL,K,KK,KL,KLM,L,LL,LM,LMN,M,MM,MN,N,NN

   CHARACTER(LEN=80):: CelFile, TxtFile

! Initialised variables
   CHARACTER(LEN=1) :: XEXT(6)=(/'S','B','W','E','C','M'/)

END MODULE Constants

!!
!! This program genearte the one level 2D multiple cell grids.
!! Adapted for multiple cell 2D advection tests using UNO schemes.
!!                    J G Li   26 Jul 2007
!!

 PROGRAM SMCGSIDE 
      USE omp_lib
      USE Constants
      IMPLICIT NONE

      REAL:: CNST, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6
      REAL (Kind=8) :: TM1, TM2

!! Interface for the external subroutine READCELL has to be included.
!! Otherwise, PRESENT(ArclFile) in READCELL will always be T(rue)!
      INTERFACE
         SUBROUTINE READCELL( CellFile )
         CHARACTER(Len=*), INTENT(IN)           :: CellFile
         END SUBROUTINE READCELL
      END INTERFACE

! Check command arguments.
      II = COMMAND_ARGUMENT_COUNT()
      IF( II < 1 )THEN
          WRITE(*,*)' *** ERROR, SMCGSide input file should be provided. ***'
          STOP
      ELSE
          WRITE(*,*)' Number of argument = ', II 
      ENDIF

! Get InpFile name from argument 
      CALL GET_COMMAND_ARGUMENT(1, InpFile, Status=K)  
      WRITE(*,*) " *** InpFile is ",  TRIM(InpFile)

! Open input file and read grid parameters.
      OPEN(UNIT=8,FILE= TRIM(InpFile),STATUS='OLD',IOSTAT=nn,ACTION='READ')
      IF(nn /= 0) PRINT*,InpFile//' was not opened! '

          READ(8,*)   SMCGrid 
         WRITE(6,*)   SMCGrid 
          READ(8,*)   NCL,  NFC,  MRL
         WRITE(6,*)   NCL,  NFC,  MRL
          READ(8,*)   NLon, NLat, NPol 
         WRITE(6,*)   NLon, NLat, NPol 
          READ(8,*)   CelFile
         WRITE(6,*)   CelFile
!! Reset Arctic if any polar cell, default Arctic = .FALSE..
       IF( NPol > 0 ) Arctic = .TRUE. 
!         READ(8,*)   Arctic 
         WRITE(6,*)   Arctic 

      CLOSE(8)

! Allocate cell and face variables.
      ALLOCATE( ICE(5,-9:NCL), NRLCel(MRL), ISD(7,NFC), JSD(8,NFC) )

!  Read Cell arrays.
      CALL READCELL( TRIM(CelFile) )

! Allocate face length marking arrays at largest possible sizes.
      LM = 2**(MRL-1)
      MN = LM*256 
      ALLOCATE( IWest(LM), IEast(LM), JSoth(MN), JNoth(MN) )
      
!  Timing of sub to test OpenMP parallelisation.
!$     TM1= OMP_GET_WTIME()

!  Call subroutines to generate flux faces. Arctic=.TRUE. assumes last cell
!  to be polar cell.

      CALL CellSide 

!$     TM2= OMP_GET_WTIME()

!     Open files to store writups
      TxtFile=TRIM(SMCGrid)//'Side.txt'  
      OPEN(UNIT=16,FILE= TRIM(TxtFile),STATUS='UNKNOWN',IOSTAT=nn,ACTION='WRITE')
      IF(nn /= 0) PRINT*,TxtFile//' was not opened! '

!     Header messages and configuration information 
      WRITE(UNIT=16,FMT='(1x/   &
        &  "  Spherical Multiple Cell Grid Face Array Output " /)' )

      WRITE(UNIT=16,FMT='(1x," *** SMCGrid Name = ",A," *** ")')  SMCGrid 

      WRITE(UNIT=16,FMT='(1x," *** CelFile is ",A )')  TRIM(CelFile)
      IF( Arctic ) &
      WRITE(UNIT=16,FMT='(1x," For Arctic cell side is ",A)'   ) '.True.'

      WRITE(UNIT=16,FMT='(1x," Global part cell NGLo  = ",i8)' )  NGLo
      WRITE(UNIT=16,FMT='(1x," Global cells by sizes  = ",6i8)')  NRLCel
      WRITE(UNIT=16,FMT='(1x," Arctic NArc NArB NGLB  = ",6i8)')  NArc, NArB, NGLB
      WRITE(UNIT=16,FMT='(1x," Size 1  NLon NLat No.s = ",3i8)')  NLon, NLat 
      WRITE(UNIT=16,FMT='(1x," Polar cell for Arctic  = ",i8)' )  NPol
      WRITE(UNIT=16,FMT='(1x," Number SMCGrid Levels  = ",i8)' )  MRL 
      WRITE(UNIT=16,FMT='(1x," Total number of U-face = ",i8)' )  NU
      WRITE(UNIT=16,FMT='(1x," Total number of V-face = ",i8)' )  NV
!$    WRITE(UNIT=16,FMT='(1x," Total OpenMP time  (s) = ",ES16.5)' )  TM2-TM1

 3912 FORMAT(1x,i4,3F9.1,ES12.3)
 638  FORMAT(5(i6,f8.2))

!    Close all files
      CLOSE(16)

 9999  PRINT*, ' SMCGSIDE completed '

 END PROGRAM SMCGSIDE 
!  End of main program


! Subroutine that generates the cell side information
 SUBROUTINE CellSide 
   USE omp_lib
   USE Constants
   IMPLICIT NONE
   REAL:: CNST, CNST1, CNST2, CNST3

!!    Test integer division for boundary cell numbers
!!    Size 2**n cell should bounded by -n cells
      DO ii=0, 8
         JJ=2**ii
         CNST=FLOAT(JJ)
         K=-INT( LOG(CNST)/LOG(2.) + 0.1)
      Write(6,*) " Cell size and boundary cell index =", JJ, K
      ENDDO

!!    For Arctic part cells
      IF( Arctic ) THEN

!!    Work out South and North Pole cell number if NPol = 2
      IF (NPol .EQ. 2) THEN
         IF( ICE(2,NC) .GT. ICE(2,NC-1) ) THEN
             NNorth = NC
             NSouth = NC - 1
         ELSE
             NSouth = NC
             NNorth = NC -1
         ENDIF
      ELSE IF(NPol .EQ. 1) THEN
!!    Assume only North Pole in the Arctic is used (NPol = 1).
         NNorth = NC
         NSouth = 0
      ELSE
!!    Insistence setting for Arctic and NPol. Stop.      
         WRITE(6, *) " Inconsistent Arctic and NPol setting:", NPol, Arctic
         STOP
      ENDIF  !! NPol
      ENDIF  !! Arctic

!     Generate i & j inter-sides for all cells
      WRITE(6,*) " Start creating inner face ..."

!     Generate i & j inter-sides for all cells at the highest level
!     Separate i & j faces into 2 sections for OpenMP parallelisation. 

!     Reset system variable OMP_NUM_THREADS if not equal 2.   JGLi28Aug2025 
!$    CALL OMP_SET_NUM_THREADS(2)

!     Start parallel sessions and setup threads.

!$OMP Parallel

!$    WRITE(6,*) "Num_Threads =",  omp_get_num_threads()

!!    Non-shared and fixed variables.
      II=0
      JJ=0
      NCP = NC
      IF( Arctic ) NCP = NC-NPol 

!$OMP Barrier
!!    Set this bariier to ensure fixed variables are defined.

!$OMP Sections  Private(K, KL, L, LM, M, MN, N) 

      DO L=1, NCP

         IF(MOD(L, 5000) .eq. 0) WRITE(6,*) " Done L, II =", L, II

!!  Cyclic boundary for i-side at L-cell east side
         LM=ICE(1,L)+ICE(3,L)
         IF(LM .ge. NLon) LM=LM-NLon

!!  Cell height size is different from width size sometimes
         KL=ICE(2,L)+ICE(4,L)

         DO M=1, NCP

!!  U-faces
            IF( ICE(1,M) .eq. LM ) THEN
!!  Allow quarterly cells across size-changing or merging lines.
                IF( ICE(4,L) <= ICE(4,M) ) THEN 
!!  L cell no larger than M cell, y range should be within M cell one.
                    IF( ICE(2,L) >= ICE(2,M) .AND.   &
                        KL <= ICE(2,M)+ICE(4,M) ) THEN
                        II=II+1
                        ISD(1,II)=LM
                        ISD(2,II)=ICE(2,L)
                        ISD(3,II)=ICE(4,L)
                        ISD(5,II)=L
                        ISD(6,II)=M
                    ENDIF
                ELSE        
!!  L cell smaller than M cell, y range should be within L cell one.
                    IF( ICE(2,L) <= ICE(2,M) .AND.   &
                        KL >= ICE(2,M)+ICE(4,M) ) THEN
                        II=II+1
                        ISD(1,II)=LM
                        ISD(2,II)=ICE(2,M) 
                        ISD(3,II)=ICE(4,M) 
                        ISD(5,II)=L
                        ISD(6,II)=M 
                    ENDIF
                ENDIF
            ENDIF
         END DO

!!    End of L-Loop
      END DO

!$OMP Section

      DO K=1, NCP

         IF(MOD(K, 5000) .eq. 0) WRITE(6,*) " Done K, JJ =", K, JJ

!!  K-cell north side for V-face position.
         MN=ICE(2,K)+ICE(4,K)

         DO N=1, NCP

!!   V-faces
            IF( ICE(2,N) .eq. MN ) THEN 
                IF( ICE(3,K) <= ICE(3,N) ) THEN  
!!  K cell no larger than N cell, x range should be within N cell one.
                    IF( ICE(1,K) >= ICE(1,N) .AND.   &
                        ICE(1,K)+ICE(3,K) <= ICE(1,N)+ICE(3,N) ) THEN
                        JJ=JJ+1
                        JSD(1,JJ)=ICE(1,K)
                        JSD(2,JJ)=MN 
                        JSD(3,JJ)=ICE(3,K)
                        JSD(5,JJ)=K
                        JSD(6,JJ)=N
!!  Minimum Y-size of the two bounding cells will be used to sort 
!!  cell sizes for multi-step implementation.
                        JSD(8,JJ)=MIN(ICE(4,N), ICE(4,K)) 
                    ENDIF
                ELSE
!!  K cell larger than N cell, x range should be within K cell one.
                    IF( ICE(1,K) <= ICE(1,N) .AND.   &
                        ICE(1,K)+ICE(3,K) >= ICE(1,N)+ICE(3,N) ) THEN
                        JJ=JJ+1
                        JSD(1,JJ)=ICE(1,N)
                        JSD(2,JJ)=MN
                        JSD(3,JJ)=ICE(3,N)
                        JSD(5,JJ)=K
                        JSD(6,JJ)=N 
!!  Minimum Y-size of the two bounding cells will be used to sort 
!!  cell sizes for multi-step implementation.
                        JSD(8,JJ)=MIN(ICE(4,N), ICE(4,K)) 
                    ENDIF
                ENDIF
            ENDIF
         END DO

!!    End of K-Loop
      END DO

!$OMP End Sections

!$OMP Barrier
!!    Set this bariier to ensure both U and V face M/N-loop finished. 

      ijk=II
      lmn=JJ

!$OMP Barrier

!$OMP Sections  Private(i, j, ij, K, kk, L, M, N, LM, MN)

!     Set boundary u faces
      WRITE(6,*) " Start creating u boundary face II =", II

!!    Loop over all cells.
      DO L=1, NCP

         IF(MOD(L, 10000) .eq. 0) WRITE(6,*) " Done L II=", L, II

!!    Cyclic boundary need to be taken into account
         LM=ICE(1,L)+ICE(3,L)
         IF(LM .ge. NLon)  LM=LM-NLon

!!    Allocate two arrays to mark L-cell i-side lengths.
         MN=ICE(4,L)
         IWest=0
         IEast=0
         ij=0
         kk=0

!!    Loop through all inner faces 
         DO M=1, ijk

!!    See if the L cell west face is covered
            IF( ISD(1,M) .eq. ICE(1,L) ) THEN
                IF( ISD(2,M)          >= ICE(2,L) .AND.  &
                    ISD(2,M)+ISD(3,M) <= ICE(2,L)+ICE(4,L) ) THEN 
                    i= ISD(2,M) - ICE(2,L) + 1
                    j= ISD(3,M) - 1
                    IWest(i:i+j)=1
                    ij=ij+ISD(3,M)
                ENDIF
            ENDIF

!!    and see if the L cell east face is covered
            IF( ISD(1,M) .eq. LM ) THEN
                IF( ISD(2,M)          >= ICE(2,L) .AND.  &
                    ISD(2,M)+ISD(3,M) <= ICE(2,L)+ICE(4,L) ) THEN 
                    i= ISD(2,M) - ICE(2,L) + 1
                    j= ISD(3,M) - 1 
                    IEast(i:i+j)=1
                    kk=kk+ISD(3,M)
                ENDIF
            ENDIF

!!  End of inner face M=1,ijk loop
         END DO

         IF(kk+ij .gt. 2*ICE(4,L) )  WRITE(6,*) "Over done i-side for cell L,ij,kk=", L, ij, kk
         IF(kk+ij .ge. 2*ICE(4,L) )  CYCLE !! Go to check next cell L 

         IF( ij .eq. 0 )  THEN
!!  Full boundary cell for west side
             II=II+1
             ISD(1,II)=ICE(1,L)
             ISD(2,II)=ICE(2,L)
             ISD(3,II)=ICE(4,L)
!!  New boundary cells proportional to cell y-sizes 
!!  Updated for any 2**n sizes
             ISD(5,II)=-INT( LOG(FLOAT(ISD(3,II)))/LOG(2.) + 0.01 )
             ISD(6,II)=L
         ENDIF

         IF( kk .eq. 0)  THEN
!!  Full boundary cell for east side
             II=II+1
             ISD(1,II)=LM
             ISD(2,II)=ICE(2,L)
             ISD(3,II)=ICE(4,L)
             ISD(5,II)=L
!!  Updated for any 2**n sizes
             ISD(6,II)=-INT( LOG(FLOAT(ISD(3,II)))/LOG(2.) + 0.01 )
         ENDIF

         IF( ij .gt. 0  .AND. ij .lt. MN )  THEN
!!  Half or quarter cell size for west boundary faces
             i = 0
             DO WHILE ( i < MN )
                 IF( IWest(i+1) == 1 ) THEN
                     i = i + 1 
                 ELSE
                     j = 0 
                     DO k=i+1, MN
                         IF( IWest(k) == 0 ) j = j + 1 
                     ENDDO
!!  Add a j-sized boundary cell
                     II=II+1
                     ISD(1,II)=ICE(1,L) 
                     ISD(2,II)=ICE(2,L) + i
                     ISD(3,II)=j 
!!  Updated for any 2**n sizes
                     ISD(5,II)=-INT( LOG(FLOAT(ISD(3,II)))/LOG(2.) + 0.01 )
!!  Size 1 for cell 0, size 2 uses cell -1 and size 4 uses cell -2
                     ISD(6,II)=L
                     i = i + j 
                 ENDIF
             END DO
         ENDIF

         IF( kk .gt. 0  .and. kk .lt. MN )  THEN
!!  Half or quarter cell size for east boundary faces
             i = 0
             DO WHILE ( i < MN )
                 IF( IEast(i+1) == 1 ) THEN
                     i = i + 1 
                 ELSE
                     j = 0 
                     DO k=i+1, MN
                         IF( IEast(k) == 0 ) j = j + 1 
                     ENDDO
!!  Add a j-sized boundary cell
                     II=II+1
                     ISD(1,II)=LM 
                     ISD(2,II)=ICE(2,L) + i
                     ISD(3,II)=j 
!!  Updated for any 2**n sizes
                     ISD(5,II)=L
                     ISD(6,II)=-INT( LOG(FLOAT(ISD(3,II)))/LOG(2.) + 0.01 )
!!  Size 1 for cell 0, size 2 uses cell -1 and size 4 uses cell -2
                     i = i + j 
                 ENDIF
             END DO
         ENDIF

!!   End of L-loop
      ENDDO


!$OMP  Section

!     Set boundary v faces
      WRITE(6,*) " Start creating v boundary face JJ=", JJ

!!    Loop over all cells
      DO N=1, NCP

         IF(MOD(N, 10000) .eq. 0) WRITE(6,*) " Done N JJ=", N, JJ

!!    Allocate two arrays to mark N-cell j-side lengths.
         MN=ICE(3,N)
         JSoth=0
         JNoth=0
         ij=0
         kk=0

!!    Loop through all V faces already set 
         DO M=1, lmn

!!    See if the N cell south face is covered
            IF( JSD(2,M) .eq. ICE(2,N) ) THEN
                IF( JSD(1,M)          >= ICE(1,N) .AND.  & 
                    JSD(1,M)+JSD(3,M) <= ICE(1,N)+ICE(3,N) ) THEN
                    i= JSD(1,M) - ICE(1,N) + 1
                    j= JSD(3,M) - 1
                    JSoth(i:i+j)=1
                    ij=ij+JSD(3,M)
                ENDIF
            ENDIF

!!    and see if the N cell north face is covered
            IF( JSD(2,M) .eq. ICE(2,N) + ICE(4,N) )  THEN 
                IF( JSD(1,M)          >= ICE(1,N) .AND.  & 
                    JSD(1,M)+JSD(3,M) <= ICE(1,N)+ICE(3,N) ) THEN
                    i= JSD(1,M) - ICE(1,N) + 1
                    j= JSD(3,M) - 1
                    JNoth(i:i+j)=1
                    kk=kk+JSD(3,M)
                ENDIF
            ENDIF

!!  End of inner face M=1,lmn loop
         END DO

         IF( kk+ij .gt. 2*ICE(3,N) )  WRITE(6,*)  "Over done j-side for N, ij, nn=", N, ij, kk
         IF( kk+ij .ge. 2*ICE(3,N) )  CYCLE !! Go to check next cell N

         IF( ij .eq. 0)  THEN
!!  Full boundary cell for south side
             JJ=JJ+1
             JSD(1,JJ)=ICE(1,N)
             JSD(2,JJ)=ICE(2,N)
             JSD(3,JJ)=ICE(3,N)
!!  Add faces to the south polar cell if NSouth > 0. 
             IF( (NSouth > 0) .AND. (ICE(2,NSouth)+ICE(4,NSouth) .eq. ICE(2,N)) ) THEN
                 JSD(5,JJ)=NSouth
                 WRITE(6,*) "Set south pole v face for cell N", N
             ELSE
!!  New boundary cells proportional to cell sizes 
!!  Updated for any 2**n sizes
                 JSD(5,JJ)=-INT( LOG(FLOAT(ICE(3,N)))/LOG(2.) + 0.01 )
             ENDIF
             JSD(6,JJ)=N
             JSD(8,JJ)=ICE(4,N)
         ENDIF

         IF( kk .eq. 0)  THEN
!!  Full boundary cell for north side
             JJ=JJ+1
             JSD(1,JJ)=ICE(1,N)
             JSD(2,JJ)=ICE(2,N)+ICE(4,N)
             JSD(3,JJ)=ICE(3,N)
             JSD(5,JJ)=N
!!  North polar cell takes the whole last 4 rows above JSD=ICE(2,NNorth).
!!  Note ICE(2,N) represents cell lower-side.  N polar cell is the NNorth cell.
             IF( (NNorth > 0) .AND. (ICE(2,N)+ICE(4,N) .eq. ICE(2,NNorth)) ) THEN
                 JSD(6,JJ)=NNorth
                 WRITE(6,*) "Set north pole v face for cell N", N
             ELSE
!!  Updated for any 2**n sizes
                 JSD(6,JJ)=-INT( LOG(FLOAT(ICE(3,N)))/LOG(2.) + 0.01 )
             ENDIF
             JSD(8,JJ)=ICE(4,N)
         ENDIF
  
         IF( ij .gt. 0  .AND. ij .lt. MN )  THEN
!!  Half or quarter cell size for south boundary faces
             i = 0
             DO WHILE ( i < MN )
                 IF( JSoth(i+1) == 1 ) THEN
                     i = i + 1 
                 ELSE
                     j = 0 
                     DO k=i+1, MN
                         IF( JSoth(k) == 0 ) j = j + 1 
                     ENDDO
!!  Add a j-sized boundary cell
                     JJ=JJ+1
                     JSD(1,JJ)=ICE(1,N) + i
                     JSD(2,JJ)=ICE(2,N)
                     JSD(3,JJ)=j 
!!  New boundary cells proportional to cell sizes 
!!  Updated for any 2**n sizes
                     JSD(5,JJ)=-INT( LOG(FLOAT(JSD(3,JJ)))/LOG(2.) + 0.01 )
                     JSD(6,JJ)=N
                     JSD(8,JJ)=ICE(4,N)
                     i = i + j 
                 ENDIF
             END DO
         ENDIF

         IF( kk .gt. 0  .and. kk .lt. MN )  THEN
!!  Half or quarter cell size for north boundary faces
             i = 0
             DO WHILE ( i < MN )
                 IF( JNoth(i+1) == 1 ) THEN
                     i = i + 1 
                 ELSE
                     j = 0 
                     DO k=i+1, MN
                         IF( JNoth(k) == 0 ) j = j + 1 
                     ENDDO
!!  Add a j-sized boundary cell
                     JJ=JJ+1
                     JSD(1,JJ)=ICE(1,N) + i
                     JSD(2,JJ)=ICE(2,N) + ICE(4,N)
                     JSD(3,JJ)=j 
                     JSD(5,JJ)=N
!!  New boundary cells proportional to cell sizes 
!!  Updated for any 2**n sizes
                     JSD(6,JJ)=-INT( LOG(FLOAT(JSD(3,JJ)))/LOG(2.) + 0.01 )
                     JSD(8,JJ)=ICE(4,N)
                     i = i + j 
                 ENDIF
             END DO
         ENDIF

!!   End of N-loop
      ENDDO

!$OMP End Sections
!$OMP Barrier

!   Store top level U V side numbers in NU NV 
      NU=II
      NV=JJ

!$OMP Sections Private(i, j, k, L, M, n, kk, nn)

!!  Loop over all u faces to find the second cells next to the L and M cells
!!  Boundary cells will be duplicated for second cells
      WRITE(6,*) " Find extra second u cell II JJ=", II, JJ
      DO i=1, NU
         L=ISD(5,i)
         M=ISD(6,i)
         kk=0
         nn=0

!!  Boundary L cell just duplicate it as LL cell
         IF(L .LE. 0) THEN
            ISD(4,i)=L
            kk=1
         ELSE
!!  Find the second LL cell by loop over all faces again
!!  The two U faces have to share at least one y-end.
!!  The second U face should be no less than this face.  
!!  Restore one face end equal and suspend no less requirement. JGLi28Feb2012
            DO k=1, NU
               IF( L .EQ. ISD(6,k) ) THEN 
                   IF( (ISD(2,i)+ISD(3,i) .eq. ISD(2,k)+ISD(3,k)) .or. &
     &                 (ISD(2,i) .eq. ISD(2,k)) )  THEN
                       ISD(4,i)=ISD(5,k)
                       kk=1
                   ENDIF
               ENDIF
            ENDDO
         ENDIF

!!  Boundary M cell just duplicate it as MM cell
         IF(M .LE. 0) THEN
            ISD(7,i)=M
            nn=1
         ELSE
!!  Find the second MM cell by loop over all faces again
!!  The two U faces have to share at least one y-end.
            DO n=1, NU
               IF( M .EQ. ISD(5,n) ) THEN 
                   IF( (ISD(2,i)+ISD(3,i) .eq. ISD(2,n)+ISD(3,n)) .or. &
     &                 (ISD(2,i) .eq. ISD(2,n)) )  THEN
                       ISD(7,i)=ISD(6,n)
                       nn=1
                   ENDIF
               ENDIF
            ENDDO
         ENDIF

!!  Duplicate central cell if upstream cells are not selected.
         IF( kk .eq. 0) THEN
            ISD(4,i)=L
         ENDIF
         IF( nn .eq. 0) THEN
            ISD(7,i)=M
         ENDIF

         IF(MOD(i, 10000) .eq. 0) WRITE(6,*) " Done U face i=", i

!!  End of u face loop
      ENDDO


!$OMP Section

!!  Loop over all v faces to find the second cells next to the L and M cells
!!  Boundary cells will be duplicated for second cells
      WRITE(6,*) " Find extra second v cell II JJ=", II, JJ

      DO j=1, NV
         L=JSD(5,j)
         M=JSD(6,j)
         kk=0
         nn=0

!!  Boundary L cell just duplicate it as LL cell
!!  South Pole L cell is also duplicated.
         IF( (L .LE. 0) .OR. (L .GT. NC-NPol) ) THEN
            JSD(4,j)=L
            kk=1
         ELSE
!!  Find the second LL cell by loop over all faces again
!!  The two V faces have to share at least one x-end.
!!  Restore one face end equal and suspend no less requirement. JGLi28Feb2012
            DO k=1, NV
               IF( (L .EQ. JSD(6,k)) .AND.                                 &
     &             ( (JSD(1,j)+JSD(3,j) .eq. JSD(1,k)+JSD(3,k)) .or.       &
     &               (JSD(1,j) .eq. JSD(1,k)) ) )  THEN 
                   JSD(4,j)=JSD(5,k)
                   kk=1
               ENDIF
            ENDDO
         ENDIF

!!  Boundary M cell just duplicate it as MM cell
!!  Duplicate north polar cell as well
         IF( (M .LE. 0) .OR. (M .GT. NC-NPol) ) THEN
            JSD(7,j)=M
            nn=1
         ELSE
!!  Find the second LL cell by loop over all faces again
!!  The two V faces have to share at least one x-end.
            DO n=1, JJ
               IF( (M .EQ. JSD(5,n)) .AND.                                 &
     &             ( (JSD(1,j)+JSD(3,j) .eq. JSD(1,n)+JSD(3,n)) .or.       &
     &               (JSD(1,j) .eq. JSD(1,n)) ) )  THEN 
                   JSD(7,j)=JSD(6,n)
                   nn=1
               ENDIF
            ENDDO
         ENDIF

!!  Duplicate central cell if upstream cells are not selected.
         IF( kk .eq. 0) THEN
             JSD(4,j)=L
         ENDIF
         IF( nn .eq. 0) THEN
             JSD(7,j)=M
         ENDIF

         IF(MOD(j, 10000) .eq. 0) WRITE(6,*) " Done V face j=", j

!!  End of v face loop
      ENDDO

!$OMP End Sections
!$OMP Barrier

      ij=0
      mn=0

!$OMP Sections Private(i, j, k, L, M)

!!  Check whether any overlaping exists
      WRITE(6,*) " Check any U-face overlaping NU = ", NU

      DO i=1, NU-1
         L=ISD(1,i)
         M=ISD(2,i)
            DO k=i+1, NU
               IF( L .EQ. ISD(1,k) .AND. M .EQ. ISD(2,k) )  THEN
                 ij=ij+1
                 WRITE(6,*) ij, ' Overlaping u face k, i, j, l, mm, m, n, nn' 
                 WRITE(6,333) i, (ISD(n,i), n=1,7)
                 WRITE(6,333) k, (ISD(n,k), n=1,7)
               ENDIF
            ENDDO
         IF(MOD(i, 10000) .eq. 0) WRITE(6,*) " Checked U face i=", i
      ENDDO

 333  FORMAT(9I8)

!$OMP Section

      WRITE(6,*) " Check any V-face overlaping NV = ", NV

      DO j=1, NV-1
         L=JSD(1,j)
         M=JSD(2,j)
            DO k=j+1, NV
               IF( L .EQ. JSD(1,k) .AND. M .EQ. JSD(2,k) )  THEN
                 mn=mn+1
                 WRITE(6,*) mn, ' Overlaping v face k, i, j, l, mm, m, n, nn'
                 WRITE(6,333) j, (JSD(n,j), n=1,7)
                 WRITE(6,333) k, (JSD(n,k), n=1,7)
               ENDIF
            ENDDO
         IF(MOD(j, 10000) .eq. 0) WRITE(6,*) " Checked V face j=", j
      ENDDO

!$OMP End Sections
!$OMP Barrier

!$OMP End Parallel

      IF(ij + mn .GT. 0) THEN
      WRITE(6,*) " Overlapping total ij, mn=", ij, mn
      ENDIF

!!  Output ISD JSD variables for later use
      WRITE(6,*) " Storing face array info NU,NV=", NU, NV

   OPEN(UNIT=10,FILE=TRIM(SMCGrid)//'ISide.d',STATUS='UNKNOWN',IOSTAT=nn)
   IF(nn /= 0) PRINT*,' File Pros was not opened! '
!     WRITE(10,FMT='(1x,i8)') NU
      DO I=1,NU
         WRITE(10,FMT='(i7,i6,i5,4i8)')  (ISD(N,I), N=1,7)
      END DO
   CLOSE(10)

   OPEN(UNIT=11,FILE=TRIM(SMCGrid)//'JSide.d',STATUS='UNKNOWN',IOSTAT=nn)
   IF(nn /= 0) PRINT*,' File Pros was not opened! '
!     WRITE(11,FMT='(1x,i8)') NV
      DO J=1,NV
         WRITE(11,FMT='(i7,i6,i5,4i8,i4)')  (JSD(N,J), N=1,8)
      END DO
   CLOSE(11)

   PRINT*, ' I J-Sides output done '

 999  PRINT*, ' Sub CellSide ended.'

      RETURN

 END SUBROUTINE CellSide


! Subroutine to read cell arrays and to define grid variables.
!  First created:    1 Apr 2015   Jian-Guo Li
!  Last modified:   28 Apr 2021   Jian-Guo Li

       SUBROUTINE READCELL( CellFile )
         USE Constants, ONLY: ICE, NRLCel, NGLo, NGLB, NC,  &
                              MRL, Arctic, NArc, NArB 
         IMPLICIT NONE
         CHARACTER(Len=*), INTENT(IN)           :: CellFile

         INTEGER :: I, J, K
         REAL:: CNST, CNST0, CNST1, CNST2, CNST3, CNST4, CNST5, CNST6

!  Read Global and Arctic part Multiple-Cell info

       OPEN(UNIT=8, FILE=TRIM(CellFile), STATUS='OLD',IOSTAT=K,ACTION='READ')
       IF(K /= 0) PRINT*, CellFile//' was not opened! '
       IF( Arctic ) THEN
          READ (8,*) NArc, NArB, NGLB
          NC = NArc
       ELSE
          READ (8,*) NGLo, NRLCel
          NC = NGLo
       ENDIF 
       DO J=1,NC 
          READ (8,*) ICE(1,J), ICE(2,J), ICE(3,J), ICE(4,J), ICE(5,J)
       END DO
       CLOSE(8)
       PRINT*, CellFile//' read done ', NC 

!  Output a few to check input values
       DO J=1, NC, NC/4
          WRITE(6,'(i8,2i6,2i4,i6)') J, (ICE(i,J), i=1,5) 
       END DO

!    Boundary -9 to 0 cells for cell size 2**n
!    Note the position indice for bounary cell are not used.
       ICE(1,-9:0)=0
       ICE(2,-9:0)=0
       ICE(3,   0)=1
       ICE(4,   0)=1
       ICE(5,-9:0)=0
       DO J=1,9
          ICE(3,-J)=ICE(3,-J+1)*2
!!   Restrict boundary cell y-size no more than base cell size.
          IF( J < MRL ) THEN
              ICE(4,-J)=ICE(3,-J)
          ELSE
              ICE(4,-J)=ICE(MRL,-J)
          ENDIF
!  Output all boundary cell to check assigned values
          WRITE(6,'(i8,2i6,2i4,i6)') J, (ICE(i,-J), i=1,5) 
       ENDDO

!! All done
       RETURN
       END SUBROUTINE READCELL
!!

