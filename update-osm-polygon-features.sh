git submodule init
git submodule update
cp osm-polygon-features/polygon-features.json osm2geojson
cp id-area-keys/areaKeys.json osm2geojson

# TODO: Drop these patch lines when osm-polygon-features sub-module is updated
# Remove the "wall" value from the "barrier" key using jq (https://github.com/rapkin/osm2geojson/issues/7#issuecomment-1967830306)
jq --indent 4 '(.[] | select(.key == "barrier" and .polygon == "whitelist") | .values) -= ["wall"]' osm2geojson/polygon-features.json > tmp1.json
# Add `highway=steps` to the blacklist (#7)
jq --indent 4 '(.[] | select(.key == "highway" and .polygon == "blacklist") | .values) += ["steps"] | if map(.key == "highway" and .polygon == "blacklist") | any | not then . += [{"key": "highway", "polygon": "blacklist", "values": ["steps"]}] else . end' tmp1.json > tmp2.json

mv tmp2.json osm2geojson/polygon-features.json
rm tmp1.json
