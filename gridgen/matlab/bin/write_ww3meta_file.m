function [messg,errno] = write_ww3meta_file(fname,gtype,lon,lat,varargin)
% -------------------------------------------------------------------------
% Write WW3 meta file (.meta) for grid outputs.
% -------------------------------------------------------------------------

fid = fopen([fname,'.meta'],'w');
[messg,errno] = ferror(fid);
if (errno ~= 0)
    fprintf(1,'!!ERROR!!: %s \n',messg);
    fclose(fid);
    return;
end

str1 = '$ Define grid -------------------------------------- $';
str2 = '$  1 Type of grid, coordinate system and type of closure: GSTRG, FLAGLL,';
str3 = '$    CSTRG';
str4 = '$      GSTRG  : String indicating type of grid :';
str5 = '$               ''RECT''  : Rectilinear grid.';
str6 = '$               ''CURV''  : Curvilinear grid.';
str7 = '$      FLAGLL : Logical, true for spherical (lon/lat) coordinates';
str8 = '$      CSTRG  : String indicating the type of grid index space closure :';
str9 = '$               ''NONE''  : No grid closure';
str10= '$               ''SMPL''  : Simple grid closure';
str11= '$               ''TRPL''  : Tripole grid closure';
fprintf(fid,'%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n', ...
    str1,str2,str3,str4,str5,str6,str7,str8,str9,str10,str11);

fprintf(fid,'   ''%s''  %s %s\n',gtype,'T','''NONE''');

switch gtype
    case 'RECT'
        N1 = varargin{1};
        N2 = varargin{2};
        [Ny,Nx] = size(lon);
        fprintf(fid,'%d \t %d \n',Nx,Ny);
        fprintf(fid,'%5.2f \t %5.2f \t %5.2f \n',(lon(1,2)-lon(1,1))*60,...
               (lat(2,1)-lat(1,1))*60,60);
        fprintf(fid,'%8.4f \t %8.4f \t %5.2f\n',lon(1,1),lat(1,1),1);
        base_idx = 3;
    case 'CURV'
        N1 = varargin{1};
        N2 = varargin{2};
        N3 = varargin{3};
        [Ny,Nx] = size(lon);
        fprintf(fid,'%d \t %d \n',Nx,Ny);
        fprintf(fid,'%d  %f  %5.2f  %d  %d %s  %s  %s  \n',20,N3,0.0,1,...
               1,'''(....)''','NAME',['''',fname,'.lon','''']);
        fprintf(fid,'%d  %f  %5.2f  %d  %d %s  %s  %s  \n',30,N3,0.0,1,...
               1,'''(....)''','NAME',['''',fname,'.lat','''']);
        base_idx = 4;
    otherwise
        fprintf(1,'!!ERROR!!: Unrecognized Grid Type\n');
        fclose(fid);
        return;
end

if nargin >= base_idx + 3
    ext1 = varargin{base_idx};
    ext2 = varargin{base_idx + 1};
    ext3 = varargin{base_idx + 2};
else
    ext1 = '.bot';
    ext2 = '.obst';
    ext3 = '.mask_nobound';
end

fprintf(fid,'$ Bottom Bathymetry \n');
fprintf(fid,'%5.2f  %5.2f  %d  %f  %d  %d %s  %s  %s \n',-0.1,2.5,40,N1,1,1,...
    '''(....)''','NAME',['''',fname,ext1,'''']);
fprintf(fid,'$ Sub-grid information \n');
fprintf(fid,'%d  %f  %d  %d  %s  %s  %s  \n',50,N2,1,1,'''(....)''','NAME',...
    ['''',fname,ext2,'''']);
fprintf(fid,'$ Mask Information \n');
fprintf(fid,'%d  %d  %d  %s  %s  %s  \n',60,1,1,'''(....)''','NAME',...
    ['''',fname,ext3,'''']);

fclose(fid);
return;
