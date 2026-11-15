#!/usr/bin/env bash
# Download / refresh all source datasets, then rebuild data/fieldshift.db.
# Each step caches into data/raw and skips what is already there; user accounts, reviews and feedback are kept.
set -euo pipefail
cd "$(dirname "$0")/backend"
PY=.venv/bin/python
mkdir -p ../data/raw/stat
# AzStat regional yield (2.186-2.257) and production (2.112-2.185) tables
for n in 187 188 191 194 196 197 198 202 203 204 205 206 207 208 210 211 214 215 219 220 224 225 227 228 230 231 \
         232 234 236 237 238 241 242 243 244 250 251 252 255 256 257 113 114 117 120 122 123 124 128 129 130 131 \
         132 133 134 136 137 140 141 145 146 151 152 154 155 157 158 159 161 163 164 165 168 169 170 171 177 178 \
         179 182 184 185; do
  f=../data/raw/stat/2.$n.xls
  $PY -c "import xlrd,sys; xlrd.open_workbook(sys.argv[1])" "$f" 2>/dev/null && continue
  curl -sfL -m 60 -o "$f" "https://www.stat.gov.az/source/agriculture/az/2.$n.xls"; sleep 1
done
[ -f ../data/raw/adm2.geojson ] || curl -sfL -o ../data/raw/adm2.geojson \
  https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/AZE/ADM2/geoBoundaries-AZE-ADM2_simplified.geojson
mkdir -p ../data/raw/ecocrop
[ -f ../data/raw/ecocrop/ecocrop.rds ] || curl -sfL -o ../data/raw/ecocrop/ecocrop.rds \
  https://raw.githubusercontent.com/cran/Recocrop/master/inst/parameters/ecocrop.rds
$PY -m etl.regions
$PY -m etl.soil
$PY -m etl.fetch_power
$PY -m etl.fetch_nex     # NASA NEX-GDDP-CMIP6 projections, ~15 min
# world layer: provinces of 198 countries
$PY -m etl.world_geo            # geoBoundaries ADM1
$PY -m etl.world_points         # farmland-elevation point per province (NOAA ETOPO1)
$PY -m etl.world_soil           # SoilGrids zonal means
$PY -m etl.world_power          # NASA POWER per province (lapse-rate corrected), ~2 h
$PY -m etl.fetch_nex_world      # NASA NEX-GDDP-CMIP6 global, 2-degree sampling
$PY -m etl.geo_web              # browser-sized GeoJSON
mkdir -p ../data/raw/faostat
[ -f "../data/raw/faostat/Production_Crops_Livestock_E_All_Data_(Normalized).csv" ] || {
  curl -sfL -o ../data/raw/faostat/qcl.zip "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
  (cd ../data/raw/faostat && unzip -o -q qcl.zip); }
$PY -m etl.build_db
