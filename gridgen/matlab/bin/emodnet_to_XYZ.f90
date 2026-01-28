MODULE Grid
   INTEGER         , DIMENSION(:),      ALLOCATABLE :: sdev,depthg,depthf
   INTEGER         , DIMENSION(:),      ALLOCATABLE :: depth
   REAL            , DIMENSION(:,:),    ALLOCATABLE :: deptho
   INTEGER nx,ny,nxo,nyo
   REAL, PARAMETER :: depthmax = 300.
   REAL, PARAMETER :: depthmin = 0.
END MODULE Grid
!*********************************************************************
PROGRAM nc_to_XYZ  !generates a binary bathymetry file
   USE GRID
   USE NETCDF
   IMPLICIT NONE
    
   
   INTEGER I,J,I0,J0,I1,I2,J1,J2,II,dummyint,lrec,irec,missing
   INTEGER iret,ncid,imin,imax,jmin,jmax,TESTS
   INTEGER(KIND=4) JALL,NALL,xysize
   INTEGER nxold,nyold,nx1,ny1,dimln(5),dimid(5),varid(5),nz,nt
   INTEGER startnc(3),count(3),size2(2)
   DOUBLE PRECISION  dx,dy,lonmin,lonmax,latmin,latmax,dxdy(2)
   REAL    lonmino,lonmaxo,latmino,latmaxo
   CHARACTER(len=5)                :: dummystring
   CHARACTER(256)                  :: filelog,filegrd,argbuf,numero
   REAL                            :: lon, lat
!     
!     Check the argument line
!     
      if (iargc().lt.5) then
         stop
      endif
!
!     Get the arguments
!
      call getarg(1,filegrd)
      call getarg(2,numero)
      read(numero,*) latmino
      call getarg(3,numero)
      read(numero,*) latmaxo
      call getarg(4,numero)
      read(numero,*) lonmino
      call getarg(5,numero)
      read(numero,*) lonmaxo

      iret=NF90_OPEN (filegrd,NF90_NOWRITE,ncid)

!      iret=NF90_INQ_DIMID (ncid, 'side', dimid(1))
!      iret=NF90_INQ_DIMID (ncid, 'xysize', dimid(2))
      iret=NF90_INQ_DIMID (ncid, 'COLUMNS', dimid(1))
      iret=NF90_INQ_DIMID (ncid, 'LINES', dimid(2))
      iret=NF90_INQUIRE_DIMENSION (ncid, dimid(1),len=nx)
      iret=NF90_INQUIRE_DIMENSION (ncid, dimid(2),len=ny)
!      iret=NF90_INQ_VARID (ncid, 'spacing', varid(1))
      iret=NF90_INQ_VARID (ncid, 'DEPTH', varid(2))
!     iret=NF90_INQ_VARID (ncid, 'dimension', varid(3))

!      lonmin=-179-(59.75)/60.
!     latmin=-89-(59.75)/60.
      lonmin=3.5
      latmin=40.

!      iret=nf90_get_var(ncid,varid(3),size2)
!      nx=size2(1)
!      ny=size2(2)
      WRITE(6,*) 'NX,NY:',nx,ny
      xysize=nx*ny
      allocate(depth(nx))
!      iret=nf90_get_var(ncid,varid(1),dxdy)
!      iret=nf90_get_var(ncid,varid(2),depth)
      dxdy(1)=0.00208333333333333
      dxdy(2)=0.00208333333333333

      imin=1+NINT((lonmino-lonmin)/dxdy(1))
      jmin=1+NINT((latmino-latmin)/dxdy(2)) 
      imax=1+NINT((lonmaxo-lonmin)/dxdy(1))
      jmax=1+NINT((latmaxo-latmin)/dxdy(2))
      nxo=imax-imin+1
      nyo=jmax-jmin+1
      WRITE(6,*) 'IMIN:',imin,imax,jmin,jmax,nxo,nyo
      ALLOCATE(deptho(nxo,nyo))
  NALL=0
 OPEN(3,file='xyz.dat',status='unknown')
  JALL=0
  DO J=jmax,jmin,-1
!    iret=nf90_get_var(ncid,varid(2),depth,start = (/ nx*(NY-J)+1 /))
     iret=nf90_get_var(ncid,varid(2),depth, start = (/ 1, J /), &
                       count = (/ nx, 1 /))
    DO I=imin,imax   
      JALL=JALL+1
      lon=dxdy(1)*(I-1)+lonmin
      lat=dxdy(2)*(J-1)+latmin
      TESTS=1
    !  IF (lon.LE.-90.AND.lon.GT.-98.AND.lat.GE.11.AND.lat.LT.17) TESTS=TESTS +1
   !IF (lon.LE.-2.AND.lon.GT.-16.AND.lat.GE.49.AND.lat.LT.60) TESTS=TESTS +1
  
   ! IF (lon.LE.-5.50.AND.lat.GE.50) TESTS=TESTS +1
      !IF (lon.GT.-5.50.AND.lon.LE.-3.5.AND.lat.GE.50.71) TESTS=TESTS +1
      !IF (lon.GT.0.AND.lat.GE.51.38) TESTS=TESTS +1
      !IF (lon.GE.2.408.AND.LAT.LT.51.5.AND.LAT.GE.50) TESTS=TESTS+1 
      !IF (lon.GE.2.25.AND.LAT.GT.51.5) TESTS=TESTS+1
     ! IF (lon.GE.52) TESTS=TESTS+1
     ! IF (lon.LE.-2.AND.LAT.LE.44) TESTS=TESTS+1
     ! IF (lon.LE.-2.25.AND.LAT.LE.44.75)  TESTS=TESTS+1
     ! IF (lon.LE.-3.5.AND.LAT.LE.45.50) TESTS=TESTS +1
! Martinique cut-out
!      IF (lon.GE.-61.4.AND.LON.LE.-60.6.AND.LAT.GE.14.2.AND.LAT.LE.15) TESTS=0 
! Guadeoupe cut-out
!      IF (lon.GE.-61.9.AND.LAT.LT.16.57.AND.LON.LT.-60.75.AND.LAT.GE.15.73) TESTS= 0
 !     IF (lon.LT.-60.OR.LAT.LT.-39.OR.LON.GT.-49.OR.LAT.GE.-32) TESTS= 0

      IF (TESTS.GE.1) THEN 
        NALL=NALL+1
!        WRITE(3,'(2F14.8,4I6)') lon,lat,-1*DEPTH(I) !,I-imin+1,J-jmin+1
        WRITE(3,'(2F14.8,I6)') lon,lat,DEPTH(I) !,I-imin+1,J-jmin+1
      ELSE  
        DEPTH(I)=200.
      ENDIF
!      DEPTHO(I-imin+1,J-jmin+1)=-1.*REAL(DEPTH(I))
       DEPTHO(I-imin+1,J-jmin+1)=REAL(DEPTH(I))
    ENDDO
  ENDDO

 WRITE(6,*) 'NALL:',NALL 
 dx=dxdy(1)*cos(0.5*(latmaxo+latmino)*acos(-1.)/180)*4E7/360.
! WRITE(6,*) 'DLON  ... :',nxo*dx,dx
 dy=dxdy(2)*4E7/360.
! WRITE(6,*) 'DLAT  ... :',nyo*dy,dy

   OPEN(2,file='xyz.log', status='unknown')
      WRITE(2,*) latmino,latmaxo,lonmino,lonmaxo
      WRITE(2,*) '0 0 0 0'
      WRITE(2,*) dx,dy
      WRITE(2,*) nxo,nyo
   CLOSE(2)

   lrec=nyo*4
   OPEN(2,FILE='xyz.grd', status='unknown',access='direct',recl=lrec)
      DO I=1,nxo
         WRITE(2,rec=I) DEPTHO(I,1:nyo) 
         WRITE(6,*) 'TEST:',I,DEPTHO(I,1:nyo) 
      END DO
   CLOSE(2)   

  
   CLOSE(3)
   WRITE(6,*) 'TRANSFER OK'
END
