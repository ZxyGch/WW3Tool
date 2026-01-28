#!/bin/sh -e

# $1 : grid name GLOB-30M like used for GLOB-30M.bound
# $2 : spec directory : path where SPEC folder is stored


if [ $# -eq 2 ] ; then
  mods=$1
  path_spec=$2
  path_d=$PWD
elif [ $# -eq 0 ] ; then
  year=2015
  source mww3_setup.sh

  if [ "$spec_zone" = 'glob' ] ; then
    SPEC_DIR=$GLOB_DIR
    if [ "$wind" == "wind_ncep" ]
    then
      wtype="_CFSR"
    elif  [ "$wind" == "wind_ecmwf" ]
    then
      wtype="_ECMWF"
    fi
  elif [ "$spec_zone" = 'med' ] ; then
    SPEC_DIR=$MED_DIR
    wtype=''
  elif [ "$spec_zone" = 'local' ] ; then
    SPEC_DIR=$path_d/SPECTRA
    wtype=''
  else
    echo '[ERROR] spec_zone not recognized'
    exit 1
  fi

  if [ ! -e $SPEC_DIR ] ; then
    echo "[ERROR] spec_dir does not exist $SPEC_DIR"
    exit 1
  else
    echo "SPEC_DIR : $SPEC_DIR"
  fi
  path_spec=$SPEC_DIR/${year}${wtype}

fi # arg

for mod in $mods
do
  echo $mod
  rm -f spec_${mod}.list
  cat $path_d/${mod}.bound | while read line
  do
    echo $line
    lon=$(echo $line | cut -d ' ' -f1)
    intlon=$(echo $lon | cut -d '.' -f1 | cut -d '-' -f2)
    intlon=$(printf "%.3d" "$intlon")
    intlon=$(echo $intlon | cut -c1-2)
    echo "intlon : $intlon"

    lat=$(echo $line | cut -d ' ' -f2)
    intlat=$(echo $lat | cut -d '.' -f1 | cut -d '-' -f2)
    intlat=$(printf "%.2d" "$intlat")
    intlat=$(echo $intlat | cut -c1-1)
    echo "intlat : $intlat"


    case $lon in
      *+*) echo "East"; signlon='E';;
      *-*) echo "West"; signlon='W';;
      *) echo "East"; signlon='E';;
    esac 

    case $lat in
      *+*) echo "North"; signlat='N';;
      *-*) echo "South"; signlat='S';;
      *) echo "North"; signlat='N';;
    esac 

    spec="*.${signlon}${intlon}*${signlat}${intlat}*_spec.nc"
    find $path_spec/SPEC_* -name "$spec" >> $path_d/spec_${mod}.list
  done
  # sort and remove duplicated lines
  sort -u $path_d/spec_${mod}.list -o $path_d/spec_${mod}.list

done

