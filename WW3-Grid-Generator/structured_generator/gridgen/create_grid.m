function create_grid(fname_nml, entry)
%CREATE_GRID  cd to bin/ and run a gridgen routine with this folder's grid.nml.
%
%   create_grid
%   create_grid('/path/to/other.nml')
%   create_grid('', @create_boundary)
%   create_grid(fullfile(pwd,'grid.nml'), 'create_grid_curv')

gridgen_root = fileparts(mfilename('fullpath'));
bin_root = fullfile(gridgen_root, 'bin');
if nargin < 1 || isempty(fname_nml)
    fname_nml = fullfile(gridgen_root, 'grid.nml');
end
if exist(fname_nml, 'file') ~= 2
    cand = fullfile(gridgen_root, fname_nml);
    if exist(cand, 'file') == 2
        fname_nml = cand;
    end
end

cur_wd = cd;
cd(bin_root);
try
    if nargin < 2 || isempty(entry)
        % After cd(bin), this resolves to bin/create_grid.m (not this launcher).
        create_grid(fname_nml);
    elseif isa(entry, 'function_handle')
        entry(fname_nml);
    else
        feval(entry, fname_nml);
    end

    % Post-process grid outputs in DATA_DIR (paths in nml are relative to this bin folder).
    addpath(bin_root);
    init_nml = read_namelist(fname_nml, 'GRID_INIT');
    data_dir = init_nml.data_dir;
    fname = init_nml.fname;
    fname(fname == '''') = [];

    nlstub = fullfile(data_dir, ['namelists_', fname, '.nml']);
    if exist(nlstub, 'file') == 2
        delete(nlstub);
    end

    src = fullfile(data_dir, ['ww3_grid.nml.', fname]);
    dst = fullfile(data_dir, 'grid.meta');
    if exist(src, 'file') == 2
        if exist(dst, 'file') == 2
            delete(dst);
        end
        movefile(src, dst);
    end
catch err
    cd(cur_wd);
    rethrow(err);
end
cd(cur_wd);

end
